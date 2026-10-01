# Correcting OMR output to PASS

Audiveris/oemer output is rarely perfect on photographed pages. This is the
path from a raw recognition to a structurally-clean score, using the bundled
tools. Work piece by piece.

```
recognise ──▶ QA check ──▶ auto-repair ──▶ re-check ──▶ (residual) MuseScore
 omr.py        check_      fix_omr.py       check_        hand-edit
 --best        musicxml                     musicxml
```

## 1. Recognise, picking the best run

```bash
python3 scripts/omr.py PAGE.jpg -o out --best --render
```
`--best` tries audiveris(±binarize ±dewarp) + oemer and keeps the lowest QA
penalty per piece. Different pieces may win with different configs.

## 2. Read the QA verdict

```bash
python3 scripts/check_musicxml.py out/PAGE/best/PAGE_piece01.mxl
```
- **PASS** (penalty < 8) — ship it (still eyeball the render).
- **WARN / FAIL** — read the issues; they tell you what to repair.

Common issues → cause:
| QA issue | Likely cause |
|---|---|
| parts start misaligned by ~N bars / parts recognised sequentially | staves not grouped as one system → re-run with `--dewarp` (fixes curvature that breaks grouping) |
| measures have wrong duration vs time signature | wrong meter, or Audiveris truncated the last beat of a bar |
| time signature not at bar 1 | header of the system misread |

## 3. Auto-repair (`fix_omr.py`)

Deterministic, scriptable equivalent of the usual MuseScore clean-up:

```bash
# Audiveris truncates the final beat of bars — extend them to fill:
python3 scripts/fix_omr.py piece.mxl piece_fixed.musicxml --fill

# wrong meter (e.g. a 3/4 lullaby read as 6/4): set it, re-barline, then fill:
python3 scripts/fix_omr.py piece.mxl piece_fixed.musicxml --ts 3/4 --rebar --fill
```
Pickups (anacrusis) are preserved. Re-check after:
```bash
python3 scripts/check_musicxml.py piece_fixed.musicxml
```

**What `--fill` is and isn't:** it makes a short bar *structurally* valid by
lengthening its last event — great when Audiveris merely clipped a final note
(very common, and usually correct). It is a heuristic, not transcription: always
compare the render to the original scan.

## 4. Worked results (kids' "Радуга" songbook)

| Piece | Raw QA | After repair | How |
|---|---|---|---|
| Божья коровка | WARN 32 | **PASS 0** | `--fill` (clipped melody tail) |
| Не летай, соловей | WARN 16 | **PASS 0** | `--fill` (one clipped piano bar) |
| Эстонская мелодия | WARN 24 | WARN 26 | needs bar-count fix (unequal systems) — MuseScore |
| Нинна, нанна | FAIL 136 | WARN 8 | `--ts 3/4 --rebar --fill` fixes the meter, but dropped bass beats + a merged bar leave a rebar artifact — **faithful finish needs MuseScore** |

## 5. When to stop scripting and open MuseScore

`--fill`/`--ts`/`--rebar` fix *structure*. When beats are genuinely missing
across many bars (dropped dots, merged bars, two systems of unequal length), a
deterministic repair can reach PASS but not a *faithful* score — the rhythm must
be re-read from the scan. That is the manual MuseScore step; there is no
shortcut that invents the right notes.
