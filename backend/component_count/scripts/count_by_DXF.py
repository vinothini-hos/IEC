"""
Count P&ID components in a DXF/DWG whose symbols are drawn as PLAIN LINES (not blocks),
using the drawing's LEGEND TABLES (columns "SYMBOLS" | "DESCRIPTION").

How it counts each legend row:
  1. BLOCK  - if the legend symbol is a block, count that block outside the legend (exact).
  2. LABEL  - if the component has a short code (PG, PS, PSV, PRV ...), count that text
              outside the legend (exact). The code is the text inside the legend symbol
              (e.g. "PG" in the gauge circle) or the initials of the description
              ("PRESSURE SAFETY VALVE" -> PSV).
  3. SHAPE  - otherwise, find the legend symbol's line geometry in the drawing, at any
              scale, rotation (0/90/180/270) or mirror (vector matching, not pictures).

Outputs:
  - table printed on screen + CSV (component_counts.csv)
  - <drawing>_check.dxf : a copy of the drawing with every counted item boxed
      red = found by shape, blue = found by label, green = found by block
    open it in DWG TrueView / AutoCAD to verify the counts.

Usage:
  python count_exploded_dxf.py samnam_pid.dxf
  python count_exploded_dxf.py samnam_pid.dxf --threshold 0.85     (looser shape matching)
  python count_exploded_dxf.py drawing.dwg                          (needs ODA File Converter)

Requires: pip install ezdxf numpy
"""
import argparse
import csv
import glob
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import ezdxf
from ezdxf import bbox, path as ezpath

HEADER_SYMBOL = ("SYMBOLS", "SYMBOL")
HEADER_DESC = ("DESCRIPTION", "DESCRIPTIONS")


# ============================================================== loading
def load(fname):
    if fname.lower().endswith(".dwg"):
        from ezdxf.addons import odafc
        if sys.platform.startswith("win"):
            for root in (r"C:\Program Files\ODA", r"C:\Program Files (x86)\ODA"):
                hits = sorted(glob.glob(root + r"\ODAFileConverter*\ODAFileConverter.exe"))
                if hits:
                    ezdxf.options.set("odafc-addon", "win_exec_path", hits[-1])
                    break
        if not odafc.is_installed():
            sys.exit("DWG file: install ODA File Converter, or save the drawing as DXF first.")
        return odafc.readfile(fname)
    return ezdxf.readfile(fname)


def text_of(e):
    t = e.dxftype()
    if t == "MTEXT":
        return " ".join(e.plain_text().split())
    if t in ("TEXT", "ATTRIB"):
        return " ".join(e.dxf.text.split())
    return ""


# ============================================================== geometry
class Drawing:
    """All geometry as straight 2-D segments + all texts, with the source of each."""

    def __init__(self, doc):
        self.doc = doc
        msp = doc.modelspace()
        ext = bbox.extents(msp, fast=True)
        self.ext = ext
        self.diag = math.hypot(ext.size.x, ext.size.y) or 1.0
        self.flat = self.diag * 1e-4                     # arc flattening accuracy
        sheet_area = ext.size.x * ext.size.y or 1.0
        segs, seg_src, texts, inserts, frames = [], [], [], [], []

        def add_entity(e, src):
            t = e.dxftype()
            if t in ("TEXT", "MTEXT", "ATTRIB"):
                s = text_of(e)
                if s:
                    p = e.dxf.insert
                    texts.append({"text": s, "x": p.x, "y": p.y,
                                  "h": e.dxf.get("char_height" if t == "MTEXT" else "height", 1.0)})
                return
            if t == "INSERT":
                b = bbox.extents([e], fast=True)
                if b.has_data and b.size.x * b.size.y > 0.2 * sheet_area:
                    return                                # sheet border / title frame
                inserts.append({"name": e.dxf.name, "x": e.dxf.insert.x, "y": e.dxf.insert.y,
                                "box": b, "src": src})
                try:
                    for v in e.virtual_entities():
                        add_entity(v, src if src is not None else len(inserts) - 1)
                except Exception:
                    pass
                for a in e.attribs:
                    add_entity(a, src)
                return
            if t in ("LWPOLYLINE", "POLYLINE") and getattr(e, "closed", False):
                fb = bbox.extents([e], fast=True)
                if fb.has_data:
                    frames.append((fb.extmin.x, fb.extmin.y, fb.extmax.x, fb.extmax.y))
            try:
                if t == "HATCH":
                    paths = list(ezpath.from_hatch(e))
                else:
                    paths = [ezpath.make_path(e)]
            except Exception:
                return
            for p in paths:
                try:
                    pts = [(v.x, v.y) for v in p.flattening(self.flat)]
                except Exception:
                    continue
                for a, b2 in zip(pts, pts[1:]):
                    if a != b2:
                        segs.append((a[0], a[1], b2[0], b2[1]))
                        seg_src.append(e.dxf.get("layer", "0"))

        for e in msp:
            add_entity(e, None)
        self.segs = np.array(segs, dtype=float).reshape(-1, 4)
        self.seg_layer = seg_src
        self.texts = texts
        self.inserts = inserts
        self.frames = frames

    # axis-aligned long segments (for table grids)
    def grid_lines(self, min_len):
        s = self.segs
        dx, dy = s[:, 2] - s[:, 0], s[:, 3] - s[:, 1]
        hz = (np.abs(dy) < 1e-6 * self.diag) & (np.abs(dx) >= min_len)
        vt = (np.abs(dx) < 1e-6 * self.diag) & (np.abs(dy) >= min_len)
        H = [(r[1], min(r[0], r[2]), max(r[0], r[2])) for r in s[hz]]   # (y, x0, x1)
        V = [(r[0], min(r[1], r[3]), max(r[1], r[3])) for r in s[vt]]   # (x, y0, y1)
        return H, V


# ============================================================== legend tables
def initials(desc):
    words = re.sub(r"\(.*?\)", " ", desc).upper().split()
    words = [w for w in words if w not in ("OF", "AND", "&", "-", "THE")]
    return "".join(w[0] for w in words if w[0].isalnum())


def read_legend_tables(dw):
    """Find every table with a SYMBOLS | DESCRIPTION header and read its rows."""
    heads = [t for t in dw.texts if t["text"].upper() in HEADER_SYMBOL]
    descs = [t for t in dw.texts if t["text"].upper() in HEADER_DESC]
    H, V = dw.grid_lines(min_len=dw.diag * 0.004)
    rows, tables = [], []
    for hs in heads:
        same_row = [d for d in descs if d["x"] > hs["x"] and abs(d["y"] - hs["y"]) < 2 * hs["h"]]
        if not same_row:
            continue
        hd = min(same_row, key=lambda d: d["x"] - hs["x"])
        # a table border crosses the header row and runs down through the rows
        below = lambda v: v[1] < hs["y"] - 2 * hs["h"] and v[2] > hs["y"]
        xl = [v[0] for v in V if v[0] < hs["x"] and below(v)]
        xd = [v[0] for v in V if hs["x"] < v[0] < hd["x"] and below(v)]
        xr = [v[0] for v in V if v[0] > hd["x"] and below(v)]
        if not (xl and xd and xr):
            continue
        x_left, x_div, x_right = max(xl), min(xd), min(xr)
        width = x_right - x_left
        tol = width * 0.03
        # horizontal grid lines of THIS table: about as wide as the table, not wider
        ys = sorted({round(h[0], 6) for h in H
                     if abs(h[1] - x_left) <= tol and abs(h[2] - x_right) <= tol}, reverse=True)
        div_bottom = min(v[1] for v in V if abs(v[0] - x_div) < 1e-6 * dw.diag and below(v))
        below_hdr = [y for y in ys if div_bottom - tol <= y < hs["y"]]
        above_hdr = [y for y in ys if hs["y"] < y < hs["y"] + 8 * hs["h"]]
        if len(below_hdr) < 2:
            continue
        # rows: consecutive lines, stop at a gap much bigger than a normal row
        rest = [below_hdr[0]]
        gaps = []
        for y in below_hdr[1:]:
            g = rest[-1] - y
            if gaps and g > 3 * sorted(gaps)[len(gaps) // 2]:
                break
            gaps.append(g)
            rest.append(y)
        y_hdr_top = min(above_hdr) if above_hdr else hs["y"] + 2 * hs["h"]
        y_table_top = max(above_hdr) if above_hdr else y_hdr_top
        # title of the table (e.g. VALVES): text above the header row, inside the table
        title = [t["text"] for t in dw.texts if x_left < t["x"] < x_right
                 and y_hdr_top - 0.5 * hs["h"] < t["y"] < y_table_top + 2 * hs["h"]
                 and t["text"].upper() not in HEADER_SYMBOL + HEADER_DESC]
        category = title[0] if title else ""
        tables.append((x_left, rest[-1], x_right, y_table_top))
        for y_hi, y_lo in zip(rest, rest[1:]):
            band = lambda t: y_lo < t["y"] < y_hi
            desc = [t for t in dw.texts if x_div < t["x"] < x_right and band(t)]
            if not desc:
                continue
            desc.sort(key=lambda t: (-round(t["y"] / (hs["h"] * 0.8)), t["x"]))
            description = " ".join(t["text"] for t in desc)
            m = min(x_div - x_left, y_hi - y_lo) * 0.03
            cell = (x_left + m, y_lo + m, x_div - m, y_hi - m)
            codes = [t["text"] for t in dw.texts
                     if cell[0] < t["x"] < cell[2] and cell[1] < t["y"] < cell[3]]
            blocks = [i["name"] for i in dw.inserts
                      if i["src"] is None and cell[0] < i["x"] < cell[2] and cell[1] < i["y"] < cell[3]]
            rows.append({"category": category, "description": description, "cell": cell,
                         "code": codes[0] if codes else initials(description),
                         "code_from_symbol": bool(codes), "blocks": blocks})
    return rows, tables


TITLE_WORDS = ("DRAWN", "CHECKED", "APPROVED", "REVIEWED", "TITLE", "SCALE", "SHEET", "SIZE",
               "DATE", "PROJECT", "CLIENT", "CLEINT", "CONSULTANT", "DRAWING NO", "DRG NO", "DRG. NO", "REV")


def find_title_block(dw):
    """Bottom-right title block: the area spanned by its typical field names."""
    hits = [t for t in dw.texts if any(t["text"].upper().startswith(w) for w in TITLE_WORDS)]
    if len(hits) < 3:
        return None
    x0 = min(t["x"] for t in hits)
    y1 = max(t["y"] + 2 * (t["h"] or 1) for t in hits)
    if x0 < dw.ext.extmin.x + 0.4 * dw.ext.size.x:          # not a bottom-right block
        return None
    return (x0 - 0.01 * dw.ext.size.x, dw.ext.extmin.y, dw.ext.extmax.x, y1)


def inside_any(x, y, boxes, pad=0.0):
    return any(b[0] - pad <= x <= b[2] + pad and b[1] - pad <= y <= b[3] + pad for b in boxes)


# ============================================================== shape matching
ORIENTS = [(k, mir) for k in range(4) for mir in (False, True)]


def orient_matrix(k, mirror):
    c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][k]
    R = np.array([[c, -s], [s, c]], dtype=float)
    if mirror:
        R = R @ np.array([[-1, 0], [0, 1]], dtype=float)
    return R


class SegIndex:
    """Grid index: distance from points to the nearest drawing segment."""

    def __init__(self, segs, cell):
        self.s = segs
        self.cell = cell
        self.grid = defaultdict(list)
        for i, (x0, y0, x1, y1) in enumerate(segs):
            for gx in range(int(math.floor(min(x0, x1) / cell)), int(math.floor(max(x0, x1) / cell)) + 1):
                for gy in range(int(math.floor(min(y0, y1) / cell)), int(math.floor(max(y0, y1) / cell)) + 1):
                    self.grid[(gx, gy)].append(i)

    def inside(self, box, grow=0.05):
        """Segments lying completely inside the box (grown a little)."""
        x0, y0, x1, y1 = box
        g = max(x1 - x0, y1 - y0) * grow
        x0, y0, x1, y1 = x0 - g, y0 - g, x1 + g, y1 + g
        idx = set()
        for gx in range(int(math.floor(x0 / self.cell)), int(math.floor(x1 / self.cell)) + 1):
            for gy in range(int(math.floor(y0 / self.cell)), int(math.floor(y1 / self.cell)) + 1):
                idx.update(self.grid.get((gx, gy), ()))
        if not idx:
            return np.zeros((0, 4))
        S = self.s[list(idx)]
        m = ((S[:, 0] >= x0) & (S[:, 2] >= x0) & (S[:, 0] <= x1) & (S[:, 2] <= x1) &
             (S[:, 1] >= y0) & (S[:, 3] >= y0) & (S[:, 1] <= y1) & (S[:, 3] <= y1))
        return S[m]

    def near(self, pts, tol):
        cells = set()
        r = int(math.ceil(tol / self.cell))
        for x, y in pts:
            gx, gy = int(math.floor(x / self.cell)), int(math.floor(y / self.cell))
            for i in range(-r, r + 1):
                for j in range(-r, r + 1):
                    cells.add((gx + i, gy + j))
        idx = set()
        for c in cells:
            idx.update(self.grid.get(c, ()))
        if not idx:
            return np.zeros(len(pts), dtype=bool)
        S = self.s[list(idx)]
        A, B = S[:, :2], S[:, 2:]
        AB = B - A
        L2 = (AB ** 2).sum(1)
        L2[L2 == 0] = 1e-12
        P = pts[:, None, :]
        t = np.clip(((P - A) * AB).sum(2) / L2, 0, 1)
        proj = A + t[..., None] * AB
        d = np.sqrt(((P - proj) ** 2).sum(2)).min(1)
        return d <= tol


def make_template(dw, row):
    x0, y0, x1, y1 = row["cell"]
    s = dw.segs
    keep = ((s[:, 0] > x0) & (s[:, 2] > x0) & (s[:, 0] < x1) & (s[:, 2] < x1) &
            (s[:, 1] > y0) & (s[:, 3] > y0) & (s[:, 1] < y1) & (s[:, 3] < y1))
    T = s[keep]
    if len(T) < 3:
        return None
    pts = np.concatenate([T[:, :2], T[:, 2:]])
    c = (pts.min(0) + pts.max(0)) / 2
    T = T - np.concatenate([c, c])
    size = float(np.ptp(np.concatenate([T[:, :2], T[:, 2:]]), axis=0).max())
    if size <= 0:
        return None
    lens = np.hypot(T[:, 2] - T[:, 0], T[:, 3] - T[:, 1])
    total = lens.sum()
    # sample points along the template
    span = np.ptp(np.concatenate([T[:, :2], T[:, 2:]]), axis=0)
    minside = float(max(span.min(), size * 0.15))
    step = size / 40
    samples, sid = [], []
    for k, ((ax, ay, bx, by), L) in enumerate(zip(T, lens)):
        n = max(1, int(L / step))
        for i in range(n + 1):
            f = i / n
            samples.append((ax + (bx - ax) * f, ay + (by - ay) * f))
            sid.append(k)
    samples, sid = np.array(samples), np.array(sid)
    # anchors: longest segments with distinct directions
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
    rng = np.random.default_rng(0)
    quick = samples[rng.choice(len(samples), size=min(12, len(samples)), replace=False)]
    return {"segs": T, "lens": lens, "size": size, "minside": minside, "total": total,
            "samples": samples, "sid": sid, "quick": quick, "anchors": anchors}


def explained(segs, tsegs, tol, per_seg=6):
    """Share of the length of `segs` that lies on the template segments `tsegs`."""
    f = np.linspace(0, 1, per_seg)
    P = (segs[:, None, :2] + f[None, :, None] * (segs[:, None, 2:] - segs[:, None, :2])).reshape(-1, 2)
    w = np.repeat(np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]), per_seg)
    A, B = tsegs[:, :2], tsegs[:, 2:]
    AB = B - A
    L2 = (AB ** 2).sum(1)
    L2[L2 == 0] = 1e-12
    t = np.clip(((P[:, None, :] - A) * AB).sum(2) / L2, 0, 1)
    d = np.sqrt(((P[:, None, :] - (A + t[..., None] * AB)) ** 2).sum(2)).min(1)
    return float((w * (d <= tol)).sum() / (w.sum() or 1.0))


def match_template(tpl, dsegs, dlen, ddir, index, threshold, scale_range, max_size, max_tol,
                   min_precision=0.8):
    found = []
    T = tpl["segs"]
    for ai in tpl["anchors"]:
        a0, a1 = T[ai, :2], T[ai, 2:]
        va = a1 - a0
        la = float(np.hypot(*va))
        for k, mir in ORIENTS:
            R = orient_matrix(k, mir)
            u = R @ va / la
            cross = np.abs(ddir[:, 0] * u[1] - ddir[:, 1] * u[0])
            scale = dlen / la
            cand = np.where((cross < 0.035) & (scale > scale_range[0]) & (scale < scale_range[1])
                            & (scale * tpl["size"] <= max_size))[0]
            for j in cand:
                s = scale[j]
                d0, d1 = dsegs[j, :2], dsegs[j, 2:]
                start = d0 if np.dot(ddir[j], u) > 0 else d1
                t = start - s * (R @ a0)
                # tolerance grows with the symbol, but never so far that it "fits" anything
                tol = max(min(0.05 * tpl["size"] * s, 0.12 * tpl["minside"] * s, max_tol), 1e-9)
                q = (tpl["quick"] @ R.T) * s + t
                if index.near(q, tol).mean() < 0.75:
                    continue
                P = (tpl["samples"] @ R.T) * s + t
                hit = index.near(P, tol)
                # every part of the symbol must be there, not just most of its length
                per_seg = np.bincount(tpl["sid"], weights=hit) / np.bincount(tpl["sid"])
                recall = min(float(hit.mean()), float((per_seg >= 0.7).mean()))
                if recall < threshold:
                    continue
                box = (P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max())
                # precision: lines drawn inside the box must belong to the symbol
                inner = index.inside(box)
                if len(inner):
                    TS = np.concatenate([(T[:, :2] @ R.T) * s + t, (T[:, 2:] @ R.T) * s + t], 1)
                    if explained(inner, TS, tol) < min_precision:
                        continue
                found.append({"recall": float(recall), "box": box, "scale": float(s),
                              "weight": float(recall * tpl["total"] * s)})
    return found


def overlap(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1e-12
    return inter / small


def resolve(dets):
    """One detection per place. Same spot claimed by two symbols -> the one that explains
    more drawn geometry wins (an auto-shutoff valve beats the plain valve inside it)."""
    dets.sort(key=lambda d: (-d["weight"], -d["recall"]))
    kept = []
    for d in dets:
        if all(overlap(d["box"], k["box"]) < 0.5 for k in kept):
            kept.append(d)
    return kept


# ============================================================== labels
def count_labels(dw, code, legend_boxes, pad):
    if len(code) < 2:
        return []
    pat = re.compile(r"^" + re.escape(code.upper()) + r"(?:[-\s]?\d+[A-Z]?)?$")
    return [t for t in dw.texts
            if pat.match(t["text"].upper()) and not inside_any(t["x"], t["y"], legend_boxes, pad)]


def name_mentions(dw, description, exclude, pad):
    name = re.sub(r"\(.*?\)", " ", description).upper().split()
    if not name:
        return []
    pat = re.compile(r"(?<![A-Z])" + r"\s+".join(map(re.escape, name)) + r"(?![A-Z])")
    return [t for t in dw.texts if pat.search(t["text"].upper())
            and not inside_any(t["x"], t["y"], exclude, pad)]


# ============================================================== check drawing
def write_check_dxf(src_file, out_file, marks):
    doc = ezdxf.readfile(src_file) if not src_file.lower().endswith(".dwg") else None
    if doc is None:
        return False
    msp = doc.modelspace()
    for name, color in (("BOQ_SHAPE", 1), ("BOQ_LABEL", 5), ("BOQ_BLOCK", 3)):
        if name not in doc.layers:
            doc.layers.add(name, color=color)
    ext = bbox.extents(msp, fast=True)
    unit = math.hypot(ext.size.x, ext.size.y) * 0.001
    text_h = unit * 1.6
    for m in marks:
        x0, y0, x1, y1 = m["box"]
        pad = max(x1 - x0, y1 - y0) * 0.1 + unit
        layer = {"shape": "BOQ_SHAPE", "label": "BOQ_LABEL", "block": "BOQ_BLOCK"}[m["how"]]
        msp.add_lwpolyline([(x0 - pad, y0 - pad), (x1 + pad, y0 - pad), (x1 + pad, y1 + pad),
                            (x0 - pad, y1 + pad)], close=True, dxfattribs={"layer": layer})
        msp.add_text(m["name"], height=text_h,
                     dxfattribs={"layer": layer}).set_placement((x0 - pad, y1 + pad * 1.3))
    doc.saveas(out_file)
    return True


# ============================================================== main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("drawing")
    ap.add_argument("--threshold", type=float, default=0.88,
                    help="shape match: share of the legend symbol that must be found (default 0.88)")
    ap.add_argument("--min-scale", type=float, default=0.3)
    ap.add_argument("--max-scale", type=float, default=8.0)
    ap.add_argument("--max-symbol", type=float, default=0.05,
                    help="largest symbol size as a share of the sheet diagonal (default 0.05)")
    ap.add_argument("--out", default="component_counts.csv")
    a = ap.parse_args()

    doc = load(a.drawing)
    dw = Drawing(doc)
    rows, tables = read_legend_tables(dw)
    if not rows:
        sys.exit("No legend table with 'SYMBOLS' and 'DESCRIPTION' headers was found.\n"
                 "If the symbols are blocks, use count_by_DXF.py instead.")
    pad = dw.diag * 0.002
    title = find_title_block(dw)
    print(f"Legend: {len(tables)} table(s), {len(rows)} symbols"
          + ("   |   title block found and ignored" if title else ""))
    print()
    tables_and_title = tables + ([title] if title else [])

    # drawing geometry outside the legend tables
    s = dw.segs
    mx, my = (s[:, 0] + s[:, 2]) / 2, (s[:, 1] + s[:, 3]) / 2
    outside = np.array([not inside_any(x, y, tables_and_title, pad) for x, y in zip(mx, my)])
    dsegs = s[outside]
    dlen = np.hypot(dsegs[:, 2] - dsegs[:, 0], dsegs[:, 3] - dsegs[:, 1])
    ok = dlen > 0
    dsegs, dlen = dsegs[ok], dlen[ok]
    ddir = (dsegs[:, 2:] - dsegs[:, :2]) / dlen[:, None]
    index = SegIndex(dsegs, cell=dw.diag / 300)

    # block names used inside the legend (never counted as components)
    results, marks, all_shape = [], [], []
    for r in rows:
        r["label_hits"] = count_labels(dw, r["code"], tables_and_title, pad)
        r["block_hits"] = [i for i in dw.inserts if i["src"] is None and i["name"] in r["blocks"]
                           and not inside_any(i["x"], i["y"], tables_and_title, pad)]
        # a symbol that carries its own code (PG in a circle, PT in a box) is identified by
        # that code; its outline alone (circle / box) says nothing, so no shape matching
        use_shape = not (r["block_hits"] or r["label_hits"] or r["code_from_symbol"])
        r["tpl"] = make_template(dw, r) if use_shape else None
        if r["tpl"] is not None:
            for d in match_template(r["tpl"], dsegs, dlen, ddir, index, a.threshold,
                                    (a.min_scale, a.max_scale),
                                    max_size=dw.diag * a.max_symbol, max_tol=dw.diag * 0.0012):
                d["row"] = r
                all_shape.append(d)

    # a shape match sitting on an item already identified another way (its own label, e.g.
    # "ASV", or a block, e.g. the PRV) is that item, not a second component
    taken = []
    for r in rows:
        for t in r["label_hits"]:
            taken.append((r, t["x"], t["y"], None))
        for i in r["block_hits"]:
            b = i["box"]
            taken.append((r, None, None, (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y)))

    def claimed(d):
        x0, y0, x1, y1 = d["box"]
        cx, cy, size = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0)
        for r, x, y, box in taken:
            if r is d["row"] or r["category"] != d["row"]["category"]:
                continue
            if box is not None and overlap(d["box"], box) > 0.3:
                return True
            if x is not None and math.hypot(x - cx, y - cy) <= 1.2 * size:
                return True
        return False

    def nested(d):
        """Centre inside a small closed frame -> part of a larger composite symbol
        (e.g. the valve drawn inside a load-cell box), not a component of its own."""
        x0, y0, x1, y1 = d["box"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        area = max((x1 - x0) * (y1 - y0), 1e-12)
        for f in dw.frames:
            fa = (f[2] - f[0]) * (f[3] - f[1])
            if f[0] < cx < f[2] and f[1] < cy < f[3] and 1.2 * area <= fa <= 4 * area:
                return True
        return False

    kept_dets = [d for d in resolve(all_shape) if not claimed(d)]
    nested_n = Counter(d["row"]["description"] for d in kept_dets if nested(d))
    shape_hits = Counter()
    for d in [d for d in kept_dets if not nested(d)]:
        shape_hits[id(d["row"])] += 1
        marks.append({"box": d["box"], "how": "shape", "name": d["row"]["description"]})

    print(f"{'Category':12} {'Component':36} {'Count':>5}  Method")
    print("-" * 72)
    for r in rows:
        if r["block_hits"]:
            n, how = len(r["block_hits"]), f"block {r['blocks'][0]}"
            for i in r["block_hits"]:
                b = i["box"]
                marks.append({"box": (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y),
                              "how": "block", "name": r["description"]})
        elif r["label_hits"]:
            n, how = len(r["label_hits"]), f"label '{r['code']}'"
            for t in r["label_hits"]:
                h = t["h"] or 1.0
                marks.append({"box": (t["x"], t["y"], t["x"] + h * len(t["text"]) * 0.8, t["y"] + h),
                              "how": "label", "name": r["description"]})
        elif r["code_from_symbol"]:
            n, how = 0, f"label '{r['code']}' (none found)"
        elif r["tpl"] is not None and shape_hits[id(r)]:
            n, how = shape_hits[id(r)], "shape"
        elif (named := name_mentions(dw, r["description"], tables_and_title, pad)):
            # drawn differently from the legend icon (e.g. the real vessel), but named
            n, how = len(named), "name written in drawing - verify"
            for t in named:
                h = t["h"] or 1.0
                marks.append({"box": (t["x"], t["y"], t["x"] + h, t["y"] + h),
                              "how": "label", "name": r["description"]})
        elif r["tpl"] is not None:
            n, how = 0, "shape (none found) - check manually"
        else:
            n, how = 0, "NOT COUNTED (no label, symbol too simple) - check manually"
        results.append((r["category"], r["description"], n, how))
        print(f"{r['category'][:12]:12} {r['description'][:36]:36} {n:>5}  {how}")
    print("-" * 72)
    print(f"{'TOTAL':49} {sum(x[2] for x in results):>5}")
    if nested_n:
        print("\nNot counted - found inside a larger symbol's frame (part of that symbol):")
        for k, n in nested_n.items():
            print(f"  {k:46} {n:>5}")

    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "component", "count", "method"])
        w.writerows(results)
    print(f"\nSaved: {a.out}")
    check = str(Path(a.drawing).with_suffix("")) + "_check.dxf"
    if write_check_dxf(a.drawing, check, marks):
        print(f"Saved: {check}  (red = shape, blue = label, green = block) - open it to verify")


if __name__ == "__main__":
    main()
