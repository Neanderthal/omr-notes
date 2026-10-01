---
name: omr-notes
description: Recognise printed sheet-music photos/scans into editable MusicXML. Splits a page into one image per musical piece BEFORE OMR (so multiple songs on one page are not merged), then runs Audiveris and/or oemer. Use when the user has photos of notes/scores and wants MusicXML, MIDI, or a clean re-engraving.
---

# OMR — sheet music → MusicXML (with per-piece splitting)

OMR (Optical Music Recognition), not OCR. Turns photographed/scanned printed
scores into editable **MusicXML** for MuseScore.

**Why splitting matters:** both engines merge several pieces printed on one page
into a single score. This skill cuts the page at the large whitespace above each
title first, so every piece is recognised on its own.

## Quick start

```bash
# full pipeline: split -> recognise -> render check
python3 scripts/omr.py IMAGE.jpg -o OUTDIR --engine audiveris --render --debug

# let the skill pick the best recognition automatically (recommended for photos)
python3 scripts/omr.py IMAGE.jpg -o OUTDIR --best --render
```

Outputs under `OUTDIR/<image>/`:
- `pieces/…_pieceNN.png` — one image per detected piece (+ `_overlay.png` cut map with `--debug`)
- `audiveris/…_pieceNN.mxl` (or `oemer/…_pieceNN.musicxml`) — MusicXML per piece
- `…_render.png` — verovio render of the result, for eyeballing accuracy
- with `--best`: `best/…_pieceNN.(mxl|musicxml)` — the winning recognition per piece

## Quality gate (`--check`, `--best`)

OMR output can be structurally wrong in ways you won't hear until playback — the
classic one here: the melody staff and the piano grand staff get recognised
*sequentially* instead of together, so the voice is shifted by several bars.

- **`--check`** runs `check_musicxml.py` on each result and prints a verdict
  (`PASS`/`WARN`/`FAIL` + a penalty). It flags: parts not starting together,
  parts that barely overlap in time (sequential), measures whose duration ≠ the
  time signature, unequal measure counts, a time signature not at bar 1, and
  zero-length notes.
- **`--best`** runs several engine/flag configs (audiveris ±binarize ±dewarp,
  oemer ±binarize), scores each with the QA checker, and **keeps the lowest-penalty
  one** per piece into `best/`. This is how `--binarize --dewarp` was found to fix
  the shifted-voice bug on a real page (penalty 186 → 0). `--best` ignores
  `--engine`.

Run the checker standalone too:
```bash
python3 scripts/check_musicxml.py SCORE.mxl
```

## Repairing a WARN/FAIL (`fix_omr.py`)

`scripts/fix_omr.py` is a deterministic auto-repair — the scriptable half of the
usual MuseScore clean-up:
```bash
python3 scripts/fix_omr.py piece.mxl piece_fixed.musicxml --fill          # extend clipped bars
python3 scripts/fix_omr.py piece.mxl piece_fixed.musicxml --ts 3/4 --rebar --fill  # wrong meter
```
`--fill` extends short bars (Audiveris often truncates a bar's last beat),
`--ts`/`--rebar` fix a misread meter; pickups are preserved. It fixes *structure*,
not transcription — verify against the scan. The full path from raw recognition
to a clean score (with worked examples) is in
[`references/correction-workflow.md`](references/correction-workflow.md).

## Engine choice (tested findings)

- **audiveris** (default) — best structural fidelity on printed multi-staff
  scores; has a GUI editor for corrections. Needs decent resolution, so the
  splitter upscales crops 3× by default (`--scale`). Rejects tiny images.
- **oemer** — tolerant of raw phone photos, one `pip`, but garbles clefs/staves
  on complex layouts. Better on single-line melodies.
- **both** — run each and compare renders.

## Splitting controls

Auto-detection cuts above each *title* (a wide text block after staff content),
which is robust to page numbers and inter-system gaps. Override:
- `--pieces N` — force exactly N pieces
- `--min-gap PX` — a whitespace gap ≥ PX is a boundary
- `--no-split` — treat the whole image as one piece
- `--scale F` — upscale factor for crops (default 3.0)

Photo cleanup (help Audiveris on raw phone photos):
- `--binarize` — feed clean black-on-white crops (background-normalized + Otsu)
  instead of the raw colour photo. **This is usually what makes Audiveris accept a
  phone photo** (it fails with "No regularly spaced lines found" on low-contrast or
  tinted scans).
- `--dewarp` — flatten page *curvature* per piece (deskew only fixes tilt, not the
  bow of a photographed book page). Strip-wise profile cross-correlation; capped
  shift. Check `_render` after — on already-flat scans it's a no-op.

> If Audiveris still fails with "No regularly spaced lines found", first confirm the
> image actually contains staves (not a cover/title page) — that error also appears
> when there is simply no music on the page.

Always check `_overlay.png` (with `--debug`); re-run with an override if a cut is wrong.

Split-only (no OMR):
```bash
python3 scripts/split_pieces.py IMAGE.jpg -o OUTDIR --debug
```

## Setup / prerequisites

Run `scripts/setup.sh` once. It builds a venv at `~/.local/share/omr-notes/venv`
(numpy<2, onnxruntime==1.17.0, oemer, verovio, cairosvg, opencv) and installs
Audiveris (bundled JRE) to `~/.local/share/omr-notes/audiveris`. Details and the
version pitfalls are in `references/setup.md`. After OMR, fix residual errors in
**MuseScore 4** (`references/workflow.md`).
