#!/usr/bin/env python3
"""Pitch-fusion driver: image -> (per staff) Audiveris skeleton + TrOMR pitches
-> fused multi-part MusicXML. See docs/plans/2026-10-02-pitch-fusion-design.md.

Runs in the omr venv (music21 + cv2); calls Audiveris (Java) and the TrOMR wrapper
(its own venv) per staff via subprocess.

    fuse_omr.py IMAGE -o FUSED.musicxml [--scale 3.0]

Env overrides: OMR_AUDIVERIS, TROMR_PY (TrOMR venv python), TROMR_OMR (tromr_omr.py).
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
from music21 import converter, stream

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from staff_split import detect_staff_bands                    # noqa: E402
from fuse_pitches import fuse_parts                           # noqa: E402

OMR_HOME = Path(os.environ.get("OMR_HOME", Path.home() / ".local/share/omr-notes"))
AUDIVERIS = Path(os.environ.get("OMR_AUDIVERIS", OMR_HOME / "audiveris/bin/Audiveris"))
TROMR_PY = Path(os.environ.get("TROMR_PY", Path.home() / ".local/share/tromr/venv/bin/python"))
TROMR_OMR = Path(os.environ.get("TROMR_OMR", HERE / "tromr_omr.py"))


def run(cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True)


def tromr_part(png, out_xml):
    """TrOMR on one staff image -> its (single) Part, or None."""
    r = run([TROMR_PY, TROMR_OMR, png, "-o", out_xml])
    if r.returncode != 0 or not Path(out_xml).exists():
        print(r.stderr[-300:], file=sys.stderr)
        return None
    try:
        sc = converter.parse(out_xml)
        return sc.parts[0] if sc.parts else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--scale", type=float, default=3.0,
                    help="upscale staff crops for Audiveris (default 3.0)")
    args = ap.parse_args()

    color = cv2.imread(args.image)
    if color is None:
        sys.exit(f"cannot read {args.image}")
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    bands = detect_staff_bands(gray)
    print(f"staves: {len(bands)}", file=sys.stderr)
    tmp = Path(tempfile.mkdtemp(prefix="fuse_"))

    # 1) Audiveris on the WHOLE system (its natural input — per-staff is unreliable);
    #    parts come out top-to-bottom, matching the staff order.
    up = cv2.resize(color, None, fx=args.scale, fy=args.scale,
                    interpolation=cv2.INTER_CUBIC)
    MAX = 18_000_000
    if up.shape[0] * up.shape[1] > MAX:
        f = (MAX / (up.shape[0] * up.shape[1])) ** 0.5
        up = cv2.resize(up, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    whole = str(tmp / "whole.png")
    cv2.imwrite(whole, up)
    a_dir = tmp / "audiveris"
    a_dir.mkdir()
    run([AUDIVERIS, "-batch", "-export", "-output", a_dir, whole]) if AUDIVERIS.exists() else None
    a_parts = []
    mxls = sorted(Path(a_dir).glob("whole*.mxl"))
    if mxls:
        try:
            a_parts = list(converter.parse(str(mxls[0])).parts)
        except Exception:
            a_parts = []
    print(f"Audiveris parts: {len(a_parts)}", file=sys.stderr)

    # 2) TrOMR per staff (pitches)
    t_parts = []
    for i, (y0, y1) in enumerate(bands, 1):
        crop = color[y0:y1]
        c = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT,
                               value=(255, 255, 255))
        png = str(tmp / f"staff{i:02d}.png")
        cv2.imwrite(png, c)
        t_parts.append(tromr_part(png, str(tmp / f"tromr{i:02d}.musicxml")))

    # 3) fuse by order: Audiveris part i  <-  TrOMR pitches of staff i
    out_score = stream.Score()
    n = max(len(a_parts), len(t_parts))
    for i in range(n):
        a_part = a_parts[i] if i < len(a_parts) else None
        t_part = t_parts[i] if i < len(t_parts) else None
        if a_part is None and t_part is None:
            continue
        if a_part is None:
            print(f"  part {i + 1}: Audiveris missing — TrOMR only", file=sys.stderr)
            out_score.insert(0, t_part)
            continue
        if t_part is None:
            print(f"  part {i + 1}: TrOMR missing — Audiveris only", file=sys.stderr)
            out_score.insert(0, a_part)
            continue
        st = fuse_parts(a_part, t_part)
        frac = st["matched"] / st["total"] if st["total"] else 0.0
        tag = "" if frac >= 0.5 else "  (low match — pitches mostly kept)"
        print(f"  part {i + 1}: match {frac:.0%}, {st['changed']}/{st['total']} "
              f"pitch(es) changed{tag}", file=sys.stderr)
        out_score.insert(0, a_part)

    out_score.write("musicxml", fp=args.out)
    print(args.out)


if __name__ == "__main__":
    sys.exit(main())
