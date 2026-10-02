#!/usr/bin/env python3
"""Deterministic auto-repair for common OMR mistakes — the scriptable equivalent
of the usual MuseScore clean-up, so a WARN/FAIL from check_musicxml.py can be
pushed toward PASS without hand-editing.

Fixes (opt-in):
  --ts A/B   replace the time signature (Audiveris often misreads e.g. 3/4 as 6/4)
  --rebar    re-barline each part from its note stream under the (new) time sig
  --fill     fill short non-pickup bars by extending their last note/rest to the
             bar length (Audiveris frequently truncates the final beat of a bar)

Pickups are preserved (measure 0, or a first/last pair summing to one bar).

    fix_omr.py IN.mxl OUT.musicxml [--ts 3/4] [--rebar] [--fill]

NOTE: --fill is a heuristic (it extends the last event). It makes a bar
*structurally* valid; verify pitches/rhythm against the original scan for a
performance-accurate score.
"""
import argparse
import sys

from music21 import converter, meter, note, stream


def set_timesig(score, ts_str):
    ts = meter.TimeSignature(ts_str)
    for p in score.parts:
        for old in list(p.recurse().getElementsByClass(meter.TimeSignature)):
            old.activeSite.remove(old)
        p.insert(0, meter.TimeSignature(ts_str))
    return ts


def rebar(score, ts_str):
    """Re-barline every part on a SHARED absolute timeline so bars stay vertically
    aligned across parts. Each note keeps its score-absolute offset (not a
    per-part re-pack, which shifts parts that start late or rest), and every part
    is padded to the common end so bar counts match.

    Note: this re-draws barlines faithfully to the source rhythm — it does not
    invent missing beats. If Audiveris dropped beats (a part ends early), run
    --fill as well (or fix the rhythm against the scan).
    """
    import copy
    collected, total = [], 0.0
    for p in score.parts:
        evs = []
        for m in p.getElementsByClass("Measure"):
            for n in m.notesAndRests:
                evs.append((m.offset + n.offset, copy.deepcopy(n)))  # absolute, reliable
        end = max((o + n.quarterLength for o, n in evs), default=0.0)
        total = max(total, end)
        collected.append((p.partName, evs, end))

    out = stream.Score()
    for name, evs, end in collected:
        np_ = stream.Part()
        np_.partName = name
        np_.insert(0, meter.TimeSignature(ts_str))
        for off, n in evs:
            np_.insert(off, n)
        if total - end > 0.01:                      # pad so all parts share bar count
            np_.insert(end, note.Rest(quarterLength=total - end))
        np_.makeMeasures(inPlace=True)
        np_.makeRests(fillGaps=True, inPlace=True)
        out.insert(0, np_)
    return out


def fill_short_bars(score):
    filled = 0
    for p in score.parts:
        ms = list(p.getElementsByClass("Measure"))
        if not ms:
            continue
        def content(m):
            return sum(n.quarterLength for n in m.notesAndRests)
        anacrusis = (len(ms) >= 2 and
                     abs(content(ms[0]) + content(ms[-1]) - ms[0].barDuration.quarterLength) < 0.01)
        for m in ms:
            if m.number == 0 or (anacrusis and m in (ms[0], ms[-1])):
                continue
            deficit = m.barDuration.quarterLength - content(m)
            if deficit <= 0.01:
                continue
            events = list(m.notesAndRests)
            if events:
                events[-1].quarterLength += deficit
            else:
                m.insert(0, note.Rest(quarterLength=m.barDuration.quarterLength))
            filled += 1
    return filled


def apply_octaves(score, spec):
    """Transpose measure ranges by whole octaves. spec: 'P:A-B:S[,...]' where P is a
    part index, A-B an inclusive measure-number range, S the octave shift (+1 = 8va,
    -1 = 8vb). For ottava lines the OMR engine missed."""
    parts = list(score.parts)
    shifted = 0
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        pstr, rng, sstr = item.split(":")
        p = int(pstr)
        a, b = (int(x) for x in rng.split("-"))
        semis = int(sstr) * 12
        if p >= len(parts):
            continue
        for m in parts[p].getElementsByClass("Measure"):
            if a <= m.measureNumber <= b:
                for n in m.notes:
                    n.transpose(semis, inPlace=True)
                    shifted += 1
    return shifted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--ts", help="replace time signature, e.g. 3/4")
    ap.add_argument("--rebar", action="store_true")
    ap.add_argument("--fill", action="store_true")
    ap.add_argument("--octave", help="apply ottava octave shifts, e.g. "
                    "'0:5-12:+1,1:5-12:+1' = part 0 & 1, measures 5-12, up an octave "
                    "(use -1 for 8vb). Fixes 8va lines OMR missed.")
    args = ap.parse_args()

    s = converter.parse(args.inp)
    if args.ts:
        set_timesig(s, args.ts)
    if args.rebar:
        if not args.ts:
            sys.exit("--rebar needs --ts A/B")
        s = rebar(s, args.ts)
    if args.octave:
        n = apply_octaves(s, args.octave)
        print(f"octave-shifted {n} note(s)", file=sys.stderr)
    if args.fill:
        n = fill_short_bars(s)
        print(f"filled {n} short bar(s)", file=sys.stderr)
    s.write("musicxml", fp=args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
