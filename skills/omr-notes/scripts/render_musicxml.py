#!/usr/bin/env python3
"""Render a MusicXML/.mxl file to PNG (page 1) for visual verification.

Usage: render_musicxml.py INPUT.(musicxml|mxl) OUTPUT.png [--width 1400]
Must run under the OMR venv (needs verovio + cairosvg).
"""
import argparse
import sys
from pathlib import Path

import verovio
import cairosvg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--width", type=int, default=1400)
    args = ap.parse_args()

    tk = verovio.toolkit()
    if not tk.loadFile(str(args.inp)):
        print(f"error: verovio could not load {args.inp}", file=sys.stderr)
        return 1
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 40,
                   "adjustPageHeight": True})
    tk.redoLayout()
    svg = args.out.with_suffix(".svg")
    tk.renderToSVGFile(str(svg), 1)
    cairosvg.svg2png(url=str(svg), write_to=str(args.out), output_width=args.width)
    print(str(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
