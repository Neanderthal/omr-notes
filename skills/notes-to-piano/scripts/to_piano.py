#!/usr/bin/env python3
"""notes-to-piano — render a scanned score into piano audio.

Pipeline:  MusicXML/.mxl (or .mid)  ->  MIDI (music21)  ->  WAV (FluidSynth + SF2)
           ->  MP3 (ffmpeg).  Optional light dynamics humanization and tempo override.

Chains after the `omr-notes` skill, which produces the MusicXML this consumes.

Run under the skill venv (setup.sh builds it); the script re-execs into it
automatically if music21 is missing from the current interpreter.
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path.home() / ".local/share/notes-to-piano"
VENV_PY = DATA_DIR / "venv/bin/python"
SOUNDFONT_DIR = DATA_DIR / "soundfonts"

# ---- bootstrap: re-exec into the skill venv if music21 is unavailable ----
# (venv/bin/python is a symlink to the system python, so compare sys.prefix —
# the active environment — not the resolved binary path.)
try:
    from music21 import converter, tempo
except ImportError:
    _in_venv = Path(sys.prefix).resolve() == (DATA_DIR / "venv").resolve()
    if VENV_PY.exists() and not _in_venv:
        os.execv(str(VENV_PY), [str(VENV_PY), os.path.abspath(__file__), *sys.argv[1:]])
    sys.exit("music21 is not installed. Run scripts/setup.sh first.")


class RenderError(RuntimeError):
    """A step of the piano-render pipeline failed."""


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RenderError(f"required tool '{name}' not found on PATH — run scripts/setup.sh")
    return path


def find_soundfont(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise RenderError(f"soundfont not found: {p}")
        return p
    if SOUNDFONT_DIR.is_dir():
        fonts = sorted(
            [p for ext in ("*.sf2", "*.sf3") for p in SOUNDFONT_DIR.glob(ext)],
            key=lambda p: p.stat().st_size,
            reverse=True,  # prefer the richer (larger) soundfont
        )
        if fonts:
            return fonts[0]
    raise RenderError(
        "no piano soundfont found. Run scripts/setup.sh to download one, "
        "or pass --soundfont PATH."
    )


def humanize(score, seed: int, vel_jitter: int, timing_jitter: float) -> None:
    """Light, musical humanization: per-note velocity spread + micro-timing.

    Velocity variation is what the ear reads as 'played by a person'; a tiny
    onset jitter loosens the mechanical grid. Both are deliberately subtle.
    """
    rng = random.Random(seed)
    for n in score.recurse().notes:
        base = n.volume.velocity or 72
        n.volume.velocity = max(1, min(127, base + rng.randint(-vel_jitter, vel_jitter)))
        if timing_jitter:
            shift = rng.uniform(-timing_jitter, timing_jitter)
            n.offset = max(0.0, float(n.offset) + shift)


def to_midi(src: Path, out_mid: Path, args) -> None:
    """Convert the input score to a MIDI file (pass .mid through untouched
    unless we must edit it for tempo/humanization)."""
    is_midi = src.suffix.lower() in (".mid", ".midi")
    needs_edit = args.humanize or args.tempo
    if is_midi and not needs_edit:
        shutil.copyfile(src, out_mid)
        return

    score = converter.parse(str(src))
    if args.tempo:
        score.insert(0, tempo.MetronomeMark(number=args.tempo))
    if args.humanize:
        humanize(score, args.seed, args.vel_jitter, args.timing_jitter)
    score.write("midi", fp=str(out_mid))


def midi_to_wav(mid: Path, wav: Path, sf: Path, gain: float, sr: int) -> None:
    fluidsynth = require_tool("fluidsynth")
    cmd = [fluidsynth, "-ni", "-g", f"{gain}", "-r", str(sr),
           "-F", str(wav), str(sf), str(mid)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not wav.is_file() or wav.stat().st_size == 0:
        raise RenderError(f"fluidsynth failed:\n{proc.stderr.strip()}")


def wav_to_mp3(wav: Path, mp3: Path, normalize: bool) -> None:
    ffmpeg = require_tool("ffmpeg")
    cmd = [ffmpeg, "-y", "-i", str(wav)]
    if normalize:
        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    cmd += ["-codec:a", "libmp3lame", "-q:a", "2", str(mp3)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not mp3.is_file():
        raise RenderError(f"ffmpeg failed:\n{proc.stderr.strip()}")


def maybe_pdf(src: Path, pdf: Path) -> bool:
    """Best-effort score PDF. Uses MuseScore if present; otherwise skips."""
    for name in ("mscore", "musescore", "mscore4portable"):
        exe = shutil.which(name)
        if exe:
            runner = ["xvfb-run", "-a", exe] if shutil.which("xvfb-run") else [exe]
            proc = subprocess.run([*runner, str(src), "-o", str(pdf)],
                                  capture_output=True, text=True)
            return proc.returncode == 0 and pdf.is_file()
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a score (MusicXML/.mxl/.mid) to piano audio.")
    ap.add_argument("input", help="score file: .mxl, .musicxml, .xml or .mid")
    ap.add_argument("-o", "--outdir", default="piano_out", help="output directory")
    ap.add_argument("--soundfont", help="path to a .sf2/.sf3 (default: auto-discover)")
    ap.add_argument("--mp3", action="store_true", help="also encode an MP3 (needs ffmpeg)")
    ap.add_argument("--no-wav", action="store_true", help="delete the intermediate WAV after MP3")
    ap.add_argument("--normalize", action="store_true", help="loudness-normalize the MP3")
    ap.add_argument("--humanize", action="store_true", help="add subtle velocity + timing variation")
    ap.add_argument("--vel-jitter", type=int, default=12, help="velocity spread for --humanize")
    ap.add_argument("--timing-jitter", type=float, default=0.01,
                    help="max onset shift (quarterLengths) for --humanize")
    ap.add_argument("--seed", type=int, default=7, help="RNG seed for reproducible humanization")
    ap.add_argument("--tempo", type=float, help="override tempo in BPM")
    ap.add_argument("--gain", type=float, default=0.6, help="fluidsynth gain (0..10)")
    ap.add_argument("--sample-rate", type=int, default=44100, dest="sample_rate")
    ap.add_argument("--pdf", action="store_true", help="also export a score PDF (if MuseScore present)")
    args = ap.parse_args()

    src = Path(args.input).expanduser()
    if not src.is_file():
        print(f"input not found: {src}", file=sys.stderr)
        return 2

    stem = src.stem
    outdir = Path(args.outdir).expanduser() / stem
    outdir.mkdir(parents=True, exist_ok=True)
    mid, wav, mp3, pdf = (outdir / f"{stem}{e}" for e in (".mid", ".wav", ".mp3", ".pdf"))

    try:
        sf = find_soundfont(args.soundfont)
        print(f"soundfont: {sf.name}")
        to_midi(src, mid, args);                 print(f"✓ MIDI  → {mid}")
        midi_to_wav(mid, wav, sf, args.gain, args.sample_rate); print(f"✓ WAV   → {wav}")
        if args.mp3:
            wav_to_mp3(wav, mp3, args.normalize); print(f"✓ MP3   → {mp3}")
            if args.no_wav:
                wav.unlink(missing_ok=True)
        if args.pdf:
            print(f"✓ PDF   → {pdf}" if maybe_pdf(src, pdf)
                  else "… PDF   skipped (MuseScore not found)")
    except RenderError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"\nDone. Piano render in: {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
