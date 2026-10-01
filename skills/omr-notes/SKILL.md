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
```

Outputs under `OUTDIR/<image>/`:
- `pieces/…_pieceNN.png` — one image per detected piece (+ `_overlay.png` cut map with `--debug`)
- `audiveris/…_pieceNN.mxl` (or `oemer/…_pieceNN.musicxml`) — MusicXML per piece
- `…_render.png` — verovio render of the result, for eyeballing accuracy

## Engine choice (tested findings)

- **audiveris** (default) — best structural fidelity on printed multi-staff
  scores; has a GUI editor for corrections. Needs decent resolution, so the
  splitter upscales crops 3× by default (`--scale`). Rejects tiny images.
- **oemer** — tolerant of raw phone photos, one `pip`, but garbles clefs/staves
  on complex layouts. Better on single-line melodies.
- **both** — run each and compare renders.

## Splitting controls

Auto-detection uses the largest "natural break" in vertical whitespace. Override:
- `--pieces N` — force exactly N pieces
- `--min-gap PX` — a whitespace gap ≥ PX is a boundary
- `--no-split` — treat the whole image as one piece
- `--scale F` — upscale factor for crops (default 3.0)

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
