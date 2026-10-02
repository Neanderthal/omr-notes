#!/usr/bin/env python3
"""Shared staff splitter: a page/system image -> individual staff crops.

Used by BOTH the TrOMR wrapper and the pitch-fusion driver so the two engines see
the SAME staves (and therefore the same barlines -> measures line up for free).
Only needs cv2 + numpy, so it imports in any of the project venvs.
"""
import cv2
import numpy as np


def detect_staff_bands(gray):
    """Return [(y0, y1)] for each staff (a group of ~5 staff lines), top to bottom."""
    h, w = gray.shape
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, int(w * 0.3)), 1))
    lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hk)
    row = (lines.sum(axis=1) / 255.0) > w * 0.3
    ys = np.where(row)[0]
    if len(ys) == 0:
        return [(0, h)]
    centres, s, p = [], ys[0], ys[0]
    for r in ys[1:]:
        if r - p > 3:
            centres.append((s + p) // 2)
            s = r
        p = r
    centres.append((s + p) // 2)
    if len(centres) < 2:
        return [(0, h)]
    gaps = np.diff(centres)
    interline = float(np.median(gaps))
    staves, group = [], [centres[0]]
    for c, g in zip(centres[1:], gaps):
        if g > 2.5 * interline:      # big gap => next staff
            staves.append(group)
            group = [c]
        else:
            group.append(c)
    staves.append(group)
    pad = int(interline * 4)          # room for ledger lines / stems
    out = [(max(0, g[0] - pad), min(h, g[-1] + pad)) for g in staves if len(g) >= 3]
    return out or [(0, h)]


def staff_crops(color, scale=1.0, rgb_on_white=True):
    """Yield (index, y0, y1, crop_bgr) for each detected staff."""
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    for i, (y0, y1) in enumerate(detect_staff_bands(gray), 1):
        crop = color[y0:y1]
        if scale != 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_CUBIC)
        if rgb_on_white:
            crop = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT,
                                      value=(255, 255, 255))
        yield i, y0, y1, crop


def segment_widths(gray_staff, max_native_w):
    """Split a wide staff at the thinnest-ink columns so each piece <= max_native_w."""
    w = gray_staff.shape[1]
    if w <= max_native_w:
        return [(0, w)]
    _, bw = cv2.threshold(gray_staff, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    col_ink = bw.sum(axis=0)
    segs, start = [], 0
    while w - start > max_native_w:
        lo, hi = start + int(max_native_w * 0.6), start + max_native_w
        cut = lo + int(np.argmin(col_ink[lo:hi]))
        segs.append((start, cut))
        start = cut
    segs.append((start, w))
    return segs
