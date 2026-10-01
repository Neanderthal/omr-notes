#!/usr/bin/env python3
"""Export a (corrected) MusicXML to a titled sheet-music PDF and/or MIDI.

    export.py IN.mxl [--pdf OUT.pdf] [--midi OUT.mid]
              [--title "..."] [--composer "..."] [--scale 48]

PDF uses verovio + cairosvg (multi-page merged with pypdf). Title/composer, when
given, overwrite the score metadata (Audiveris usually leaves the filename as the
title). Run under the OMR venv.
"""
import argparse
import shutil
import sys
import tempfile

from music21 import converter, metadata


def with_metadata(score, title, composer):
    if not title and not composer:
        return score
    md = score.metadata or metadata.Metadata()
    for e in list(score.getElementsByClass(metadata.Metadata)):
        score.remove(e)
    if title:
        md.title = title
        md.movementName = title
        md.movementNumber = None
    if composer:
        md.composer = composer
    score.insert(0, md)
    return score


def to_pdf(src_musicxml, out_pdf, scale):
    import verovio
    import cairosvg
    tk = verovio.toolkit()
    if not tk.loadFile(str(src_musicxml)):
        raise RuntimeError(f"verovio could not load {src_musicxml}")
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": scale,
                   "pageMarginTop": 150, "pageMarginLeft": 120, "pageMarginRight": 120,
                   "header": "auto", "footer": "none", "adjustPageHeight": False})
    tk.redoLayout()
    pages = tk.getPageCount()
    tmp = tempfile.mkdtemp()
    parts = []
    for i in range(1, pages + 1):
        svg = f"{tmp}/p{i}.svg"
        pdf = f"{tmp}/p{i}.pdf"
        tk.renderToSVGFile(svg, i)
        cairosvg.svg2pdf(url=svg, write_to=pdf)
        parts.append(pdf)
    if len(parts) == 1:
        shutil.copyfile(parts[0], out_pdf)
    else:
        try:
            from pypdf import PdfWriter
        except ImportError:
            from PyPDF2 import PdfWriter
        w = PdfWriter()
        for p in parts:
            w.append(p)
        with open(out_pdf, "wb") as f:
            w.write(f)
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("--pdf")
    ap.add_argument("--midi")
    ap.add_argument("--title")
    ap.add_argument("--composer")
    ap.add_argument("--scale", type=float, default=48)
    args = ap.parse_args()

    if not args.pdf and not args.midi:
        sys.exit("nothing to do — pass --pdf and/or --midi")

    score = with_metadata(converter.parse(args.inp), args.title, args.composer)

    # write a temp MusicXML carrying the metadata, for verovio
    tmp = tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False)
    score.write("musicxml", fp=tmp.name)

    if args.midi:
        score.write("midi", fp=args.midi)
        print(f"✓ MIDI → {args.midi}")
    if args.pdf:
        n = to_pdf(tmp.name, args.pdf, args.scale)
        print(f"✓ PDF  → {args.pdf} ({n} page{'s' if n != 1 else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
