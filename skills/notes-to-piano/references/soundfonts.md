# Piano soundfonts

`to_piano.py` auto-discovers the **largest** `.sf2`/`.sf3` in
`~/.local/share/notes-to-piano/soundfonts/` (richer sample sets are bigger), or
use `--soundfont PATH` to force one.

## Shipped by `setup.sh` (both CC-BY 3.0, from FreePats)

| SoundFont | Download | Size | Character |
|---|---|---|---|
| **YDP Grand Piano** *(default)* | `YDP-GrandPiano-SF2-20160804.tar.bz2` | ~37 MB | Yamaha Disklavier Pro; clean, light, fast to fetch |
| **Salamander Grand** (`setup.sh --salamander`) | `SalamanderGrandPiano-SF2-V3+20200602.tar.xz` | ~310 MB | Yamaha C5; deep, realistic, multi-velocity |

Source: <https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html>
License: **Creative Commons Attribution 3.0** — free for any use **with
attribution**. Credit FreePats / the original samplers when you publish audio.

## Other options (install manually, point `--soundfont` at them)

- **FluidR3_GM** — general-MIDI set with a usable acoustic grand (program 0);
  small, permissively licensed; often packaged as `fluid-soundfont-gm`.
- **soundfonts4u** (Nice-Steinway, SGM pianos) — good quality, **but the license
  is unverified**. A widely repeated claim that the collection is
  CC-BY-NC-SA could not be confirmed; do not assume non-commercial terms are the
  real license. Prefer the FreePats CC-BY pianos for anything you redistribute.

## Tips

- Bigger multi-velocity soundfonts (Salamander) react to `--humanize` far more
  musically than small ones, because velocity layers actually change timbre.
- If a render sounds too quiet/loud, adjust `--gain` (FluidSynth, 0..10) rather
  than normalizing twice.
