# TrOMR fallback engine

A **transformer, single-staff** OMR ([NetEase/Polyphonic-TrOMR](https://github.com/NetEase/Polyphonic-TrOMR))
used as a **backup** when Audiveris/oemer get the *pitches* wrong on a staff —
e.g. dense passages on a modest scan. Pretrained weights ship inside the repo, so
(unlike some research models) it loads cleanly and produces coherent output.

## When to reach for it
- Audiveris recognised the structure but a staff's **notes are wrong** and you
  want a second opinion on that line.
- A single melody/staff line you just want transcribed accurately.

It is **not** a drop-in replacement for the main pipeline: it reads one staff at a
time, so a grand staff is recognised staff-by-staff and the parts may not bar-align
perfectly (each staff is decoded independently). Treat its output as a per-staff
pitch source to cross-check or stitch, not a finished score.

## Setup (own env — separate from the Audiveris/oemer venv)
```bash
scripts/tromr_setup.sh          # clones the repo (+ bundled weights) and builds
                                # a venv at ~/.local/share/tromr
```
Needs Python 3.8–3.10 (old pinned deps). The repo pins torch 1.11, which won't load
on modern kernels, so setup installs torch 2.4.1 (runs the checkpoint fine).

## Use
```bash
~/.local/share/tromr/venv/bin/python scripts/tromr_omr.py IMAGE.png -o OUT.musicxml
```
`IMAGE.png` is a single staff **or** a grand-staff system (3-channel RGB on white —
grayscale is rejected by TrOMR's reader). The wrapper:
1. detects individual staves (5-line groups),
2. splits each staff into width-limited segments at whitespace (TrOMR caps input
   width), runs TrOMR on each and stitches the tokens,
3. converts the semantic tokens to a music21 Part, unifying the time signature
   across staves,
4. writes a multi-part MusicXML.

Then QA / render / play it like any other MusicXML
(`check_musicxml.py`, `notes-to-piano`).

## How it did on our tests
- **Minuet in G (clean typeset), treble staff** — exact: `clef-G2 keySig-GM 3/4`,
  melody notes correct.
- **Grand-staff system** — treble correct; bass approximate; parts don't bar-align
  (independent per-staff decode). Good as a pitch cross-check, needs manual stitch
  for a clean score.
- **Maikapar «Пастушок» (dense scan)** — coherent attempt, some errors (missed a key
  sharp, dense 16ths) — still a useful second opinion where Audiveris drifts.

## Token format (for reference)
`clef-G2 + keySignature-GM + timeSignature-3/4 + note-D5_quarter + rest-quarter +
barline + chord: note-C5_quarter|note-E5_quarter`. Pitch carries its accidental
(`note-F5#`), duration may be dotted (`eighth.`). `tromr_omr.py` parses all of this.
