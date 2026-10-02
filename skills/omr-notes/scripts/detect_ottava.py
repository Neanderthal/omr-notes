#!/usr/bin/env python3
"""Best-effort ottava (8va/8vb) detector — SUGGESTS regions, never edits.

OMR engines routinely miss the dashed "8va" line above a staff, leaving those notes
an octave off. This scans the strip just above each staff for a long, broken
(dashed) horizontal line and prints a candidate x-range. YOU review it, map the
x-range to measure numbers, and apply the shift explicitly with
`fix_omr.py --octave 'PART:A-B:+1'` — so a false positive can never corrupt a score.

    detect_ottava.py IMAGE [--debug]
Run under a cv2/numpy env.
"""
import argparse
import sys

import cv2
import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from staff_split import detect_staff_bands   # noqa: E402


def find_ottava_above(gray, y0, y1):
    """Look in the strip above a staff for a dashed horizontal line. Returns
    (row_y, x0_frac, x1_frac, coverage) or None."""
    h, w = gray.shape
    sh = y1 - y0
    top = max(0, y0 - int(sh * 1.3))          # ~1.3 staff-heights above
    strip = gray[top:y0]
    if strip.shape[0] < 5:
        return None
    _, bw = cv2.threshold(strip, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    # join dashes into runs
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, int(w * 0.02)), 1))
    joined = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, hk)
    best = None
    for r in range(joined.shape[0]):
        cols = np.where(joined[r] > 0)[0]
        if len(cols) == 0:
            continue
        span = cols[-1] - cols[0]
        cover = len(cols) / max(1, span)       # dashed line: wide span, not 100% solid
        # a dashed ottava: spans a good chunk of width, broken (0.3<cover<0.95), thin
        if span > w * 0.12 and 0.25 < cover < 0.97:
            score = span * (0.6 if cover < 0.9 else 0.3)
            if best is None or score > best[4]:
                best = (top + r, cols[0] / w, cols[-1] / w, cover, score)
    if best:
        return best[0], best[1], best[2], best[3]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    color = cv2.imread(args.image)
    if color is None:
        sys.exit(f"cannot read {args.image}")
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    bands = detect_staff_bands(gray)
    print(f"staves: {len(bands)}", file=sys.stderr)
    found = 0
    for i, (y0, y1) in enumerate(bands):
        hit = find_ottava_above(gray, y0, y1)
        if hit:
            found += 1
            ry, x0f, x1f, cov = hit
            print(f"possible 8va above staff {i} (part {i}): "
                  f"x {x0f:.0%}-{x1f:.0%} of width (row y={ry}, coverage {cov:.0%})")
            print(f"    -> map that x-range to measures M-N, then: "
                  f"fix_omr.py IN OUT --octave '{i}:M-N:+1'")
    if not found:
        print("no ottava lines detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
