#!/usr/bin/env python3
"""Split a sheet-music page into one image per musical piece BEFORE OMR.

Both oemer and Audiveris merge multiple pieces printed on one page into a
single score. Cutting the page so each piece is its own image fixes that.

Pipeline: deskew (photos are often tilted, which smears the analysis) -> detect
titles -> cut above each title.

Detection (auto): a new piece starts at a *title* — a wide text block that
follows staff content. This ignores page numbers (too narrow) and, unlike a
"largest whitespace gap" rule, does not mis-fire on the gap before a page number
or on the gap between two systems of the same multi-line piece.

Usage:
    split_pieces.py IMAGE -o OUTDIR [--pieces N] [--min-gap PX]
                     [--scale 3.0] [--no-deskew] [--debug]

Overrides (switch to whitespace-gap method):
    --pieces N    force exactly N pieces (take the N-1 largest interior gaps)
    --min-gap PX  a gap >= PX is a boundary
    --scale F     upscale each crop by F (default 3.0; Audiveris needs ~300 DPI)
    --no-deskew   skip the deskew step
    --debug       also write <stem>_overlay.png showing the cut lines

Prints a JSON summary to stdout.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def estimate_skew(gray, limit=5.0, step=0.2):
    """Angle (deg) that makes staff lines horizontal = sharpest row profile.

    Photographed pages are often tilted a few degrees, which smears the
    horizontal-whitespace gaps the splitter relies on and can break the
    boundary detection entirely. Search a small angle range and pick the
    rotation maximising the sharpness of the row-ink profile.
    """
    small = cv2.resize(gray, None, fx=0.5, fy=0.5)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    h, w = bw.shape
    best_a, best_s = 0.0, -1.0
    for a in np.arange(-limit, limit + 1e-9, step):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(a), 1.0)
        rot = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        proj = rot.sum(axis=1, dtype=np.float64)
        score = float(((proj[1:] - proj[:-1]) ** 2).sum())
        if score > best_s:
            best_s, best_a = score, float(a)
    return best_a


def rotate(img, angle, border):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def _bands(mask, gap=10):
    """Group True rows of a boolean mask into (y0, y1) bands, merging gaps<=gap."""
    ys = np.where(mask)[0]
    if len(ys) == 0:
        return []
    out = []
    s = p = ys[0]
    for r in ys[1:]:
        if r - p > gap:
            out.append((int(s), int(p) + 1))
            s = r
        p = r
    out.append((int(s), int(p) + 1))
    return out


def detect_pieces_auto(gray, content_frac=0.015, staff_frac=0.15, title_frac=0.15):
    """Split by titles: a new piece starts at a wide text block (a title) that
    follows staff content. Robust to page numbers (too narrow) and to the large
    whitespace before a page number (only titles start pieces, not gaps).

    Returns (ranges, cuts).
    """
    h, w = gray.shape
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, int(w * 0.2)), 1))
    staff_row = (cv2.morphologyEx(bw, cv2.MORPH_OPEN, hk).sum(axis=1) / 255.0) > w * staff_frac
    content = (bw.sum(axis=1) / 255.0) > w * content_frac

    cbands = [b for b in _bands(content, gap=10) if b[0] > 2 and b[1] < h - 2]
    if not cbands:
        return [(0, h)], []

    cuts = []
    seen_staff = False
    prev_bottom = None
    for y0, y1 in cbands:
        is_staff = bool(staff_row[y0:y1].any())
        width = int((bw[y0:y1].sum(axis=0) > 0).sum())
        is_title = (not is_staff) and width > w * title_frac
        if is_staff:
            seen_staff = True
        elif is_title and seen_staff:
            cuts.append((prev_bottom + y0) // 2 if prev_bottom is not None else y0)
            seen_staff = False
        prev_bottom = y1

    # drop any cut not followed by staff content (stray footer text)
    staff_bands = _bands(staff_row, gap=12)
    cuts = [c for c in cuts if any(sb[0] >= c for sb in staff_bands)]

    top, bot = cbands[0][0], cbands[-1][1]
    edges = [top] + cuts + [bot]
    ranges = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    return ranges, cuts


def detect_pieces_gaps(gray, content_frac=0.015, pieces=None, min_gap=None):
    """Manual fallback: split on the largest vertical-whitespace gaps.
    Used only when --pieces or --min-gap is given."""
    h, w = gray.shape
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    content = (bw.sum(axis=1) / 255.0) > w * content_frac
    ys = np.where(content)[0]
    if len(ys) == 0:
        return [(0, h)], []
    top, bot = int(ys[0]), int(ys[-1])

    gaps = []
    i = top
    while i <= bot:
        if not content[i]:
            j = i
            while j <= bot and not content[j]:
                j += 1
            gaps.append([i, j, j - i])
            i = j
        else:
            i += 1
    interior = [g for g in gaps if g[2] >= 6]
    if not interior:
        return [(top, bot)], []

    if min_gap is not None:
        bounds = [g for g in interior if g[2] >= min_gap]
    else:
        n = max(0, (pieces or 1) - 1)
        bounds = sorted(sorted(interior, key=lambda g: -g[2])[:n])

    bounds = sorted(bounds)
    cuts = [(g[0] + g[1]) // 2 for g in bounds]
    edges = [top] + cuts + [bot]
    ranges = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    return ranges, cuts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, required=True)
    ap.add_argument("--pieces", type=int, default=None)
    ap.add_argument("--min-gap", type=int, default=None)
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--pad", type=int, default=8)
    ap.add_argument("--no-deskew", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    color = cv2.imread(str(args.image))
    if color is None:
        print(f"error: cannot read {args.image}", file=sys.stderr)
        return 1
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)

    angle = 0.0
    if not args.no_deskew:
        angle = estimate_skew(gray)
        if abs(angle) >= 0.2:
            color = rotate(color, angle, (255, 255, 255))
            gray = rotate(gray, angle, 255)
    h, w = gray.shape

    if args.pieces is not None or args.min_gap is not None:
        ranges, cuts = detect_pieces_gaps(gray, pieces=args.pieces,
                                          min_gap=args.min_gap)
    else:
        ranges, cuts = detect_pieces_auto(gray)
    args.outdir.mkdir(parents=True, exist_ok=True)
    stem = args.image.stem

    out = []
    for idx, (a, b) in enumerate(ranges, 1):
        y0 = max(0, a - args.pad)
        y1 = min(h, b + args.pad)
        crop = color[y0:y1]
        if args.scale and args.scale != 1.0:
            crop = cv2.resize(crop, None, fx=args.scale, fy=args.scale,
                              interpolation=cv2.INTER_CUBIC)
        name = args.outdir / f"{stem}_piece{idx:02d}.png"
        cv2.imwrite(str(name), crop)
        out.append({"index": idx, "file": str(name),
                    "src_rows": [y0, y1], "size": [crop.shape[1], crop.shape[0]]})

    if args.debug:
        ov = color.copy()
        for yc in cuts:
            cv2.line(ov, (0, yc), (w, yc), (0, 0, 255), 3)
        dbg = args.outdir / f"{stem}_overlay.png"
        cv2.imwrite(str(dbg), ov)

    print(json.dumps({"image": str(args.image), "pieces": len(ranges),
                      "skew_deg": round(angle, 2), "cuts": cuts, "outputs": out},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
