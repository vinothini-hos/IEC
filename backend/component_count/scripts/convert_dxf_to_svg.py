"""
Convert DXF files to SVG with the ezdxf drawing add-on.

Usage:
  python convert_dxf_to_svg.py so2_vaporizer.dxf                -> so2_vaporizer.svg
  python convert_dxf_to_svg.py so2_vaporizer.dxf out.svg        -> chosen output name
  python convert_dxf_to_svg.py "C:\\Drawings"                    -> every .dxf in the folder
  python convert_dxf_to_svg.py so2_vaporizer.dxf --layout Layout1   -> a paper-space layout
  python convert_dxf_to_svg.py so2_vaporizer.dxf --color           -> keep CAD colours

Requires: pip install ezdxf
"""
import argparse
import sys
from pathlib import Path

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, config, layout, svg


def convert(src: Path, dest: Path, layout_name: str, keep_color: bool, margin_mm: float):
    doc = ezdxf.readfile(src)
    if layout_name == "Model":
        space = doc.modelspace()
    else:
        try:
            space = doc.paperspace(layout_name)
        except KeyError:
            names = ", ".join(doc.layout_names())
            raise SystemExit(f"Layout '{layout_name}' not found in {src.name}. Available: {names}")

    cfg = config.Configuration(
        background_policy=config.BackgroundPolicy.WHITE,
        color_policy=config.ColorPolicy.COLOR if keep_color else config.ColorPolicy.BLACK,
        lineweight_scaling=1.0,
    )
    backend = svg.SVGBackend()
    Frontend(RenderContext(doc), backend, config=cfg).draw_layout(space, finalize=True)

    # page size 0 x 0 = fit the page to the drawing's extents
    page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(margin_mm))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(backend.get_string(page), encoding="utf-8")
    print(f"OK  {src.name} -> {dest}  ({len(space)} entities)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="a .dxf file or a folder of .dxf files")
    ap.add_argument("dest", nargs="?", help="output .svg file (single-file mode only)")
    ap.add_argument("--layout", default="Model", help="'Model' (default) or a layout tab name")
    ap.add_argument("--color", action="store_true", help="keep CAD colours (default: black on white)")
    ap.add_argument("--margin", type=float, default=10, help="page margin in mm (default 10)")
    a = ap.parse_args()

    src = Path(a.source)
    if src.is_dir():
        files = sorted(p for p in src.iterdir() if p.suffix.lower() == ".dxf")
        if not files:
            sys.exit(f"No .dxf files in {src}")
        for f in files:
            try:
                convert(f, f.with_suffix(".svg"), a.layout, a.color, a.margin)
            except Exception as err:
                print(f"FAILED  {f.name}: {err}")
    elif src.is_file() and src.suffix.lower() == ".dxf":
        convert(src, Path(a.dest) if a.dest else src.with_suffix(".svg"), a.layout, a.color, a.margin)
    else:
        sys.exit(f"Not a .dxf file or folder: {src}")


if __name__ == "__main__":
    main()
