"""
Draft BOQ: component count from P&ID drawings uploaded against one equipment
item of an RFQ thread, using each drawing's own legend tables. An equipment
item can have several drawings (sheets); its draft BOQ is their counts added up.

The counting/conversion scripts live as-is in settings.component_count_script_dir
(backend/component_count/scripts) and are run as subprocesses - they're
standalone CLI tools that are also used by hand, print their own report, and
write their outputs (CSV, check drawing, legend crops) into the working folder.

Per upload format:
  .dxf -> count_by_DXF.py
  .svg -> count_by_svg.py
  .dwg -> convert_dwg_to_dxf.py (ODA File Converter) -> .dxf, then
          convert_dxf_to_svg.py -> .svg, then count_by_DXF.py on the .dxf
          (real text + block names, so more exact); falls back to
          count_by_svg.py on the .svg if the DXF counter finds no legend.

Each uploaded drawing gets its own folder under settings.component_count_storage_dir
(<thread_id>/<equipment_index>/<run_id>/), holding the upload, every
converted/check file and result.json.
"""
import csv
import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from .config import settings

ALLOWED_EXTENSIONS = (".dwg", ".dxf", ".svg")

# script runs can be slow on big sheets (shape matching over every legend row),
# especially on a laptop on battery power
SCRIPT_TIMEOUT_SECONDS = 1800

# files a run folder may hold that the API serves for download / preview
SERVED_FILES = {
    "drawing.dwg", "drawing.dxf", "drawing.svg", "drawing_check.dxf",
    "check.svg", "check.png", "counts.csv",
}


def _scripts_dir() -> Path:
    return Path(settings.component_count_script_dir).resolve()


def _storage_dir() -> Path:
    return Path(settings.component_count_storage_dir).resolve()


def _equipment_dir(thread_id, equipment_index: int) -> Path:
    return _storage_dir() / str(thread_id) / str(int(equipment_index))


def run_dir(thread_id, run_id: str) -> Path | None:
    """A drawing's folder, under any equipment item of the thread."""
    if not re.fullmatch(r"[0-9a-f]{32}", run_id or ""):
        return None
    for d in (_storage_dir() / str(thread_id)).glob(f"*/{run_id}"):
        if d.is_dir():
            return d
    return None


def _run_script(script: str, args: list[str], cwd: Path) -> dict:
    """Run one of the scripts; returns a step record for the result log."""
    cmd = [sys.executable, str(_scripts_dir() / script), *args]
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=SCRIPT_TIMEOUT_SECONDS,
        )
        output = (proc.stdout + ("\n" + proc.stderr if proc.stderr.strip() else "")).strip()
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        output, ok = f"Timed out after {SCRIPT_TIMEOUT_SECONDS}s", False
    return {"script": script, "ok": ok, "output": output}


def _read_counts(csv_path: Path) -> list[dict]:
    """Both counters' CSVs -> one row shape. The DXF counter has category +
    method columns; the SVG counter has the legend row number instead."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            rows.append({
                "category": r.get("category") or "",
                "component": r.get("component") or "",
                "count": int(float(r.get("count") or 0)),
                "method": r.get("method") or "",
                "legend_row": int(r["legend_row"]) if r.get("legend_row") else None,
            })
    return rows


def _count_dxf(folder: Path, steps: list) -> bool:
    step = _run_script("count_by_DXF.py", ["drawing.dxf", "--out", "counts.csv"], folder)
    steps.append(step)
    if not step["ok"] or not (folder / "counts.csv").exists():
        return False
    # the check DXF (every counted item boxed) as SVG, so it previews in the browser
    if (folder / "drawing_check.dxf").exists():
        steps.append(_run_script(
            "convert_dxf_to_svg.py", ["drawing_check.dxf", "check.svg", "--color"], folder
        ))
    return True


def _count_svg(folder: Path, steps: list) -> bool:
    step = _run_script(
        "count_by_svg.py",
        ["drawing.svg", "--out", "counts.csv", "--check-image", "check.png"],
        folder,
    )
    steps.append(step)
    return step["ok"] and (folder / "counts.csv").exists()


def run(thread_id, equipment_index: int, filename: str, data: bytes) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext}' - upload a .dwg, .dxf or .svg drawing")
    if not data:
        raise ValueError("The uploaded file is empty")

    run_id = uuid.uuid4().hex
    folder = _equipment_dir(thread_id, equipment_index) / run_id
    folder.mkdir(parents=True)
    (folder / f"drawing{ext}").write_bytes(data)

    steps: list[dict] = []
    counted_by = None
    if ext == ".dxf":
        counted_by = "dxf" if _count_dxf(folder, steps) else None
    elif ext == ".svg":
        counted_by = "svg" if _count_svg(folder, steps) else None
    else:
        steps.append(_run_script("convert_dwg_to_dxf.py", ["drawing.dwg", "drawing.dxf"], folder))
        if (folder / "drawing.dxf").exists():
            steps.append(_run_script("convert_dxf_to_svg.py", ["drawing.dxf", "drawing.svg"], folder))
            if _count_dxf(folder, steps):
                counted_by = "dxf"
            elif (folder / "drawing.svg").exists():
                (folder / "counts.csv").unlink(missing_ok=True)
                counted_by = "svg" if _count_svg(folder, steps) else None

    components = _read_counts(folder / "counts.csv") if counted_by else []
    result = {
        "run_id": run_id,
        "file_name": Path(filename).name,
        "file_type": ext[1:],
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "counted_by": counted_by,
        "ok": counted_by is not None,
        "error": None if counted_by else _failure_message(steps),
        "components": components,
        "total": sum(c["count"] for c in components),
        "files": sorted(f.name for f in folder.iterdir() if f.name in SERVED_FILES),
        "steps": steps,
    }
    (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _failure_message(steps: list[dict]) -> str:
    failed = next((s for s in reversed(steps) if not s["ok"]), None)
    if failed is None:
        return "Counting produced no result"
    lines = [l for l in failed["output"].splitlines() if l.strip()] or ["(no output)"]
    # a crash -> the exception line at the end; a sys.exit message -> its first line
    reason = lines[-1] if "Traceback" in failed["output"] else lines[0]
    return f"{failed['script']} failed: {reason.strip()}"


def list_runs(thread_id, equipment_index: int) -> list[dict]:
    """Every drawing uploaded for this equipment item, oldest first."""
    out = []
    for f in _equipment_dir(thread_id, equipment_index).glob("*/result.json"):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    out.sort(key=lambda r: r.get("ran_at") or "")
    return out


def drawing_count(thread_id) -> int:
    """Drawings uploaded for this thread, across all its equipment items."""
    return sum(1 for _ in (_storage_dir() / str(thread_id)).glob("*/*/result.json"))


def set_count(thread_id, run_id: str, index: int, count: int | None) -> dict:
    """Override one component's count in a drawing (None reverts it to the
    count the script found, kept as detected_count while edited). Saved in the
    drawing's result.json, so the combined BOQ picks it up too."""
    d = run_dir(thread_id, run_id)
    if d is None or not (d / "result.json").exists():
        raise LookupError("Drawing not found")
    result = json.loads((d / "result.json").read_text(encoding="utf-8"))
    components = result.get("components") or []
    if not 0 <= index < len(components):
        raise ValueError("Invalid component index")
    if count is not None and count < 0:
        raise ValueError("Count can't be negative")
    c = components[index]
    detected = c.get("detected_count", c["count"])
    if count is None or count == detected:
        c["count"] = detected
        c.pop("detected_count", None)
    else:
        c["count"] = count
        c["detected_count"] = detected
    result["total"] = sum(x["count"] for x in components)
    (d / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def delete_run(thread_id, run_id: str) -> bool:
    d = run_dir(thread_id, run_id)
    if d is None:
        return False
    shutil.rmtree(d)
    return True


def combine(runs: list[dict]) -> list[dict]:
    """The equipment item's draft BOQ: every counted drawing's components added
    up by name, in first-seen (legend) order. Matched on name only - SVG counts
    have no category, so the same valve from a DXF and an SVG sheet still adds up."""
    totals: dict[str, dict] = {}
    for r in runs:
        if not r.get("ok"):
            continue
        for c in r["components"]:
            key = " ".join(c["component"].upper().split())
            if key not in totals:
                totals[key] = {"category": c["category"], "component": c["component"], "count": 0}
            elif not totals[key]["category"]:
                totals[key]["category"] = c["category"]
            totals[key]["count"] += c["count"]
    return list(totals.values())
