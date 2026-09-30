# 099 — A named person is not a named place: clips for places, eras, objects and events in every style

## Type

AFK

## Parent PRD

`issues/prd.md`

## Why (root cause, not this reel)

Run05 had 21 of 26 beats `depicts: named_entity`, and one rule treats a person, place,
product, organisation and event alike: "never stock". So a person story can never show a
desert, an oil well, a palace, a 1950s plane or a city as footage. It is enforced in four
places: `picture_v19.md:89-91` and `:170`, `vishva.md:214`, `grammar.py:753-759` (hard),
and `assets/__init__.py:1227-1235` / `:1286-1290` (Pexels/Pixabay skipped, 14 times in
run05).

## What to build

- `depicts` separates **`named_person`** (a real, named human) from **`named_place`,
  `named_era`, `named_event`, `named_object`**. The old `named_entity` value is read as
  before for stored plans; new plans use the split. The contract, the fake plan and
  compare_plan follow.
- **Only `named_person` keeps the no-stock rule**: never a stock stranger, never AI (100).
  Places, eras, events and objects may take clips and stock stills.
- **Era judgement (operator taste, 30 Sep 2026):** for a `named_era` beat (or any beat
  with an era in its query), period-looking footage first (Commons / Openverse /
  archival). A timeless modern shot (desert, sea, sky, dunes) is fine and may take a light
  film/sepia grade (the grade is 102's). **Never** modern cars, skylines, phones or
  present-day clothes standing in for an old era; then a still. The clip judge is asked
  this per clip, like an editor, and its reason is logged.
- The grammar rule, the sourcing skips and the prompt text change together; the grammar
  keeps a hard violation for stock/AI on `named_person` only.

## Acceptance criteria

- [ ] A `named_place`/`named_era`/`named_event`/`named_object` beat planned as `clip`
      passes the grammar and reaches Pexels/Pixabay in the ladder (test with fakes).
- [ ] A `named_person` beat planned as `clip` is still a hard violation, and sourcing
      never gives it stock.
- [ ] A stored plan with `named_entity` loads and behaves exactly as before.
- [ ] The clip judge's prompt carries the era rule; a clip it refuses for "modern stands in
      for old" is logged with the reason and the beat falls to a still (no job failure).
- [ ] The prompt is a new version (`picture_v20.md`, shared with 110); older versions
      untouched.

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026 (run05 King Saud, job `20260930-042239-302dc9`, phone 6.5/10):
"Clips are used smartly in every style, person stories included (desert, oil wells,
palaces, 1950s planes, cities); a named person is still never shown as a stock stranger."
