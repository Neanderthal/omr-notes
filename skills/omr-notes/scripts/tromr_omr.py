#!/usr/bin/env python3
"""TrOMR OMR pipeline (fallback engine): staff/system/page image -> MusicXML.

TrOMR is a SINGLE-STAFF recogniser. This wrapper:
  1. detects individual staves (groups of 5 staff lines) in the image,
  2. splits each staff into width-limited segments (at whitespace) so it fits the
     model's input, runs TrOMR on each and stitches the token streams,
  3. converts the semantic tokens of each staff to a music21 Part,
  4. stacks the parts into one Score and writes MusicXML.

Runs in the TrOMR venv (torch + the repo + music21).

    tromr_omr.py IMAGE -o OUT.musicxml [--staves N] [--debug]
"""
import argparse
import contextlib
import io
import os
import re
import sys
import tempfile

import cv2
import numpy as np

REPO = os.environ.get(
    "TROMR_REPO",
    os.path.expanduser("~/.local/share/tromr/Polyphonic-TrOMR/tromr"))
sys.path.insert(0, REPO)
from configs import getconfig          # noqa: E402
from staff2score import StaffToScore   # noqa: E402

from music21 import stream, note, chord, clef, key, meter   # noqa: E402

# ----------------------------- TrOMR model --------------------------------
class TrOMR:
    def __init__(self):
        cfg = getconfig(os.path.join(REPO, "workspace", "config.yaml"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.h = StaffToScore(cfg)
        self.max_w = cfg.max_width
        self.max_h = cfg.max_height

    def tokens(self, img_bgr):
        """Run TrOMR on a single-staff BGR image -> merged token string."""
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        # TrOMR's readimg wants 3- or 4-channel; give it clean RGB on white
        cv2.imwrite(tmp.name, img_bgr)
        with contextlib.redirect_stdout(io.StringIO()):
            rh, pi, li = self.h.predict(tmp.name)
        os.unlink(tmp.name)
        return _merge(rh[0], pi[0], li[0])


def _merge(predrhythm, predpitch, predlift):
    merge = predrhythm[0] + "+"
    for j in range(1, len(predrhythm)):
        if predrhythm[j] == "|":
            merge = merge[:-1] + "|"
        elif "note" in predrhythm[j]:
            lift = ""
            if predlift[j] in ("lift_##", "lift_#", "lift_bb", "lift_b", "lift_N"):
                lift = predlift[j].split("_")[-1]
            merge += predpitch[j] + lift + "_" + predrhythm[j].split("note-")[-1] + "+"
        else:
            merge += predrhythm[j] + "+"
    return merge[:-1]


# ----------------------------- staff detection -----------------------------
def detect_staves(gray, debug=False):
    """Return list of (y0, y1) crops, one per staff (group of 5 lines)."""
    h, w = gray.shape
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, int(w * 0.3)), 1))
    lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hk)
    row = (lines.sum(axis=1) / 255.0) > w * 0.3          # staff-line rows
    # centres of contiguous line runs
    centres = []
    ys = np.where(row)[0]
    if len(ys) == 0:
        return [(0, h)]
    s = p = ys[0]
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
    # a gap > 2.5x interline separates two staves
    staves, group = [], [centres[0]]
    for c, g in zip(centres[1:], gaps):
        if g > 2.5 * interline:
            staves.append(group)
            group = [c]
        else:
            group.append(c)
    staves.append(group)
    pad = int(interline * 4)                              # room for ledger lines
    out = []
    for g in staves:
        if len(g) < 3:                                   # not a real staff
            continue
        out.append((max(0, g[0] - pad), min(h, g[-1] + pad)))
    return out or [(0, h)]


# ----------------------------- width segmentation --------------------------
def segment_widths(gray_staff, max_native_w):
    """Split a wide staff into pieces <= max_native_w at the best whitespace gaps."""
    w = gray_staff.shape[1]
    if w <= max_native_w:
        return [(0, w)]
    _, bw = cv2.threshold(gray_staff, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    col_ink = bw.sum(axis=0)
    segs, start = [], 0
    while w - start > max_native_w:
        lo = start + int(max_native_w * 0.6)
        hi = start + max_native_w
        window = col_ink[lo:hi]
        cut = lo + int(np.argmin(window))               # thinnest ink column
        segs.append((start, cut))
        start = cut
    segs.append((start, w))
    return segs


# ----------------------------- tokens -> music21 ---------------------------
DUR = {"whole": 4.0, "half": 2.0, "quarter": 1.0, "eighth": 0.5, "sixteenth": 0.25,
       "thirty_second": 0.125, "thirtysecond": 0.125, "sixty_fourth": 0.0625}
CLEFS = {"G2": clef.TrebleClef, "F4": clef.BassClef, "C3": clef.AltoClef,
         "C4": clef.TenorClef, "F3": clef.BassClef}


def _dur(d):
    dots = 0
    while d.endswith("."):
        dots += 1
        d = d[:-1]
    base = DUR.get(d, 1.0)
    ql, add = base, base
    for _ in range(dots):
        add /= 2
        ql += add
    return ql


def _pitch(p):
    m = re.match(r"([A-Ga-g])(##|#|bb|b|N)?(-?\d+)", p.replace("note-", ""))
    if not m:
        return None
    acc = {"#": "#", "##": "##", "b": "-", "bb": "--", "N": "", None: ""}[m.group(2)]
    return f"{m.group(1).upper()}{acc}{m.group(3)}"


def find_timesig(token_strings):
    for s in token_strings:
        m = re.search(r"timeSignature-(\d+/\d+)", s)
        if m:
            return m.group(1)
    return None


def tokens_to_part(token_strings, forced_ts=None):
    """token_strings: list of per-segment token streams for ONE staff."""
    p = stream.Part()
    if forced_ts:
        try:
            p.append(meter.TimeSignature(forced_ts))
        except Exception:
            pass
    for si, s in enumerate(token_strings):
        for t in (x.strip() for x in s.strip().strip("[]'\"").split("+")):
            if not t:
                continue
            head = t.startswith
            if head("clef-"):
                if si == 0:
                    p.append(CLEFS.get(t[5:], clef.TrebleClef)())
            elif head("keySignature-"):
                if si == 0:
                    m = re.match(r"keySignature-([A-G][#b]?)([Mm])", t)
                    if m:
                        p.append(key.Key(m.group(1).replace("b", "-"),
                                         "major" if m.group(2) == "M" else "minor"))
            elif head("timeSignature-"):
                if si == 0 and not forced_ts:
                    try:
                        p.append(meter.TimeSignature(t.split("-", 1)[1]))
                    except Exception:
                        pass
            elif t == "barline":
                continue
            elif head("rest-") or head("nonote"):
                d = t.split("-")[-1] if "-" in t else t.split("_")[-1]
                p.append(note.Rest(quarterLength=_dur(d)))
            elif "note-" in t:
                names, ql = [], 1.0
                for voice in t.split("|"):
                    pd = voice.replace("note-", "")
                    i = pd.rfind("_")
                    nm = _pitch(pd[:i])
                    ql = _dur(pd[i + 1:])
                    if nm:
                        names.append(nm)
                if names:
                    el = note.Note(names[0]) if len(names) == 1 else chord.Chord(names)
                    el.quarterLength = ql
                    p.append(el)
    p.makeMeasures(inPlace=True)
    return p


# ----------------------------- pipeline ------------------------------------
def page_to_score(image_path, model, forced_staves=None, debug=False):
    color = cv2.imread(image_path)
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    bands = detect_staves(gray, debug)
    if forced_staves:
        # even split into N (fallback when detection is off)
        h = gray.shape[0]
        step = h // forced_staves
        bands = [(i * step, (i + 1) * step) for i in range(forced_staves)]
    print(f"staves detected: {len(bands)}", file=sys.stderr)
    # 1st pass: recognise every staff's tokens
    staff_tokens = []
    for (y0, y1) in bands:
        staff, gstaff = color[y0:y1], gray[y0:y1]
        max_native = int(10 * staff.shape[0])            # 128/h*w <= 1280  ->  w <= 10h
        toks = []
        for (x0, x1) in segment_widths(gstaff, max_native):
            seg = cv2.copyMakeBorder(staff[:, x0:x1], 10, 10, 10, 10,
                                     cv2.BORDER_CONSTANT, value=(255, 255, 255))
            toks.append(model.tokens(seg))
        staff_tokens.append(toks)
    # unify the time signature (per-staff reads can disagree) from the first staff
    ts = next((find_timesig(t) for t in staff_tokens if find_timesig(t)), None)
    score = stream.Score()
    for idx, toks in enumerate(staff_tokens, 1):
        part = tokens_to_part(toks, forced_ts=ts)
        print(f"  staff {idx}: {len(toks)} segment(s), "
              f"{len(list(part.recurse().notes))} notes", file=sys.stderr)
        score.insert(0, part)
    return score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--staves", type=int, default=None, help="force N equal staves")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    model = TrOMR()
    score = page_to_score(args.image, model, args.staves, args.debug)
    score.write("musicxml", fp=args.out)
    print(args.out)


if __name__ == "__main__":
    main()
