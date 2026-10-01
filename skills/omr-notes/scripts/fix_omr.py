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
    out = stream.Score()
    for p in score.parts:
        flat = p.flatten().notesAndRests.stream()
        np_ = stream.Part()
        np_.insert(0, meter.TimeSignature(ts_str))
        for el in flat:
            np_.insert(el.offset, el)
        np_.makeMeasures(inPlace=True)
        np_.makeRests(fillGaps=True, inPlace=True)
        np_.partName = p.partName
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--ts", help="replace time signature, e.g. 3/4")
    ap.add_argument("--rebar", action="store_true")
    ap.add_argument("--fill", action="store_true")
    args = ap.parse_args()

    s = converter.parse(args.inp)
    if args.ts:
        set_timesig(s, args.ts)
    if args.rebar:
        if not args.ts:
            sys.exit("--rebar needs --ts A/B")
        s = rebar(s, args.ts)
    if args.fill:
        n = fill_short_bars(s)
        print(f"filled {n} short bar(s)", file=sys.stderr)
    s.write("musicxml", fp=args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
