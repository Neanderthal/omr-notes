#!/usr/bin/env python3
"""OMR pipeline: sheet-music image -> per-piece MusicXML (+ optional render/QA).

Pipeline:  split page into pieces  ->  recognise each piece  ->  render / QA check.

Splitting BEFORE recognition is the whole point: oemer and Audiveris otherwise
merge several pieces printed on one page into one score.

Usage:
    omr.py IMAGE [IMAGE ...] -o OUTDIR
           [--engine oemer|audiveris|both]   (default: audiveris)
           [--no-split] [--pieces N] [--min-gap PX] [--scale F]
           [--dewarp] [--binarize]
           [--render] [--check] [--best] [--debug]

    --check   run structural QA (check_musicxml.py) on each result and print a verdict
    --best    try several engine/flag configs per piece and KEEP the one with the
              lowest QA penalty (ignores --engine). Winners land in OUTDIR/<img>/best/.

This orchestrator runs under any python3; heavy work is delegated to the OMR
venv and the bundled Audiveris. Resolve tool locations via env vars:
    OMR_HOME       (default ~/.local/share/omr-notes)
    OMR_PYTHON     (default $OMR_HOME/venv/bin/python)
    OMR_AUDIVERIS  (default $OMR_HOME/audiveris/bin/Audiveris)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("OMR_HOME", Path.home() / ".local/share/omr-notes"))
PYTHON = Path(os.environ.get("OMR_PYTHON", HOME / "venv/bin/python"))
AUDIVERIS = Path(os.environ.get("OMR_AUDIVERIS", HOME / "audiveris/bin/Audiveris"))
HERE = Path(__file__).resolve().parent

# configs tried by --best, roughly best-first (cheap wins early)
BEST_CONFIGS = [
    ("audiveris", ["--binarize", "--dewarp"]),
    ("audiveris", ["--binarize"]),
    ("audiveris", []),
    ("oemer", ["--binarize"]),
    ("oemer", []),
]


def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd), file=sys.stderr)
    return subprocess.run([str(c) for c in cmd], **kw)


def split(image, outdir, scale, flags, debug):
    cmd = [PYTHON, HERE / "split_pieces.py", image, "-o", outdir, "--scale", scale, *flags]
    if debug:
        cmd += ["--debug"]
    r = run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return []
    return [Path(o["file"]) for o in json.loads(r.stdout)["outputs"]]


def split_flags(args):
    f = []
    if args.pieces:
        f += ["--pieces", str(args.pieces)]
    if args.min_gap:
        f += ["--min-gap", str(args.min_gap)]
    if args.dewarp:
        f += ["--dewarp"]
    if args.binarize:
        f += ["--binarize"]
    return f


def _first_output(outdir, stem, ext):
    # Audiveris may append .mvtN for multi-movement scores; oemer is exact.
    hits = sorted(outdir.glob(f"{stem}*.{ext}"))
    return hits[0] if hits else None


def recognise_oemer(piece, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="")  # force CPU
    run([PYTHON.parent / "oemer", "-o", outdir, piece],
        env=env, capture_output=True, text=True)
    return _first_output(outdir, piece.stem, "musicxml")


def recognise_audiveris(piece, outdir):
    if not AUDIVERIS.exists():
        print(f"  ! Audiveris not found at {AUDIVERIS}", file=sys.stderr)
        return None
    outdir.mkdir(parents=True, exist_ok=True)
    run([AUDIVERIS, "-batch", "-export", "-output", outdir, piece],
        capture_output=True, text=True)
    return _first_output(outdir, piece.stem, "mxl")


ENGINES = {"oemer": recognise_oemer, "audiveris": recognise_audiveris}


def render(inp, outdir):
    out = outdir / f"{inp.stem}_render.png"
    r = run([PYTHON, HERE / "render_musicxml.py", inp, out],
            capture_output=True, text=True)
    return out if r.returncode == 0 and out.exists() else None


def qa(xml):
    """Structural QA penalty for a MusicXML (lower = better). None → worst."""
    if not xml:
        return {"penalty": 999, "verdict": "FAIL", "issues": ["no output"]}
    r = run([PYTHON, HERE / "check_musicxml.py", xml, "--json"],
            capture_output=True, text=True)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"penalty": 999, "verdict": "FAIL", "issues": ["QA check failed"]}


def process_normal(image, args, engines):
    piece_dir = args.outdir / image.stem
    if args.no_split:
        pieces = [image]
    else:
        pieces = split(image, piece_dir / "pieces", args.scale,
                       split_flags(args), args.debug) or [image]
    print(f"{image.name}: {len(pieces)} piece(s)", file=sys.stderr)

    results = []
    for piece in pieces:
        for eng in engines:
            eng_dir = piece_dir / eng
            xml = ENGINES[eng](piece, eng_dir)
            rendered = render(xml, eng_dir) if (xml and args.render) else None
            rec = {"image": image.name, "piece": piece.name, "engine": eng,
                   "musicxml": str(xml) if xml else None,
                   "render": str(rendered) if rendered else None}
            status = "ok" if xml else "FAILED"
            if args.check:
                q = qa(str(xml) if xml else None)
                rec["qa"] = q
                status += f"  [QA {q['verdict']} pen={q['penalty']}]"
                for i in q["issues"]:
                    print(f"      ✗ {i}", file=sys.stderr)
            print(f"  [{eng}] {piece.name} -> {status}", file=sys.stderr)
            results.append(rec)
    return results


def process_best(image, args):
    piece_dir = args.outdir / image.stem
    base = []
    if args.pieces:
        base += ["--pieces", str(args.pieces)]
    if args.min_gap:
        base += ["--min-gap", str(args.min_gap)]

    # run every config; piece detection is independent of binarize/dewarp, so
    # piece indices line up across configs.
    per_piece = {}
    for eng, sflags in BEST_CONFIGS:
        label = "_".join([eng] + [f.lstrip("-") for f in sflags])
        cfg_dir = piece_dir / "configs" / label
        pieces = split(image, cfg_dir / "pieces", args.scale, base + sflags, args.debug)
        if not pieces:
            pieces = [image]
        for i, piece in enumerate(pieces, 1):
            xml = ENGINES[eng](piece, cfg_dir / eng)
            per_piece.setdefault(i, []).append(
                {"label": label, "engine": eng, "xml": xml, "qa": qa(str(xml) if xml else None)})

    best_dir = piece_dir / "best"
    best_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for idx in sorted(per_piece):
        cands = sorted(per_piece[idx], key=lambda c: c["qa"]["penalty"])
        print(f"{image.name} piece{idx:02d} — ranked:", file=sys.stderr)
        for c in cands:
            print(f"    {c['label']:24} QA {c['qa']['verdict']:5} pen={c['qa']['penalty']}",
                  file=sys.stderr)
        win = cands[0]
        dest = None
        if win["xml"]:
            dest = best_dir / f"{image.stem}_piece{idx:02d}{Path(win['xml']).suffix}"
            shutil.copyfile(win["xml"], dest)
        rendered = render(dest, best_dir) if (dest and args.render) else None
        print(f"  ⇒ winner: {win['label']} (pen={win['qa']['penalty']})", file=sys.stderr)
        results.append({"image": image.name, "piece": idx, "winner": win["label"],
                        "musicxml": str(dest) if dest else None,
                        "render": str(rendered) if rendered else None,
                        "qa": win["qa"],
                        "ranking": [{"config": c["label"], "penalty": c["qa"]["penalty"],
                                     "verdict": c["qa"]["verdict"]} for c in cands]})
    return results


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
    ap.add_argument("--check", action="store_true",
                    help="run structural QA on each result and print a verdict")
    ap.add_argument("--best", action="store_true",
                    help="try several engine/flag configs and keep the lowest-penalty one")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    engines = ["oemer", "audiveris"] if args.engine == "both" else [args.engine]

    results = []
    for image in args.images:
        if args.best:
            results += process_best(image, args)
        else:
            results += process_normal(image, args, engines)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    ok = sum(1 for r in results if r.get("musicxml"))
    print(f"\n{ok}/{len(results)} recognised", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
