# Pitch fusion (Audiveris skeleton + TrOMR pitches)

Improves note accuracy on dense scans by keeping **Audiveris's structure/rhythm**
and overlaying **TrOMR's pitches** where the two line up. Design:
[`docs/plans/2026-10-02-pitch-fusion-design.md`](../../../docs/plans/2026-10-02-pitch-fusion-design.md).

## Use
```bash
# needs the Audiveris venv AND the TrOMR env (scripts/tromr_setup.sh)
python3 scripts/fuse_omr.py SYSTEM.png -o fused.musicxml --scale 2.0
```
Input is a **system** image (one or more grand-staff systems). The driver:
1. runs **Audiveris on the whole system** (its reliable input — per-staff is flaky);
2. runs **TrOMR per staff** (shared `staff_split.py` → the staves);
3. for each part, aligns the two note sequences **per measure** by rhythm
   (`fuse_pitches.py`, Needleman-Wunsch on onset+duration) and swaps a pitch only
   when the pair lines up within tolerance;
4. writes a fused multi-part MusicXML + prints a per-part diff.

Core converter alone (two MusicXMLs of the same staves):
```bash
python3 scripts/fuse_pitches.py AUDIVERIS.mxl TROMR.musicxml -o fused.musicxml
```

## Guarantees / behaviour
- **Pitch only** — rhythm/durations/ties/measures/structure are never touched.
- **Agreement gate (the key safety rule):** a part is only corrected when TrOMR
  already agrees with Audiveris on ≥ 80 % of the aligned notes. High agreement means
  TrOMR's read is trustworthy, so the few disagreements are credible corrections of
  Audiveris. Low agreement means TrOMR is unreliable *here* → the whole part is
  **skipped** and Audiveris is kept verbatim. (This is what makes blind fusion safe:
  a structural QA check can't tell a good pitch swap from a bad one, so we gate on
  cross-engine agreement instead.)
- Also skips a part when the two measure counts don't correspond.
- Net effect: on a clean page TrOMR disagrees too much → everything is skipped, no
  corruption; where Audiveris is mostly-right with a few pitch slips → those get
  fixed. `omr.py --fuse` additionally keeps the fused result only if QA is no worse.
  Still eyeball the render.

## Known limits (v1)
- `staff_split` auto-detects staves from their 5 lines. Tightly-spaced staves whose
  lines *are* found are now re-split (5-line chunking), but a **very dense staff**
  (continuous beamed runs / ottava) can obscure its own lines so it isn't detected
  at all — pass `--staves N` to `fuse_omr.py`/`tromr_omr.py` to force N equal bands.
- Fusion helps where the two engines **agree on rhythm**; in passages where TrOMR's
  rhythm also diverges, few notes align and little changes.
- Does not fix octave (8va) errors or rhythm — pitches only.
- One Audiveris launch per system (~10 s startup) + TrOMR per staff → it's a
  targeted accuracy pass, not the fast default.
