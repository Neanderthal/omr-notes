#!/usr/bin/env python3
"""OMR pipeline: sheet-music image -> per-piece MusicXML (+ optional render).

Pipeline:  split page into pieces  ->  recognise each piece  ->  render check.

Splitting BEFORE recognition is the whole point: oemer and Audiveris otherwise
merge several pieces printed on one page into one score.

Usage:
    omr.py IMAGE [IMAGE ...] -o OUTDIR
           [--engine oemer|audiveris|both]   (default: audiveris)
           [--no-split] [--pieces N] [--min-gap PX] [--scale F]
           [--render] [--debug]

This orchestrator runs under any python3; heavy work is delegated to the OMR
venv and the bundled Audiveris. Resolve tool locations via env vars:
    OMR_HOME       (default ~/.local/share/omr-notes)
    OMR_PYTHON     (default $OMR_HOME/venv/bin/python)
    OMR_AUDIVERIS  (default $OMR_HOME/audiveris/bin/Audiveris)
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("OMR_HOME", Path.home() / ".local/share/omr-notes"))
PYTHON = Path(os.environ.get("OMR_PYTHON", HOME / "venv/bin/python"))
AUDIVERIS = Path(os.environ.get("OMR_AUDIVERIS", HOME / "audiveris/bin/Audiveris"))
HERE = Path(__file__).resolve().parent


def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd), file=sys.stderr)
    return subprocess.run([str(c) for c in cmd], **kw)


def split(image, outdir, args):
    cmd = [PYTHON, HERE / "split_pieces.py", image, "-o", outdir,
           "--scale", args.scale]
    if args.pieces:
        cmd += ["--pieces", args.pieces]
    if args.min_gap:
        cmd += ["--min-gap", args.min_gap]
    if args.dewarp:
        cmd += ["--dewarp"]
    if args.binarize:
        cmd += ["--binarize"]
    if args.debug:
        cmd += ["--debug"]
    r = run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return []
    info = json.loads(r.stdout)
    return [Path(o["file"]) for o in info["outputs"]]


def _first_output(outdir, stem, ext):
    # Audiveris may append .mvtN for multi-movement scores; oemer is exact.
    hits = sorted(outdir.glob(f"{stem}*.{ext}"))
    return hits[0] if hits else None


def recognise_oemer(piece, outdir):
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="")  # force CPU
    run([PYTHON.parent / "oemer", "-o", outdir, piece],
        env=env, capture_output=True, text=True)
    return _first_output(outdir, piece.stem, "musicxml")


def recognise_audiveris(piece, outdir):
    if not AUDIVERIS.exists():
        print(f"  ! Audiveris not found at {AUDIVERIS}", file=sys.stderr)
        return None
    run([AUDIVERIS, "-batch", "-export", "-output", outdir, piece],
        capture_output=True, text=True)
    return _first_output(outdir, piece.stem, "mxl")


ENGINES = {"oemer": recognise_oemer, "audiveris": recognise_audiveris}


def render(inp, outdir):
    out = outdir / f"{inp.stem}_render.png"
    r = run([PYTHON, HERE / "render_musicxml.py", inp, out],
            capture_output=True, text=True)
    return out if r.returncode == 0 and out.exists() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, required=True)
    ap.add_argument("--engine", choices=["oemer", "audiveris", "both"],
                    default="audiveris")
    ap.add_argument("--no-split", action="store_true")
    ap.add_argument("--pieces", type=int, default=None)
    ap.add_argument("--min-gap", type=int, default=None)
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--dewarp", action="store_true",
                    help="flatten page curvature before splitting (bowed photos)")
    ap.add_argument("--binarize", action="store_true",
                    help="feed clean bitonal crops to the OMR engine")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    engines = ["oemer", "audiveris"] if args.engine == "both" else [args.engine]
    results = []

    for image in args.images:
        piece_dir = args.outdir / image.stem
        if args.no_split:
            pieces = [image]
        else:
            pieces = split(image, piece_dir / "pieces", args) or [image]
        print(f"{image.name}: {len(pieces)} piece(s)", file=sys.stderr)

        for piece in pieces:
            for eng in engines:
                eng_dir = piece_dir / eng
                eng_dir.mkdir(parents=True, exist_ok=True)
                xml = ENGINES[eng](piece, eng_dir)
                rendered = render(xml, eng_dir) if (xml and args.render) else None
                results.append({"image": image.name, "piece": piece.name,
                                "engine": eng,
                                "musicxml": str(xml) if xml else None,
                                "render": str(rendered) if rendered else None})
                status = "ok" if xml else "FAILED"
                print(f"  [{eng}] {piece.name} -> {status}", file=sys.stderr)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    ok = sum(1 for r in results if r["musicxml"])
    print(f"\n{ok}/{len(results)} recognised", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
