# Recognition workflow & known limits

## Recommended flow
1. **Split first** (`--debug`), open `pieces/…_overlay.png`, confirm every piece
   was cut correctly. Re-run with `--pieces N` / `--min-gap PX` if a cut is wrong.
2. **Recognise** each piece with Audiveris (default) — best on printed
   multi-staff scores. Use `--engine both` to compare against oemer.
3. **Eyeball** the `_render.png` next to the source crop.
4. **Fix residual errors in MuseScore 4** (free): open the `.mxl`/`.musicxml`,
   play it back — wrong notes are easiest to catch by ear.

## Splitting: how boundaries are found
1. **Deskew** — photographed pages tilt a few degrees, which smears the row
   profile and breaks detection. The angle that sharpens the horizontal
   projection is found and the page rotated (`--no-deskew` to skip).
2. **Title detection** — a new piece starts at a *title*: a wide text block that
   follows staff content. Each content band is classified staff-vs-text (staff =
   long horizontal lines via morphology); a wide text band seen after staves is a
   title, and the cut goes in the whitespace just above it.

Why not "largest whitespace gap": on real pages the biggest gap is often above a
page number, and the gap between two systems of one multi-line piece can exceed
the gap before the next title. The title rule avoids both traps.

Overrides fall back to the whitespace-gap method: `--pieces N`, `--min-gap PX`.
Other tunables: `--scale`, `--pad`, `--no-deskew`.

## Known limits (be honest with the user)
- Even per-piece, both engines can mis-recognise a system: Audiveris may split a
  single piece into "movements" or pick a wrong clef; oemer may garble octaves on
  dense multi-staff layouts. Run `--engine both` and keep whichever render is
  cleaner. Verified example: on a 2-piece page one piece came out clean from
  Audiveris while the other needed oemer / manual fixes.
- Splitting is heuristic: a title very close to the preceding system, or a page
  with unusual layout, may need `--pieces N`. Always check the `_overlay.png`.
- Handwritten scores are out of scope — both engines target printed notation.
