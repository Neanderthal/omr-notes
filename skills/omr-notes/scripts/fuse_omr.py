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


def audiveris_parts(color, scale, tmp):
    """Run Audiveris on the WHOLE system (its natural input) -> parts top-to-bottom."""
    up = cv2.resize(color, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    MAX = 18_000_000
    if up.shape[0] * up.shape[1] > MAX:
        f = (MAX / (up.shape[0] * up.shape[1])) ** 0.5
        up = cv2.resize(up, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    whole = str(tmp / "whole.png")
    cv2.imwrite(whole, up)
    a_dir = tmp / "audiveris"
    a_dir.mkdir(exist_ok=True)
    if AUDIVERIS.exists():
        run([AUDIVERIS, "-batch", "-export", "-output", a_dir, whole])
    mxls = sorted(Path(a_dir).glob("whole*.mxl"))
    if not mxls:
        return []
    try:
        return list(converter.parse(str(mxls[0])).parts)
    except Exception:
        return []


def tromr_parts(color, bands, tmp):
    """Run TrOMR per staff -> one part per staff (pitches)."""
    parts = []
    for i, (y0, y1) in enumerate(bands, 1):
        c = cv2.copyMakeBorder(color[y0:y1], 12, 12, 12, 12,
                               cv2.BORDER_CONSTANT, value=(255, 255, 255))
        png = str(tmp / f"staff{i:02d}.png")
        cv2.imwrite(png, c)
        parts.append(tromr_part(png, str(tmp / f"tromr{i:02d}.musicxml")))
    return parts


def _concat(parts):
    """Concatenate measures of several staff Parts (same role across systems)."""
    import copy
    out = stream.Part()
    num = 1
    for p in parts:
        if p is None:
            continue
        for m in p.getElementsByClass("Measure"):
            mm = copy.deepcopy(m)
            mm.number = num
            num += 1
            out.append(mm)
    return out if list(out.getElementsByClass("Measure")) else None


def fuse(a_parts, t_parts):
    """Overlay TrOMR pitches onto Audiveris parts by top-to-bottom order.

    Multi-system page: Audiveris gives P continuous parts, TrOMR gives one part per
    staff (P per system). Regroup TrOMR staves by role (staff i -> part i mod P) and
    concatenate, so each Audiveris part fuses with its full-length TrOMR counterpart.
    """
    P = len(a_parts)
    if P and len(t_parts) > P and len(t_parts) % P == 0:
        t_parts = [_concat([t_parts[j] for j in range(r, len(t_parts), P)])
                   for r in range(P)]

    out = stream.Score()
    for i in range(max(len(a_parts), len(t_parts))):
        a = a_parts[i] if i < len(a_parts) else None
        t = t_parts[i] if i < len(t_parts) else None
        if a is None and t is None:
            continue
        if a is None:
            print(f"  part {i + 1}: Audiveris missing — TrOMR only", file=sys.stderr)
            out.insert(0, t)
            continue
        if t is None:
            print(f"  part {i + 1}: TrOMR missing — Audiveris only", file=sys.stderr)
            out.insert(0, a)
            continue
        st = fuse_parts(a, t)
        if "skipped" in st:
            print(f"  part {i + 1}: SKIPPED ({st['skipped']}) — Audiveris kept",
                  file=sys.stderr)
        else:
            print(f"  part {i + 1}: agreement {st['agreement']:.0%}, "
                  f"{st['changed']}/{st['total']} pitch(es) changed", file=sys.stderr)
        out.insert(0, a)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--from-mxl", help="use this existing Audiveris MusicXML "
                    "instead of re-running Audiveris (e.g. omr.py's result)")
    ap.add_argument("--scale", type=float, default=3.0,
                    help="upscale for Audiveris when not using --from-mxl")
    args = ap.parse_args()

    color = cv2.imread(args.image)
    if color is None:
        sys.exit(f"cannot read {args.image}")
    bands = detect_staff_bands(cv2.cvtColor(color, cv2.COLOR_BGR2GRAY))
    print(f"staves: {len(bands)}", file=sys.stderr)
    tmp = Path(tempfile.mkdtemp(prefix="fuse_"))

    if args.from_mxl:
        try:
            a_parts = list(converter.parse(args.from_mxl).parts)
        except Exception as e:
            sys.exit(f"cannot read --from-mxl: {e}")
    else:
        a_parts = audiveris_parts(color, args.scale, tmp)
    print(f"Audiveris parts: {len(a_parts)}", file=sys.stderr)

    out_score = fuse(a_parts, tromr_parts(color, bands, tmp))
    out_score.write("musicxml", fp=args.out)
    print(args.out)


if __name__ == "__main__":
    sys.exit(main())
