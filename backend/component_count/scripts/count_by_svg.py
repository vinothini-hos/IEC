"""
Count P&ID components in an SVG drawing using its LEGEND TABLES.

Works with SVGs exported from CAD where everything is plain paths (no block names,
text drawn as outlines). The script reads the SVG as VECTORS, not as a picture:

  1. Read every path in the SVG as straight line pieces (curves are flattened).
  2. Find the legend tables from their grid lines: a column of rows with a
     SYMBOL column on the left and a DESCRIPTION column on the right.
     No OCR and no "LEGEND" word are needed.
  3. For every legend row, find that symbol's geometry in the drawing at any
     size, rotation (0/90/180/270) or mirror.
  4. Keep one component per place; a bigger symbol wins over a smaller one drawn
     inside it (e.g. an auto shut-off valve over the plain valve inside it).
  5. Write the counts (screen + CSV) and a check image with every hit boxed.

Component names (in this order):
  --names "BALL VALVE,NEEDLE VALVE,..."   names in legend order (tables left->right,
                                           rows top->bottom), or
  Tesseract OCR, if installed, reads the DESCRIPTION cells, or
  real <text> in the SVG, if the exporter kept text, otherwise
  SYMBOL_1, SYMBOL_2 ... (the legend crops are saved in legend_symbols/ to look at)

Usage:
  python count_svg_legend.py drawing.svg
  python count_svg_legend.py drawing.svg --names "BALL VALVE,PRESSURE SAFETY VALVE,..."
  python count_svg_legend.py drawing.svg --exclude-box 0.69,0.70,1.0,1.0   (e.g. title block,
                                           fractions of width/height: left,top,right,bottom)
  python count_svg_legend.py drawing.svg --threshold 0.85                  (looser matching)

Requires: pip install svgelements numpy opencv-python pymupdf
Optional: pip install pytesseract  (+ Tesseract OCR program) to read the legend names
"""
import argparse
import csv
import math
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

try:
    import svgelements as se
except ImportError:
    sys.exit("Install svgelements:  python -m pip install svgelements")
try:
    import cv2
except ImportError:
    cv2 = None
try:
    import pymupdf
except ImportError:
    pymupdf = None
try:
    import pytesseract
    if not shutil.which("tesseract"):
        _win = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(_win):
            pytesseract.pytesseract.tesseract_cmd = _win
        else:
            pytesseract = None
except ImportError:
    pytesseract = None


# ====================================================================== reading the SVG
class Drawing:
    def __init__(self, path):
        svg = se.SVG.parse(path, reify=True)
        self.width = float(svg.width) if svg.width else 1.0
        self.height = float(svg.height) if svg.height else 1.0
        segs, stroked, frames, texts, fill_parts = [], [], [], [], []
        for el in svg.elements():
            if isinstance(el, se.Text):
                if el.text and el.text.strip():
                    # x/y are in the text's own units: map them like the paths (viewBox scale)
                    p = el.transform.point_in_matrix_space(se.Point(el.x, el.y))
                    texts.append({"text": " ".join(el.text.split()), "x": float(p.x), "y": float(p.y)})
                continue
            if not isinstance(el, se.Shape):
                continue
            try:
                p = se.Path(el)
                p.reify()
            except Exception:
                continue
            if el.values.get("visibility") == "hidden" or el.values.get("display") == "none":
                continue
            has_stroke = el.stroke is not None and el.stroke.value is not None and el.stroke.alpha != 0
            for sub in p.as_subpaths():
                pts_all = []
                closed = False
                first = len(segs)
                for s in sub:
                    if isinstance(s, se.Move):
                        continue
                    if isinstance(s, se.Close):
                        closed = True
                    if isinstance(s, (se.Line, se.Close)):
                        pts = [s.start, s.end]
                    else:
                        n = max(4, min(24, int(s.length(error=1e-2) / (self.width * 0.0008)) + 2))
                        pts = [s.point(t) for t in np.linspace(0, 1, n)]
                    pts = [(float(q.x), float(q.y)) for q in pts if q is not None]
                    for a, b in zip(pts, pts[1:]):
                        if a != b:
                            segs.append((a[0], a[1], b[0], b[1]))
                            stroked.append(has_stroke)
                    pts_all.extend(pts)
                if closed and len(pts_all) >= 4:
                    xs, ys = [q[0] for q in pts_all], [q[1] for q in pts_all]
                    frames.append((min(xs), min(ys), max(xs), max(ys)))
                if not has_stroke and len(pts_all) >= 3 and len(segs) > first:
                    xs, ys = [q[0] for q in pts_all], [q[1] for q in pts_all]
                    fill_parts.append(((min(xs), min(ys), max(xs), max(ys)), first, len(segs)))
        self.segs = np.array(segs, dtype=float).reshape(-1, 4)
        self.stroked = np.array(stroked, dtype=bool)
        self.frames = frames
        self.texts = texts
        self.fill_parts = fill_parts
        allp = np.concatenate([self.segs[:, :2], self.segs[:, 2:]]) if len(segs) else np.zeros((1, 2))
        self.box = (*allp.min(0), *allp.max(0))
        self.diag = math.hypot(self.box[2] - self.box[0], self.box[3] - self.box[1]) or 1.0

    def grid_lines(self, min_len):
        s = self.segs[self.stroked]
        dx, dy = s[:, 2] - s[:, 0], s[:, 3] - s[:, 1]
        eps = 1e-4 * self.diag
        hz = (np.abs(dy) < eps) & (np.abs(dx) >= min_len)
        vt = (np.abs(dx) < eps) & (np.abs(dy) >= min_len)
        H = [(r[1], min(r[0], r[2]), max(r[0], r[2])) for r in s[hz]]
        V = [(r[0], min(r[1], r[3]), max(r[1], r[3])) for r in s[vt]]
        return H, V


# ====================================================================== words (letters drawn as shapes)
def group_words(dw):
    """Group filled letter shapes into words: same line, small gaps between letters."""
    parts = sorted(range(len(dw.fill_parts)), key=lambda i: dw.fill_parts[i][0][0])
    parent = list(range(len(dw.fill_parts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    boxes = [fp[0] for fp in dw.fill_parts]
    heights = sorted(b[3] - b[1] for b in boxes)
    letter = heights[len(heights) // 2] if heights else 1.0      # typical letter height
    for ii, i in enumerate(parts):
        a = boxes[i]
        ha = a[3] - a[1]
        for j in parts[ii + 1:]:
            b = boxes[j]
            if b[0] > a[2] + 0.6 * max(ha, b[3] - b[1]):
                break
            hb = b[3] - b[1]
            if max(ha, hb) > 4 * letter:
                continue                              # a filled bar / big shape, not a letter
            ov = min(a[3], b[3]) - max(a[1], b[1])
            same_size = max(ha, hb) < 3 * max(min(ha, hb), 1e-9)
            # small marks on the text line (hyphen, dot) belong to the word: PG-01 is one word
            small_on_line = (hb < ha and a[1] <= (b[1] + b[3]) / 2 <= a[3]) or \
                            (ha < hb and b[1] <= (a[1] + a[3]) / 2 <= b[3])
            if ov > 0.5 * min(ha, hb) and (same_size or small_on_line):
                parent[find(j)] = find(i)
    groups = defaultdict(list)
    for i in range(len(boxes)):
        groups[find(i)].append(i)
    words = []
    for members in groups.values():
        segs = np.concatenate([dw.segs[dw.fill_parts[m][1]:dw.fill_parts[m][2]] for m in members])
        bx = np.array([boxes[m] for m in members])
        words.append({"box": (bx[:, 0].min(), bx[:, 1].min(), bx[:, 2].max(), bx[:, 3].max()),
                      "sig": glyph_points(segs), "n": len(members)})
    return words


# ====================================================================== legend tables
def find_legend_tables(dw):
    """Tables = >=4 data rows of equal width, a full-height left/right border and an
    inner divider that splits a narrow SYMBOL column from a wide DESCRIPTION column."""
    H, V = dw.grid_lines(dw.diag * 0.004)
    tol = dw.diag * 0.002
    spans = defaultdict(list)                     # (x0, x1) -> [y, ...]
    for y, x0, x1 in H:
        key = (round(x0 / tol), round(x1 / tol))
        spans[key].append((y, x0, x1))
    tables = []
    for key, lines in spans.items():
        if len(lines) < 5:
            continue
        x0 = float(np.median([l[1] for l in lines]))
        x1 = float(np.median([l[2] for l in lines]))
        width = x1 - x0
        ys = sorted({round(l[0] / tol) * tol for l in lines})
        # inner dividers: vertical lines strictly inside, spanning several rows. They must lie
        # within this table's own rows: a long line elsewhere on the sheet in the same x range
        # (e.g. a vessel wall) would otherwise win as "the longest divider".
        divs = [v for v in V if x0 + 0.05 * width < v[0] < x0 + 0.5 * width
                and ys[0] - tol <= v[1] and v[2] <= ys[-1] + tol
                and v[2] - v[1] > 2.5 * min(np.diff(ys)) if len(ys) > 1]
        if not divs:
            continue
        d = max(divs, key=lambda v: v[2] - v[1])
        rows_y = [y for y in ys if d[1] - tol <= y <= d[2] + tol]
        if len(rows_y) < 5:
            continue
        # the top row inside the divider is the header (SYMBOLS | DESCRIPTION)
        bands = list(zip(rows_y[1:], rows_y[2:]))
        if len(bands) < 3:
            continue
        hgt = np.median([b - a for a, b in bands])
        if any((b - a) > 3 * hgt for a, b in bands):
            continue
        tables.append({"x0": x0, "x1": x1, "xd": d[0], "y0": min(ys), "y1": max(ys),
                       "bands": bands})
    tables.sort(key=lambda t: (round(t["y0"] / (dw.diag * 0.05)), t["x0"]))
    return tables


def render(svg_path, width_px):
    """Render the SVG to a grey image (for OCR of names and the check image)."""
    if pymupdf is None or cv2 is None:
        return None
    root = ET.parse(svg_path).getroot()
    rules = {}
    for st in root.iter():
        if st.tag.endswith("style") and st.text:
            for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", st.text):
                props = {k.strip(): v.strip() for k, v in
                         (p.split(":", 1) for p in body.split(";") if ":" in p)}
                for s in sel.split(","):
                    if s.strip().startswith("."):
                        rules.setdefault(s.strip()[1:], {}).update(props)
    for e in root.iter():
        for cls in (e.get("class") or "").split():
            for k, v in rules.get(cls, {}).items():
                if e.get(k) is None and v:
                    e.set(k, "0" if (k == "stroke-width" and v == "none") else v)
    doc = pymupdf.open(stream=ET.tostring(root), filetype="svg")
    page = doc[0]
    z = width_px / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if pix.n == 3 else img[:, :, :3].copy()


def ocr_cell(img, dw, cell):
    if pytesseract is None or img is None:
        return None
    sx, sy = img.shape[1] / dw.width, img.shape[0] / dw.height
    x0, y0, x1, y1 = cell
    crop = img[int(y0 * sy) + 2:int(y1 * sy) - 2, int(x0 * sx) + 2:int(x1 * sx) - 2]
    if crop.size == 0:
        return None
    crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    t = pytesseract.image_to_string(crop, config="--psm 6")
    t = " ".join(t.split())
    t = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", t))      # "(MANUAL )" -> "(MANUAL)"
    return t or None


# ====================================================================== shape matching
ORIENTS = [(k, m) for k in range(4) for m in (False, True)]


def orient_matrix(k, mirror):
    c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][k]
    R = np.array([[c, -s], [s, c]], dtype=float)
    return R @ np.array([[-1, 0], [0, 1]], dtype=float) if mirror else R


class SegIndex:
    def __init__(self, segs, cell):
        self.s, self.cell, self.grid = segs, cell, defaultdict(list)
        for i, (x0, y0, x1, y1) in enumerate(segs):
            for gx in range(int(min(x0, x1) // cell), int(max(x0, x1) // cell) + 1):
                for gy in range(int(min(y0, y1) // cell), int(max(y0, y1) // cell) + 1):
                    self.grid[(gx, gy)].append(i)

    def _cand(self, x0, y0, x1, y1):
        idx = set()
        for gx in range(int(x0 // self.cell), int(x1 // self.cell) + 1):
            for gy in range(int(y0 // self.cell), int(y1 // self.cell) + 1):
                idx.update(self.grid.get((gx, gy), ()))
        return list(idx)

    def near(self, pts, tol):
        idx = self._cand(pts[:, 0].min() - tol, pts[:, 1].min() - tol,
                         pts[:, 0].max() + tol, pts[:, 1].max() + tol)
        if not idx:
            return np.zeros(len(pts), dtype=bool)
        return dist_to_segs(pts, self.s[idx]) <= tol

    def inside(self, box, grow=0.05):
        x0, y0, x1, y1 = box
        g = max(x1 - x0, y1 - y0) * grow
        x0, y0, x1, y1 = x0 - g, y0 - g, x1 + g, y1 + g
        idx = self._cand(x0, y0, x1, y1)
        if not idx:
            return np.zeros((0, 4))
        S = self.s[idx]
        m = ((np.minimum(S[:, 0], S[:, 2]) >= x0) & (np.maximum(S[:, 0], S[:, 2]) <= x1) &
             (np.minimum(S[:, 1], S[:, 3]) >= y0) & (np.maximum(S[:, 1], S[:, 3]) <= y1))
        return S[m]


def dist_to_segs(P, S):
    A, B = S[:, :2], S[:, 2:]
    AB = B - A
    L2 = (AB ** 2).sum(1)
    L2[L2 == 0] = 1e-12
    t = np.clip(((P[:, None, :] - A) * AB).sum(2) / L2, 0, 1)
    return np.sqrt(((P[:, None, :] - (A + t[..., None] * AB)) ** 2).sum(2)).min(1)


def in_cell(segs, cell):
    x0, y0, x1, y1 = cell
    return ((np.minimum(segs[:, 0], segs[:, 2]) > x0) & (np.maximum(segs[:, 0], segs[:, 2]) < x1) &
            (np.minimum(segs[:, 1], segs[:, 3]) > y0) & (np.maximum(segs[:, 1], segs[:, 3]) < y1))


def glyph_points(segs):
    """Letters drawn as filled outlines -> points normalised to the letters' own box,
    so 'PG' in a big bubble and 'PG' in a small legend bubble compare equal."""
    if len(segs) == 0:
        return None
    f = np.linspace(0, 1, 4)
    P = (segs[:, None, :2] + f[None, :, None] * (segs[:, None, 2:] - segs[:, None, :2])).reshape(-1, 2)
    lo, hi = P.min(0), P.max(0)
    size = float((hi - lo).max())
    if size <= 0:
        return None
    return (P - lo) / size


def glyph_distance(A, B):
    """Symmetric mean nearest-point distance between two normalised point sets."""
    if A is None or B is None:
        return 1.0
    if len(A) > 600:
        A = A[np.linspace(0, len(A) - 1, 600).astype(int)]
    if len(B) > 600:
        B = B[np.linspace(0, len(B) - 1, 600).astype(int)]
    d = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(2))
    return float((d.min(1).mean() + d.min(0).mean()) / 2)


def word_distance(A, B):
    """Worst-point distance between two normalised code words. Unlike the mean, one
    different letter is enough to reject: PG vs TG share the G, so their MEAN distance
    is small, but around the P/T it is large."""
    if A is None or B is None:
        return 1.0
    if len(A) > 600:
        A = A[np.linspace(0, len(A) - 1, 600).astype(int)]
    if len(B) > 600:
        B = B[np.linspace(0, len(B) - 1, 600).astype(int)]
    d = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(2))
    return float(max(d.min(1).max(), d.min(0).max()))


def make_template(stroke_segs, fill_segs, cell, n_fill_parts=0):
    T = stroke_segs[in_cell(stroke_segs, cell)]
    G = fill_segs[in_cell(fill_segs, cell)]
    glyphs, solid, fillmark = None, False, None
    if len(T) < 3:                      # symbol drawn only as a filled shape: use its outline
        T, G, solid = np.concatenate([T, G]), G[:0], True
    elif len(G) and n_fill_parts >= 2:
        glyphs = glyph_points(G)         # letters inside the symbol (PG, TG, PT ...)
    elif len(G):
        fillmark = G                     # a filled part of the symbol (dot, flag): must be there too
    if len(T) < 3:
        return None
    pts = np.concatenate([T[:, :2], T[:, 2:]])
    c = (pts.min(0) + pts.max(0)) / 2
    T = T - np.concatenate([c, c])
    fill_samples = None
    if fillmark is not None:
        f = np.linspace(0, 1, 4)
        F = fillmark - np.concatenate([c, c])
        fill_samples = (F[:, None, :2] + f[None, :, None] * (F[:, None, 2:] - F[:, None, :2])).reshape(-1, 2)
    span = np.ptp(pts, axis=0)
    size = float(span.max())
    if size <= 0:
        return None
    lens = np.hypot(T[:, 2] - T[:, 0], T[:, 3] - T[:, 1])
    step = size / 40
    samples, sid = [], []
    for k, ((ax, ay, bx, by), L) in enumerate(zip(T, lens)):
        n = max(1, int(L / step))
        for i in range(n + 1):
            f = i / n
            samples.append((ax + (bx - ax) * f, ay + (by - ay) * f))
            sid.append(k)
    order = np.argsort(-lens)
    anchors, dirs = [], []
    for i in order:
        if lens[i] < 0.15 * size:
            break
        d = np.array([T[i, 2] - T[i, 0], T[i, 3] - T[i, 1]]) / lens[i]
        if all(abs(np.dot(d, q)) < 0.98 for q in dirs) or len(anchors) < 2:
            anchors.append(i)
            dirs.append(d)
        if len(anchors) == 4:
            break
    samples = np.array(samples)
    rng = np.random.default_rng(0)
    quick = samples[rng.choice(len(samples), size=min(12, len(samples)), replace=False)]
    # hatched symbol: many parallel lines (e.g. a filter drawn solid / cross-hatched)
    ang = np.round(np.degrees(np.arctan2(T[:, 3] - T[:, 1], T[:, 2] - T[:, 0])) % 180 / 5)
    hatched = bool(len(T) >= 8 and Counter(ang).most_common(1)[0][1] >= 6
                   and Counter(ang).most_common(1)[0][1] >= 0.4 * len(T))
    return {"segs": T, "size": size, "minside": float(max(span.min(), size * 0.15)), "hatched": hatched,
            "total": float(lens.sum()), "samples": samples, "sid": np.array(sid),
            "quick": quick, "anchors": anchors, "glyphs": glyphs, "solid": solid,
            "fill_samples": fill_samples}


def explained(segs, tsegs, tol, per_seg=6):
    f = np.linspace(0, 1, per_seg)
    P = (segs[:, None, :2] + f[None, :, None] * (segs[:, None, 2:] - segs[:, None, :2])).reshape(-1, 2)
    w = np.repeat(np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]), per_seg)
    return float((w * (dist_to_segs(P, tsegs) <= tol)).sum() / (w.sum() or 1.0))


def match_template(tpl, dsegs, dlen, ddir, index, threshold, max_size, max_tol, fill_index,
                   min_precision=0.8, glyph_tol=0.07, anchors=None):
    found, T = [], tpl["segs"]
    for ai in (tpl["anchors"] if anchors is None else anchors):
        a0, a1 = T[ai, :2], T[ai, 2:]
        va = a1 - a0
        la = float(np.hypot(*va))
        for k, mir in ORIENTS:
            R = orient_matrix(k, mir)
            u = R @ va / la
            cross = np.abs(ddir[:, 0] * u[1] - ddir[:, 1] * u[0])
            scale = dlen / la
            cand = np.where((cross < 0.035) & (scale > 0.3) & (scale < 8)
                            & (scale * tpl["size"] <= max_size))[0]
            for j in cand:
                s = scale[j]
                start = dsegs[j, :2] if np.dot(ddir[j], u) > 0 else dsegs[j, 2:]
                t = start - s * (R @ a0)
                tol = max(min(0.05 * tpl["size"] * s, 0.12 * tpl["minside"] * s, max_tol), 1e-9)
                if index.near((tpl["quick"] @ R.T) * s + t, tol).mean() < 0.75:
                    continue
                P = (tpl["samples"] @ R.T) * s + t
                hit = index.near(P, tol)
                per_seg = np.bincount(tpl["sid"], weights=hit) / np.bincount(tpl["sid"])
                recall = min(float(hit.mean()), float((per_seg >= 0.7).mean()))
                if recall < threshold:
                    continue
                box = (P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max())
                if tpl["solid"]:
                    # legend shows a solid block: the drawing must be solid or hatched inside
                    w_, h_ = box[2] - box[0], box[3] - box[1]
                    core = (box[0] + 0.15 * w_, box[1] + 0.15 * h_, box[2] - 0.15 * w_, box[3] - 0.15 * h_)
                    hatch = index.inside(core, grow=0.0)
                    hl = np.hypot(hatch[:, 2] - hatch[:, 0], hatch[:, 3] - hatch[:, 1]).sum()
                    filled = len(fill_index.inside(box, grow=0.02))
                    if hl < 1.5 * (w_ + h_) and filled < 4:
                        continue
                    found.append({"recall": recall, "box": box, "scale": float(s), "glyph": None,
                                  "weight": float(recall * tpl["total"] * s), "tol": tol,
                                  "TS": np.concatenate([(T[:, :2] @ R.T) * s + t, (T[:, 2:] @ R.T) * s + t], 1)})
                    continue
                inner = index.inside(box)
                if len(inner):
                    TS = np.concatenate([(T[:, :2] @ R.T) * s + t, (T[:, 2:] @ R.T) * s + t], 1)
                    if explained(inner, TS, tol) < min_precision:
                        continue
                gd = None
                extra = 0.0
                if tpl["fill_samples"] is not None:
                    FP = (tpl["fill_samples"] @ R.T) * s + t
                    if fill_index.near(FP, tol * 1.5).mean() < 0.7:
                        continue                  # the filled dot / flag is missing: other symbol
                    extra = 0.5 * tpl["total"] * s
                if tpl["glyphs"] is not None:
                    G = fill_index.inside(box, grow=0.0)
                    gd = glyph_distance(tpl["glyphs"], glyph_points(G))
                    if gd > glyph_tol:
                        continue                  # same outline, different letters (PG vs TG)
                found.append({"recall": recall, "box": box, "scale": float(s), "glyph": gd,
                              "weight": float(recall * tpl["total"] * s + extra), "tol": tol,
                              "TS": np.concatenate([(T[:, :2] @ R.T) * s + t, (T[:, 2:] @ R.T) * s + t], 1)})
    return found


# ---- parallel matching: each (legend row, anchor) pair is an independent job. Every
# worker process builds the segment indexes once, then matches the jobs it is given.
_worker = {}


def _init_worker(dsegs, dlen, ddir, fill_segs, cell):
    _worker.update(dsegs=dsegs, dlen=dlen, ddir=ddir,
                   index=SegIndex(dsegs, cell), fill_index=SegIndex(fill_segs, cell))


def _match_job(job):
    tpl, anchor, kw = job
    w = _worker
    return match_template(tpl, w["dsegs"], w["dlen"], w["ddir"], w["index"],
                          fill_index=w["fill_index"], anchors=[anchor], **kw)


def match_all(jobs, dsegs, dlen, ddir, fill_segs, cell, workers):
    """Run match jobs, in parallel when workers > 1. Results come back in job order,
    so the outcome is identical to matching one row after another."""
    if workers > 1 and len(jobs) > 1:
        try:
            with ProcessPoolExecutor(max_workers=min(workers, len(jobs)), initializer=_init_worker,
                                     initargs=(dsegs, dlen, ddir, fill_segs, cell)) as ex:
                return list(ex.map(_match_job, jobs))
        except Exception as err:                 # no process pool here: fall back to serial
            print(f"(parallel matching unavailable: {err} - running serially)")
    _init_worker(dsegs, dlen, ddir, fill_segs, cell)
    return [_match_job(j) for j in jobs]


def overlap(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1e-12
    return ix * iy / small


def resolve(dets):
    dets.sort(key=lambda d: (-d["weight"], -d["recall"]))
    kept = []
    for d in dets:
        if all(overlap(d["box"], k["box"]) < 0.5 for k in kept):
            kept.append(d)
    return kept


def area(b):
    return max((b[2] - b[0]) * (b[3] - b[1]), 1e-12)


def explained_len(index, d, box):
    inner = index.inside(box)
    if not len(inner):
        return 0.0
    total = np.hypot(inner[:, 2] - inner[:, 0], inner[:, 3] - inner[:, 1]).sum()
    return explained(inner, d["TS"], d["tol"]) * total


def prefer_bigger(strong, weak, index):
    """A weaker match of a BIGGER symbol that covers a strong match and explains clearly
    more of the drawn lines there wins (valve + actuator = auto shut-off valve)."""
    out = []
    used = set()
    for d in strong:
        best = None
        for k, w in enumerate(weak):
            if k in used or w["row"] is d["row"]:
                continue
            if overlap(d["box"], w["box"]) < 0.8 or area(w["box"]) < 1.5 * area(d["box"]):
                continue
            # symbols on one sheet are drawn at about the same scale as their legend: a
            # "bigger symbol" blown up 5x around a small valve is a chance fit to the piping
            if not 0.5 <= w["scale"] / d["scale"] <= 2.0:
                continue
            # the bigger symbol must contain the smaller one's shape (ASV contains a valve body)
            if explained(d["TS"], w["TS"], w["tol"] * 1.5) < 0.6:
                continue
            if w["row"]["tpl"].get("hatched"):
                continue                     # a hatch "explains" anything it covers
            ew, ed = explained_len(index, w, w["box"]), explained_len(index, d, w["box"])
            if ew >= 1.05 * ed and (best is None or ew > best[0]):
                best = (ew, k)
        if best:
            used.add(best[1])
            out.append(weak[best[1]])
        else:
            out.append(d)
    return out


def drop_slices(dets):
    """3+ equal matches stacked edge to edge are slices of one long object, not symbols."""
    by_row = defaultdict(list)
    for i, d in enumerate(dets):
        by_row[id(d["row"])].append(i)
    bad = set()
    for idxs in by_row.values():
        parent = {i: i for i in idxs}

        def find(i):
            while parent[i] != i:
                i = parent[i]
            return i
        for a_ in idxs:
            for b_ in idxs:
                if a_ < b_:
                    A, B = dets[a_]["box"], dets[b_]["box"]
                    gap = 0.25 * max(A[2] - A[0], A[3] - A[1])
                    same_col = abs(A[0] - B[0]) < gap and abs(A[2] - B[2]) < gap
                    same_row = abs(A[1] - B[1]) < gap and abs(A[3] - B[3]) < gap
                    near = (A[0] - gap <= B[2] and B[0] - gap <= A[2] and
                            A[1] - gap <= B[3] and B[1] - gap <= A[3])
                    if near and (same_col or same_row):
                        parent[find(a_)] = find(b_)
        groups = defaultdict(list)
        for i in idxs:
            groups[find(i)].append(i)
        for g in groups.values():
            if len(g) >= 3:
                bad.update(g)
    return [d for i, d in enumerate(dets) if i not in bad], len(bad)


def enclosed(d, index):
    """Lines that are not part of the symbol close it in on all 4 sides (often dashed):
    the symbol is drawn inside a bigger one (e.g. a valve inside a load-cell box)."""
    x0, y0, x1, y1 = d["box"]
    w, h = x1 - x0, y1 - y0
    ring = index.inside((x0 - 0.7 * w, y0 - 0.7 * h, x1 + 0.7 * w, y1 + 0.7 * h), grow=0.0)
    if not len(ring):
        return False
    mids = (ring[:, :2] + ring[:, 2:]) / 2
    own = dist_to_segs(mids, d["TS"]) <= d["tol"] * 1.5
    ring = ring[~own]
    dx, dy = ring[:, 2] - ring[:, 0], ring[:, 3] - ring[:, 1]
    hz, vt = np.abs(dy) < 0.05 * np.abs(dx) + 1e-9, np.abs(dx) < 0.05 * np.abs(dy) + 1e-9

    def cover(sel, lo, hi, a0, a1, axis):
        if not sel.any():
            return 0.0
        segs = ring[sel]
        pos = (segs[:, 1] + segs[:, 3]) / 2 if axis == "h" else (segs[:, 0] + segs[:, 2]) / 2
        segs = segs[(pos >= lo) & (pos <= hi)]
        if not len(segs):
            return 0.0
        if axis == "h":
            iv = np.sort(np.stack([np.minimum(segs[:, 0], segs[:, 2]), np.maximum(segs[:, 0], segs[:, 2])], 1), 0)
        else:
            iv = np.sort(np.stack([np.minimum(segs[:, 1], segs[:, 3]), np.maximum(segs[:, 1], segs[:, 3])], 1), 0)
        covered = sum(max(0.0, min(b, a1) - max(a, a0)) for a, b in iv)
        return covered / max(a1 - a0, 1e-9)

    sides = [cover(hz, y0 - 0.6 * h, y0 + 0.35 * h, x0, x1, "h"),
             cover(hz, y1 - 0.35 * h, y1 + 0.6 * h, x0, x1, "h"),
             cover(vt, x0 - 0.6 * w, x0 + 0.35 * w, y0, y1, "v"),
             cover(vt, x1 - 0.35 * w, x1 + 0.6 * w, y0, y1, "v")]
    return min(sides) >= 0.4


def inside_any(x, y, boxes):
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes)


# ====================================================================== main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("svg")
    ap.add_argument("--names", help="legend names in order, comma separated")
    ap.add_argument("--threshold", type=float, default=0.88,
                    help="share of the legend symbol that must be found (default 0.88)")
    ap.add_argument("--exclude-box", action="append", default=[],
                    help="area to ignore, fractions left,top,right,bottom (can repeat)")
    ap.add_argument("--max-symbol", type=float, default=0.25,
                    help="largest symbol as a share of the drawing diagonal (default 0.25)")
    ap.add_argument("--word-tol", type=float, default=0.06,
                    help="largest allowed letter difference between a code word and the legend's "
                         "letters, as a share of the word size (default 0.06)")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1,
                    help="processes for shape matching (default: all CPU cores, 1 = no parallelism)")
    ap.add_argument("--out", default="component_counts_svg.csv")
    ap.add_argument("--check-image", default="svg_check.png")
    a = ap.parse_args()

    dw = Drawing(a.svg)
    tables = find_legend_tables(dw)
    if not tables:
        sys.exit("No legend table found (a SYMBOL column + DESCRIPTION column with grid lines).")
    img = render(a.svg, 5000)

    rows = []
    for ti, t in enumerate(tables):
        for ri, (ya, yb) in enumerate(t["bands"]):
            m = min(t["xd"] - t["x0"], yb - ya) * 0.04
            rows.append({"table": ti + 1, "row": ri + 1,
                         "sym": (t["x0"] + m, ya + m, t["xd"] - m, yb - m),
                         "desc": (t["xd"] + m, ya + m, t["x1"] - m, yb - m)})
    names = [n.strip() for n in a.names.split(",")] if a.names else []
    os.makedirs("legend_symbols", exist_ok=True)
    for i, r in enumerate(rows):
        svg_text = [tt["text"] for tt in dw.texts if r["desc"][0] < tt["x"] < r["desc"][2]
                    and r["desc"][1] < tt["y"] < r["desc"][3]]
        r["name"] = (names[i] if i < len(names) else
                     (" ".join(svg_text) if svg_text else None) or ocr_cell(img, dw, r["desc"])
                     or f"SYMBOL_{i + 1}")
        if img is not None:
            sx, sy = img.shape[1] / dw.width, img.shape[0] / dw.height
            x0, y0, x1, y1 = r["desc"][0] - (r["desc"][0] - r["sym"][0]), r["sym"][1], r["desc"][2], r["sym"][3]
            crop = img[int(y0 * sy):int(y1 * sy), int(x0 * sx):int(x1 * sx)]
            if crop.size:
                cv2.imwrite(os.path.join("legend_symbols", f"{i + 1:02d}.png"), crop)

    # areas never counted: the legend tables and any --exclude-box
    W, Hh = dw.width, dw.height
    excl = [(t["x0"], t["y0"], t["x1"], t["y1"]) for t in tables]
    for e in a.exclude_box:
        f = [float(v) for v in e.split(",")]
        excl.append((f[0] * W, f[1] * Hh, f[2] * W, f[3] * Hh))

    s = dw.segs
    mx, my = (s[:, 0] + s[:, 2]) / 2, (s[:, 1] + s[:, 3]) / 2
    outside = np.array([not inside_any(x, y, excl) for x, y in zip(mx, my)], dtype=bool)
    stroke_all, fill_all = s[dw.stroked], s[~dw.stroked]
    fill_segs = s[outside & ~dw.stroked]
    fill_index = SegIndex(fill_segs, cell=dw.diag / 300)
    dsegs = s[outside & dw.stroked]
    dlen = np.hypot(dsegs[:, 2] - dsegs[:, 0], dsegs[:, 3] - dsegs[:, 1])
    ok = dlen > 0
    dsegs, dlen = dsegs[ok], dlen[ok]
    ddir = (dsegs[:, 2:] - dsegs[:, :2]) / dlen[:, None]
    index = SegIndex(dsegs, cell=dw.diag / 300)

    words = [w for w in group_words(dw)
             if not inside_any((w["box"][0] + w["box"][2]) / 2, (w["box"][1] + w["box"][3]) / 2, excl)]
    dets, word_hits, jobs, job_rows = [], {}, [], []
    for r in rows:
        nparts = sum(1 for fp in dw.fill_parts
                     if r["sym"][0] < fp[0][0] and fp[0][2] < r["sym"][2]
                     and r["sym"][1] < fp[0][1] and fp[0][3] < r["sym"][3])
        r["tpl"] = make_template(stroke_all, fill_all, r["sym"], nparts)
        if r["tpl"] is None:
            continue
        if r["tpl"]["glyphs"] is not None:
            # a symbol that carries a code (PG, PS, PT ...): count that code word in the drawing
            hits = [w for w in words if word_distance(r["tpl"]["glyphs"], w["sig"]) <= a.word_tol]
            word_hits[id(r)] = hits
            continue
        kw = dict(threshold=min(a.threshold, 0.65), max_size=dw.diag * a.max_symbol,
                  max_tol=dw.diag * 0.0012)
        for anchor in r["tpl"]["anchors"]:
            jobs.append((r["tpl"], anchor, kw))
            job_rows.append(r)
    for r, found in zip(job_rows, match_all(jobs, dsegs, dlen, ddir, fill_segs,
                                             dw.diag / 300, a.workers)):
        for d in found:
            d["row"] = r
            dets.append(d)

    def nested(d):
        x0, y0, x1, y1 = d["box"]
        cx, cy, area = (x0 + x1) / 2, (y0 + y1) / 2, max((x1 - x0) * (y1 - y0), 1e-12)
        return any(f[0] < cx < f[2] and f[1] < cy < f[3]
                   and 1.2 * area <= (f[2] - f[0]) * (f[3] - f[1]) <= 4 * area for f in dw.frames)

    # per symbol first: one hit per place, and drop "slices" of long objects (3+ in a row)
    strong, slice_boxes = [], []
    for r in rows:
        mine = resolve([d for d in dets if d["row"] is r and d["recall"] >= a.threshold])
        kept, _ = drop_slices(mine)
        slice_boxes += [d["box"] for d in mine if not any(d is k for k in kept)]
        strong += kept
    not_slice = lambda d: all(overlap(d["box"], b) < 0.5 for b in slice_boxes)
    strong = [d for d in strong if not_slice(d)]
    weak = [d for d in dets if d["recall"] < a.threshold and not_slice(d)]
    final = resolve(prefer_bigger(resolve(strong), weak, index))
    inner = [d for d in final if nested(d) or enclosed(d, index)]
    nested_n = Counter(d["row"]["name"] for d in inner)
    final = [d for d in final if not any(d is x for x in inner)]
    counts = Counter(id(d["row"]) for d in final)
    for rid, hits in word_hits.items():
        counts[rid] = len(hits)

    print(f"Legend: {len(tables)} table(s), {len(rows)} symbols"
          f"   |  names from: {'--names' if names else ('SVG text' if dw.texts else ('OCR' if pytesseract else 'not available - use --names'))}\n")
    print(f"{'#':>3}  {'Component':40} {'Count':>5}")
    print("-" * 52)
    out_rows = []
    for i, r in enumerate(rows):
        n = counts.get(id(r), 0)
        note = "" if r["tpl"] is not None else "   (legend symbol not readable)"
        print(f"{i + 1:>3}  {r['name'][:40]:40} {n:>5}{note}")
        out_rows.append([i + 1, r["name"], n])
    print("-" * 52)
    print(f"{'':3}  {'TOTAL':40} {sum(counts.values()):>5}")
    if nested_n:
        print("\nNot counted - found inside a larger symbol's frame (part of that symbol):")
        for k, n in nested_n.items():
            print(f"     {k:40} {n:>5}")

    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["legend_row", "component", "count"])
        w.writerows(out_rows)
    print(f"\nSaved: {a.out}")

    if img is not None:
        sx, sy = img.shape[1] / dw.width, img.shape[0] / dw.height
        for e in excl:
            cv2.rectangle(img, (int(e[0] * sx), int(e[1] * sy)), (int(e[2] * sx), int(e[3] * sy)),
                          (200, 120, 0), 2)
        for d in final:
            x0, y0, x1, y1 = d["box"]
            p = 4
            cv2.rectangle(img, (int(x0 * sx) - p, int(y0 * sy) - p), (int(x1 * sx) + p, int(y1 * sy) + p),
                          (0, 0, 230), 2)
            cv2.putText(img, str(rows.index(d["row"]) + 1), (int(x0 * sx) - p, int(y0 * sy) - p - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 230), 2)
        for r in rows:
            for w in word_hits.get(id(r), []):
                x0, y0, x1, y1 = w["box"]
                p = 6
                cv2.rectangle(img, (int(x0 * sx) - p, int(y0 * sy) - p), (int(x1 * sx) + p, int(y1 * sy) + p),
                              (0, 140, 0), 2)
                cv2.putText(img, str(rows.index(r) + 1), (int(x0 * sx) - p, int(y0 * sy) - p - 3),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 0), 2)
        cv2.imwrite(a.check_image, img)
        print(f"Saved: {a.check_image}  (red = symbol found by shape, green = found by its code letters, blue = ignored areas)")
        print("       legend_symbols/NN.png shows legend row NN")


if __name__ == "__main__":
    main()
