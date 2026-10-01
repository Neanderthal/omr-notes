#!/usr/bin/env python3
"""Structural QA for recognized MusicXML — catch common OMR mistakes and score a
file so several OMR runs can be ranked automatically (lower penalty = better).

Checks (each adds penalty + an issue line):
  * parts don't start together  (→ "voice shifted by N bars")
  * parts play sequentially, not concurrently  (staves not grouped as one system)
  * measures whose real duration != the time signature  (misread barlines/rhythm)
  * staves/parts with different measure counts
  * time signature first appears after measure 1
  * zero-length notes

Run under the OMR/music21 venv. Prints a JSON report; exit 0 = PASS, 1 = issues.

    check_musicxml.py FILE.mxl [--json]
"""
import argparse
import json
import sys

from music21 import converter
from music21.meter import TimeSignature


def note_span(part):
    offs = [(n.getOffsetInHierarchy(part), n.quarterLength) for n in part.recurse().notes]
    if not offs:
        return None
    start = min(o for o, _ in offs)
    end = max(o + d for o, d in offs)
    return start, end


def check(path):
    s = converter.parse(path)
    parts = [p for p in s.parts]
    issues, penalty = [], 0.0

    tss = list(s.recurse().getElementsByClass(TimeSignature))
    bar_ql = tss[0].barDuration.quarterLength if tss else 4.0

    voiced = [(p, note_span(p)) for p in parts]
    voiced = [(p, sp) for p, sp in voiced if sp]

    # 1. parts start together?  Only a gap of a whole bar or more is a real fault
    #    — a 1–2 beat spread is normal (a pickup, or a bass that rests on the
    #    anacrusis), not the shifted-voice bug.
    starts = [sp[0] for _, sp in voiced]
    if len(starts) > 1:
        spread = max(starts) - min(starts)
        if spread >= bar_ql:
            bars = spread / bar_ql
            penalty += 50 + spread
            issues.append(f"parts start misaligned by {spread:g} beats (~{bars:g} bars)")

    # 2. sequential vs concurrent (pairwise temporal overlap)
    if len(voiced) > 1:
        worst = None
        for i in range(len(voiced)):
            for j in range(i + 1, len(voiced)):
                a, b = voiced[i][1], voiced[j][1]
                overlap = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
                shorter = min(a[1] - a[0], b[1] - b[0]) or 1.0
                frac = overlap / shorter
                worst = frac if worst is None else min(worst, frac)
        if worst is not None and worst < 0.25:
            penalty += 100
            issues.append(f"parts barely overlap in time ({worst:.0%}) — recognised "
                          f"sequentially, not as one system")

    # 3. measure duration vs its time signature — but a pickup (anacrusis) is
    #    legal: measure 0, a padded measure, or a first/last pair that together
    #    sum to one full bar.
    def content(m):   # actual beats present = notes + rests (a correct bar fills exactly)
        return sum(n.quarterLength for n in m.notesAndRests)

    bad_measures = 0
    for p in parts:
        ms = list(p.getElementsByClass("Measure"))
        if not ms:
            continue
        anacrusis_pair = (len(ms) >= 2 and
                          abs(content(ms[0]) + content(ms[-1])
                              - ms[0].barDuration.quarterLength) < 0.01)
        for m in ms:
            exp = m.barDuration.quarterLength
            if not m.notesAndRests or abs(content(m) - exp) <= 0.01:
                continue
            if m.number == 0:                       # explicit pickup bar
                continue
            if anacrusis_pair and m in (ms[0], ms[-1]):
                continue
            bad_measures += 1
    if bad_measures:
        penalty += 8 * bad_measures
        issues.append(f"{bad_measures} measure(s) have wrong duration vs time signature")

    # 4. equal measure counts across parts
    counts = [len(p.getElementsByClass("Measure")) for p in parts]
    if len(set(counts)) > 1:
        penalty += 10
        issues.append(f"parts have different measure counts: {counts}")

    # 5. time signature at measure 1?
    tss = list(s.recurse().getElementsByClass(TimeSignature))
    if tss:
        first_off = min(ts.getOffsetInHierarchy(s) for ts in tss)
        if first_off > 0:
            penalty += 15
            issues.append(f"time signature first appears at offset {first_off:g} (not bar 1)")
    else:
        penalty += 15
        issues.append("no time signature found")

    # 6. zero-length notes
    zeros = sum(1 for n in s.recurse().notes if n.quarterLength == 0)
    if zeros:
        penalty += 3 * zeros
        issues.append(f"{zeros} zero-length note(s)")

    verdict = "PASS" if penalty < 8 else ("WARN" if penalty < 80 else "FAIL")
    return {"file": path, "parts": len(parts), "penalty": round(penalty, 1),
            "verdict": verdict, "issues": issues}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true", help="machine-readable only")
    args = ap.parse_args()

    try:
        rep = check(args.file)
    except Exception as e:  # noqa: BLE001 — a crash is itself a quality signal
        rep = {"file": args.file, "penalty": 999, "verdict": "FAIL",
               "issues": [f"could not parse: {e}"]}

    if args.json:
        print(json.dumps(rep, ensure_ascii=False))
    else:
        print(f"{rep['file']}")
        print(f"  verdict: {rep['verdict']}  (penalty {rep['penalty']}, parts {rep.get('parts','?')})")
        for i in rep["issues"]:
            print(f"  ✗ {i}")
        if not rep["issues"]:
            print("  ✓ no structural issues found")
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
