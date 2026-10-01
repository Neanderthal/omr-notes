# omr-notes

**Optical Music Recognition (OMR) skill for [Claude Code](https://claude.com/claude-code).**
Turn photographed or scanned **printed sheet music** into editable **MusicXML**
for MuseScore — and from there to MIDI or a clean re-engraving.

> OMR, not OCR: it recognises staves, clefs, notes and rhythm, not text.

## Why this skill

Both OMR engines (Audiveris, oemer) **merge several pieces printed on one page**
into a single score. This skill **splits the page first** — cutting at the large
whitespace above each title — so every piece is recognised on its own. That alone
is the difference between usable output and a garbled mess on real songbook pages.

## Install

### As a Claude Code plugin (recommended)

```text
/plugin marketplace add Neanderthal/omr-notes
/plugin install omr-notes@omr-notes
```

### Manual (clone into your skills folder)

```bash
git clone https://github.com/Neanderthal/omr-notes.git
cp -r omr-notes/skills/omr-notes ~/.claude/skills/omr-notes
```

## One-time setup

The engines need a Python venv and Audiveris. Run once:

```bash
~/.claude/skills/omr-notes/scripts/setup.sh
```

It creates a venv at `~/.local/share/omr-notes/venv` (numpy<2, onnxruntime 1.17,
oemer, verovio, cairosvg, opencv) and installs Audiveris (bundled JRE) to
`~/.local/share/omr-notes/audiveris`. See
[`skills/omr-notes/references/setup.md`](skills/omr-notes/references/setup.md) for
version pitfalls.

## Quick start

```bash
# full pipeline: split -> recognise -> render check
python3 scripts/omr.py IMAGE.jpg -o OUTDIR --engine audiveris --render --debug
```

Outputs under `OUTDIR/<image>/`:

- `pieces/…_pieceNN.png` — one image per detected piece (+ `_overlay.png` cut map with `--debug`)
- `audiveris/…_pieceNN.mxl` (or `oemer/…_pieceNN.musicxml`) — MusicXML per piece
- `…_render.png` — a verovio render of the result, for eyeballing accuracy

### Engines

| Engine | Best for | Notes |
|---|---|---|
| **audiveris** (default) | printed multi-staff scores | best structural fidelity; GUI editor for fixes; needs resolution (crops upscaled 3×) |
| **oemer** | raw phone photos, single-line melodies | one `pip`; garbles clefs/staves on complex layouts |
| **both** | — | run each and compare renders |

### Splitting controls

- `--pieces N` — force exactly N pieces
- `--min-gap PX` — a whitespace gap ≥ PX is a boundary
- `--no-split` — treat the whole image as one piece
- `--scale F` — upscale factor for crops (default 3.0)

Always check `_overlay.png` (`--debug`) and re-run with an override if a cut is wrong.

After OMR, fix residual errors in **MuseScore 4** — see
[`skills/omr-notes/references/workflow.md`](skills/omr-notes/references/workflow.md).

## Repository layout

```
.claude-plugin/marketplace.json     # marketplace manifest
skills/omr-notes/
├── .claude-plugin/plugin.json      # plugin manifest
├── SKILL.md                        # the skill
├── scripts/                        # omr.py, split_pieces.py, render_musicxml.py, setup.sh
└── references/                     # setup.md, workflow.md
```

## License

MIT © Sergey Istomin. See [LICENSE](LICENSE).
