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
- Safe on clean scores: on the Minuet both engines agree → ~0 changes, QA stays PASS.
- Low agreement is handled: if a part's matched fraction is low, only the few
  well-aligned notes change (Audiveris pitches are otherwise kept). Always re-check
  with `check_musicxml.py` and eyeball the render.

## Known limits (v1)
- `staff_split` can merge two staves of a tightly-spaced grand staff into one —
  tune the gap threshold or crop per staff if that happens.
- Fusion helps where the two engines **agree on rhythm**; in passages where TrOMR's
  rhythm also diverges, few notes align and little changes.
- Does not fix octave (8va) errors or rhythm — pitches only.
- One Audiveris launch per system (~10 s startup) + TrOMR per staff → it's a
  targeted accuracy pass, not the fast default.
