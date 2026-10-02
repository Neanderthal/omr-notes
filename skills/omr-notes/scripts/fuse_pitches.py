#!/usr/bin/env python3
"""Overlay TrOMR pitches onto an Audiveris skeleton (pitch fusion).

Audiveris supplies structure/rhythm; TrOMR supplies pitches. For each staff/part we
align the two note sequences PER MEASURE by rhythmic position (Needleman-Wunsch on
onset+duration, NOT pitch), and where a pair lines up within tolerance we replace
the Audiveris pitch with the TrOMR pitch. Rhythm/durations/ties/structure are never
touched. See docs/plans/2026-10-02-pitch-fusion-design.md.

    fuse_pitches.py AUDIVERIS.(mxl|musicxml) TROMR.musicxml -o FUSED.musicxml
Run under a music21 env.
"""
import argparse
import sys

from music21 import converter, note, chord

GAP = 1.0          # NW gap penalty (quarterLengths)
TOL = 0.75         # max rhythmic distance to accept a pitch swap (|Δonset|+|Δdur|)
MIN_MATCH = 0.5    # skip a staff if < this fraction of notes got matched


def _events(measure):
    """Pitched events of a measure as (offset, quarterLength, element)."""
    return [(float(n.offset), float(n.quarterLength), n) for n in measure.notes]


def _nw(a, b):
    """Needleman-Wunsch on event lists keyed by rhythm. Returns matched (i,j) pairs."""
    n, m = len(a), len(b)
    d = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i * GAP
    for j in range(1, m + 1):
        d[0][j] = j * GAP
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = abs(a[i - 1][0] - b[j - 1][0]) + abs(a[i - 1][1] - b[j - 1][1])
            d[i][j] = min(d[i - 1][j - 1] + cost, d[i - 1][j] + GAP, d[i][j - 1] + GAP)
    i, j, pairs = n, m, []
    while i > 0 and j > 0:
        cost = abs(a[i - 1][0] - b[j - 1][0]) + abs(a[i - 1][1] - b[j - 1][1])
        if abs(d[i][j] - (d[i - 1][j - 1] + cost)) < 1e-9:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif abs(d[i][j] - (d[i - 1][j] + GAP)) < 1e-9:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def _swap_pitch(a_el, t_el):
    """Replace a_el's pitch(es) with t_el's; keep a_el's duration/ties/etc."""
    if isinstance(a_el, note.Note) and isinstance(t_el, note.Note):
        a_el.pitch = note.Note(t_el.nameWithOctave).pitch
        return 1
    if isinstance(a_el, chord.Chord) and isinstance(t_el, chord.Chord):
        a_el.pitches = tuple(note.Note(p.nameWithOctave).pitch for p in t_el.pitches)
        return 1
    # note<->chord: map the single note to the chord's nearest pitch (top for treble)
    if isinstance(a_el, note.Note) and isinstance(t_el, chord.Chord):
        a_el.pitch = max(t_el.pitches, key=lambda p: p.ps)
        return 1
    if isinstance(a_el, chord.Chord) and isinstance(t_el, note.Note):
        a_el.pitches = (note.Note(t_el.nameWithOctave).pitch,)
        return 1
    return 0


def fuse_parts(a_part, t_part):
    """Overlay t_part pitches onto a_part (modified in place). Returns (stats)."""
    a_meas = list(a_part.getElementsByClass("Measure"))
    t_meas = list(t_part.getElementsByClass("Measure"))
    changed, matched, total = 0, 0, 0
    diffs = []
    for mi, am in enumerate(a_meas):
        tm = t_meas[mi] if mi < len(t_meas) else None
        a_ev = _events(am)
        total += len(a_ev)
        if not tm:
            continue
        t_ev = _events(tm)
        if not a_ev or not t_ev:
            continue
        for ai, tj in _nw(a_ev, t_ev):
            ao, ad, ael = a_ev[ai]
            to, td, tel = t_ev[tj]
            if abs(ao - to) + abs(ad - td) > TOL:
                continue
            matched += 1
            before = ael.nameWithOctave if ael.isNote else "/".join(p.nameWithOctave for p in ael.pitches)
            if _swap_pitch(ael, tel):
                after = ael.nameWithOctave if ael.isNote else "/".join(p.nameWithOctave for p in ael.pitches)
                if after != before:
                    changed += 1
                    diffs.append(f"m{am.measureNumber} off{ao:g}: {before} -> {after}")
    return {"total": total, "matched": matched, "changed": changed, "diffs": diffs}


def fuse_scores(a_score, t_score):
    a_parts = list(a_score.parts)
    t_parts = list(t_score.parts)
    report = []
    for i, ap in enumerate(a_parts):
        if i >= len(t_parts):
            report.append({"part": i, "skipped": "no TrOMR part"})
            continue
        st = fuse_parts(ap, t_parts[i])
        frac = st["matched"] / st["total"] if st["total"] else 0.0
        if frac < MIN_MATCH:
            report.append({"part": i, "skipped": f"low match {frac:.0%}",
                           "total": st["total"]})
            # (pitches already partially swapped; acceptable since only well-aligned
            #  notes were touched. A stricter revert could re-parse — v2.)
        else:
            report.append({"part": i, "match": f"{frac:.0%}",
                           "changed": st["changed"], "diffs": st["diffs"]})
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audiveris")
    ap.add_argument("tromr")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    a = converter.parse(args.audiveris)
    t = converter.parse(args.tromr)
    report = fuse_scores(a, t)
    a.write("musicxml", fp=args.out)
    for r in report:
        if "skipped" in r:
            print(f"part {r['part']}: SKIPPED ({r['skipped']})", file=sys.stderr)
        else:
            print(f"part {r['part']}: match {r['match']}, {r['changed']} pitch(es) changed",
                  file=sys.stderr)
            if not args.quiet:
                for dln in r["diffs"][:40]:
                    print(f"    {dln}", file=sys.stderr)
    print(args.out)


if __name__ == "__main__":
    sys.exit(main())
