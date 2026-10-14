"""
Convert DWG files to DXF.

Uses the free ODA File Converter (download: opendesign.com > Guest Files > ODA File Converter).
ezdxf calls it in the background, so nothing has to be opened by hand.

Usage:
  python convert_dwg_to_dxf.py so2_vaporizer.dwg                 -> so2_vaporizer.dxf (same folder)
  python convert_dwg_to_dxf.py so2_vaporizer.dwg out\\so2.dxf     -> chosen output name
  python convert_dwg_to_dxf.py "C:\\Drawings"                     -> converts every .dwg in the folder
  python convert_dwg_to_dxf.py "C:\\Drawings" --out-dir dxf       -> puts the DXFs in another folder
  python convert_dwg_to_dxf.py so2_vaporizer.dwg --version R2013  -> older DXF version

Requires: pip install ezdxf   (+ ODA File Converter installed)
"""
import argparse
import glob
import sys
from pathlib import Path

import ezdxf
from ezdxf.addons import odafc


def find_oda_windows():
    """ODA installs into a versioned folder, e.g. C:\\Program Files\\ODA\\ODAFileConverter 25.12.0\\"""
    for root in (r"C:\Program Files\ODA", r"C:\Program Files (x86)\ODA"):
        hits = sorted(glob.glob(root + r"\ODAFileConverter*\ODAFileConverter.exe"))
        if hits:
            return hits[-1]                      # newest installed version
    return None


def setup_oda(exe_path=None):
    if sys.platform.startswith("win"):
        exe = exe_path or find_oda_windows()
        if exe:
            ezdxf.options.set("odafc-addon", "win_exec_path", exe)
    elif exe_path:
        ezdxf.options.set("odafc-addon", "unix_exec_path", exe_path)
    if not odafc.is_installed():
        sys.exit("ODA File Converter not found.\n"
                 "  Install it from opendesign.com (Guest Files > ODA File Converter),\n"
                 "  or give its location with --oda \"C:\\path\\to\\ODAFileConverter.exe\"")


def convert_one(src: Path, dest: Path, version: str) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        odafc.convert(str(src), str(dest), version=version, audit=True, replace=True)
    except Exception as err:                     # corrupt file, unsupported version, ...
        print(f"  FAILED  {src.name}: {err}")
        return False
    # quick check: the new DXF opens and has content
    try:
        doc = ezdxf.readfile(dest)
        n = len(doc.modelspace())
        blocks = len(doc.modelspace().query("INSERT"))
        print(f"  OK      {src.name} -> {dest}  ({n} entities, {blocks} block references)")
    except Exception as err:
        print(f"  WARNING {dest} was written but could not be re-opened: {err}")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="a .dwg file or a folder of .dwg files")
    ap.add_argument("dest", nargs="?", help="output .dxf file (single-file mode only)")
    ap.add_argument("--out-dir", help="folder for the DXF files (default: next to each DWG)")
    ap.add_argument("--version", default="R2018",
                    help="DXF version: R12, R2000, R2004, R2007, R2010, R2013, R2018 (default R2018)")
    ap.add_argument("--oda", help="full path to ODAFileConverter.exe, if not found automatically")
    a = ap.parse_args()

    setup_oda(a.oda)
    src = Path(a.source)

    if src.is_dir():
        files = sorted(p for p in src.iterdir() if p.suffix.lower() == ".dwg")
        if not files:
            sys.exit(f"No .dwg files in {src}")
        print(f"Converting {len(files)} DWG file(s) to DXF {a.version}:")
        ok = 0
        for f in files:
            out_dir = Path(a.out_dir) if a.out_dir else f.parent
            ok += convert_one(f, out_dir / f.with_suffix(".dxf").name, a.version)
        print(f"\nDone: {ok} of {len(files)} converted.")
    elif src.is_file() and src.suffix.lower() == ".dwg":
        if a.dest:
            dest = Path(a.dest)
        elif a.out_dir:
            dest = Path(a.out_dir) / src.with_suffix(".dxf").name
        else:
            dest = src.with_suffix(".dxf")
        print(f"Converting to DXF {a.version}:")
        if not convert_one(src, dest, a.version):
            sys.exit(1)
    else:
        sys.exit(f"Not a .dwg file or folder: {src}")


if __name__ == "__main__":
    main()
