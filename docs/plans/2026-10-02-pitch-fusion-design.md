# Pitch fusion: Audiveris skeleton + TrOMR pitches

**Goal.** Improve note **accuracy on dense/low-res scans** by combining the two
engines' complementary strengths: Audiveris reads *structure* (parts, measures,
onsets, durations, ties) well but drifts on *pitches* in dense passages; TrOMR
(single-staff transformer) reads *pitches* better. Keep Audiveris as the only
source of structure/time and overlay TrOMR pitches where they can be trusted.

Scope: **pitches only.** No rhythm fusion, no 3-way voting (YAGNI for v1).

## Architecture / data flow

Common staff splitter feeds BOTH engines the SAME staff crops, so barlines line up
for free and Audiveris's grand-staff grouping problem disappears (we group staves
ourselves).

```
image ─► staff_split (shared) ─► [staff crops]
   per staff:  Audiveris (Java)   → rhythm/structure (skeleton)
               TrOMR (its venv)   → pitches
   per staff:  align per measure (same image → same bars) ─► swap pitches
   assemble staves → parts → fused.musicxml ─► check_musicxml + diff render
```

## Components

- `staff_split.py` — extract `detect_staves` (today in `tromr_omr.py`) into a shared
  module: page/system → individual staff images + top-to-bottom order.
- `fuse_pitches.py` (core, music21) — given two MusicXMLs of the SAME staff
  (Audiveris + TrOMR), align and overlay pitches → fused staff Part.
- `fuse_omr.py` (driver) — image → staff_split → per staff run Audiveris + TrOMR →
  `fuse_pitches` → assemble Score. Runs in the omr venv; calls TrOMR via subprocess
  (its own venv). Later: an `omr.py --fuse` wrapper.

## Alignment (within a measure)

Needleman–Wunsch on the two note sequences, scored by **rhythmic distance**, not
pitch (pitches are expected to differ):

1. note/chord → `(onset_in_measure, duration)`. Audiveris onsets are exact; TrOMR
   onsets = cumulative sum of its durations in the measure.
2. NW cost = `|Δonset| + |Δduration|`, with a gap penalty.
3. matched pair `(A,T)`: if rhythmic distance ≤ tolerance (onset within an eighth,
   duration ≈ equal) → **replace A.pitch ← T.pitch** (chord↔chord: swap the pitch
   set); else leave A untouched.
4. gaps (insert/delete) → leave Audiveris note as is.
5. if the two staff recognitions disagree on measure count → fall back to NW over
   the whole staff.

## Guardrails (never make it worse)

- Pitch only; rhythm/duration/ties/measures/structure untouched.
- Per staff: if matched fraction < 50 %, skip fusion for that staff (keep Audiveris).
- If Audiveris gives no output for a staff → fall back to TrOMR staff, or full-system
  Audiveris.
- Hard invariant: **fused QA penalty ≤ Audiveris QA penalty**, else revert.

## Reporting

- summary: pitches changed per staff/measure, match fraction.
- diff log: `staff 1, m6, note 3: A=C5 → T=E5`.
- `_diff_render.png` (before/after) + `check_musicxml.py` on the result.

## Testing

- unit (`fuse_pitches`): same rhythm/different pitches → all swapped; count mismatch
  → partial; onsets don't line up → 0 swaps.
- integration: **Minuet** (clean — fusion barely changes; both agree) and
  **Maikapar «Пастушок»** (dense — fixes some pitches); compare QA + render.
- regression: fused QA ≤ Audiveris QA.

## Not doing (v1)

Rhythm fusion · oemer 3-way voting · model-internal confidence (use rhythmic
agreement as the proxy) · multi-page auto.
