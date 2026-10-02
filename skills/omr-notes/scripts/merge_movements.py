#!/usr/bin/env python3
"""Merge the movement files Audiveris emits for one piece into a single score.

Audiveris splits a piece into separate scores/"movements" (file.mvt1.mxl,
file.mvt2.mxl, …) whenever it detects an indented system — which on a multi-system
page is usually just a new line of the SAME piece, not a new work. Taking only
mvt1 (as a naive "first output" would) drops most of the piece; this appends each
movement's measures onto the matching part so you get one continuous score.

    merge_movements.py OUT.musicxml IN.mvt1.mxl IN.mvt2.mxl [...]
"""
import copy
import sys

from music21 import converter, stream


def merge(paths):
    movements = [converter.parse(p) for p in paths]
    out = stream.Score()
    nparts = max(len(m.parts) for m in movements)
    for i in range(nparts):
        part = stream.Part()
        part.partName = next((m.parts[i].partName for m in movements
                              if i < len(m.parts)), f"P{i}")
        num = 1
        for m in movements:
            if i >= len(m.parts):
                continue
            for meas in m.parts[i].getElementsByClass("Measure"):
                nm = copy.deepcopy(meas)   # keep each bar intact (no re-flattening)
                nm.number = num
                num += 1
                part.append(nm)
        out.insert(0, part)
    return out


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: merge_movements.py OUT.musicxml IN.mvt1.mxl [IN.mvt2.mxl ...]")
    out_path, inputs = sys.argv[1], sys.argv[2:]
    merge(inputs).write("musicxml", fp=out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
