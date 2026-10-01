---
name: notes-to-piano
description: Render a scanned music score into realistic PIANO audio (WAV/MP3). Takes MusicXML/.mxl/.mid (e.g. the output of the omr-notes skill) and deterministically synthesizes it with FluidSynth + a CC-BY grand-piano soundfont — fully offline, no cloud. Optional dynamics humanization, tempo override, and score PDF. Use after omr-notes, or whenever the user wants to HEAR a MusicXML/MIDI score as piano.
---

# notes-to-piano — score → piano audio

Turns a notated score into **piano sound**. This is **deterministic rendering**
of the written notes (not composing new music). It pairs with
[`omr-notes`](../omr-notes/SKILL.md): OMR gives you MusicXML, this makes it audible.

```
omr-notes  →  score.mxl / .musicxml / .mid  →  [notes-to-piano]  →  score.mid + piano.wav/.mp3
```

Everything runs **offline** (FluidSynth + a local soundfont) — important where
cloud music/AI APIs are geo-blocked.

## Quick start

```bash
# one-time setup (venv + music21 + a CC-BY piano soundfont ~37 MB)
scripts/setup.sh                 # add --salamander for the 310 MB high-end piano

# render a score to MIDI + WAV + MP3
python3 scripts/to_piano.py SCORE.mxl -o OUTDIR --mp3
```

`to_piano.py` re-execs itself into the skill venv automatically, so plain
`python3` is fine.

Outputs under `OUTDIR/<stem>/`:
- `<stem>.mid` — MIDI (from music21)
- `<stem>.wav` — rendered piano audio (44.1 kHz stereo)
- `<stem>.mp3` — with `--mp3` (needs ffmpeg)
- `<stem>.pdf` — with `--pdf`, only if MuseScore is installed (else skipped)

## Pipeline

1. **MusicXML → MIDI** via **music21** (`.mid` input is passed straight through
   unless it must be edited for tempo/humanization).
2. **MIDI → WAV** via **FluidSynth** with a grand-piano SoundFont.
3. **WAV → MP3** via **ffmpeg** (`--mp3`), optionally loudness-normalized.

## Options

| Flag | Effect |
|---|---|
| `--mp3` | also encode MP3 (libmp3lame, `-q:a 2`) |
| `--no-wav` | delete the intermediate WAV after the MP3 |
| `--normalize` | EBU R128 loudness-normalize the MP3 |
| `--humanize` | subtle per-note velocity + micro-timing variation (less mechanical) |
| `--vel-jitter N` | velocity spread for `--humanize` (default 12) |
| `--timing-jitter Q` | max onset shift in quarterLengths (default 0.01) |
| `--seed N` | RNG seed — reproducible humanization (default 7) |
| `--tempo BPM` | override tempo |
| `--gain G` | FluidSynth gain 0..10 (default 0.6) |
| `--sample-rate HZ` | WAV sample rate (default 44100) |
| `--soundfont PATH` | use a specific `.sf2`/`.sf3` (default: auto-discover the richest one) |
| `--pdf` | also export a score PDF (MuseScore only) |

## Chaining after omr-notes

`omr-notes` writes `…_pieceNN.mxl`. Feed each piece in:

```bash
python3 ../notes-to-piano/scripts/to_piano.py \
    OUTDIR/<image>/audiveris/<image>_piece01.mxl -o audio --mp3 --humanize
```

Verify by **listening** to the MP3, and cross-check against the `omr-notes`
`_render.png`. If a wrong note jumps out, fix it in MuseScore (see the omr-notes
workflow) and re-render.

## Soundfonts & licensing

Default download is the **YDP Grand Piano** (Yamaha Disklavier Pro, ~37 MB,
**CC-BY 3.0**). `scripts/setup.sh --salamander` fetches the larger, more
realistic **Salamander Grand** (~310 MB, **CC-BY 3.0**). Both need attribution.
Details and other options: `references/soundfonts.md`.

## Prerequisites

- System: `fluidsynth`, `ffmpeg` (setup checks and tells you how to install).
- `scripts/setup.sh` builds a venv at `~/.local/share/notes-to-piano/venv`
  (music21) and drops the soundfont in `~/.local/share/notes-to-piano/soundfonts`.
- Optional: MuseScore for `--pdf`. Not required for audio.
