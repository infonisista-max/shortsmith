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

- [x] A `named_place`/`named_era`/`named_event`/`named_object` beat planned as `clip`
      passes the grammar and reaches Pexels/Pixabay in the ladder (test with fakes).
- [x] A `named_person` beat planned as `clip` is still a hard violation, and sourcing
      never gives it stock.
- [x] A stored plan with `named_entity` loads and behaves exactly as before.
- [x] The clip judge's prompt carries the era rule; a clip it refuses for "modern stands in
      for old" is logged with the reason and the beat falls to a still (no job failure).
- [x] The prompt is a new version (`picture_v20.md`, shared with 110); older versions
      untouched.

## Done note

- Contract: `Depicts` adds `named_person`, `named_place`, `named_era`, `named_event`,
  `named_object`; `named_entity` stays valid and is read exactly as before
  (`contracts.py:229`, `NAMED_DEPICTS` `:238`, `Era` `:241`). `JudgeVerdict` carries
  `era` and `why` (`contracts.py:992`), so the chosen asset's era verdict sits on
  `AssetRecord.judge` for 102 to read (`timeless` = the one to grade).
- One set of helpers in `assets/generate.py`: `never_stock` (`:188`, `named_person` or
  legacy `named_entity`, incl. an unlabelled entity beat), `is_named` (`:182`),
  `is_era` (`:195`, `named_era` or a year / decade / century / age word in the query,
  `_ERA` `:167`). 100's `names_a_person` (`:175`) is unchanged in logic: only
  `named_person`, or legacy `named_entity` on a non-concept beat; the split place / era
  / event / object values are never a person, so they may be generated as the last rung
  (illustration template, `:213`; T9 now fails any named value rendered photoreal,
  `rights.py:182`).
- Grammar: the hard 4.1 clip violation is `never_stock` only (`grammar.py:756`).
- Sourcing (`assets/__init__.py`): stock skip `:1255`, clip refusal `:1313`, planned
  clip reuse `:1467` and the replaced-beat named ladder `:1379` read `never_stock`;
  entity matching / name evidence read `is_named` (`:1006`, `:1197`, `:1266`).
- Era rule: the judge's system prompt carries it (`assets/judge.py:82`), an era beat's
  request adds the `Era beat: yes` line (`:233`), the reply's `era` / `why` are parsed,
  a `modern` verdict is never accepted (`:115`, reason `modern_for_era` `:65`), era
  verdicts are cached apart (`:432`). `clip_found` runs two passes on an era beat with a
  judge (`assets/__init__.py:1346`): period only (`:795`), then period or timeless;
  each modern refusal is a `sourcing: bNN: <url> refused: modern stands in for the era
  (<why>) (099)` line (`:790`); no clip left -> the still ladder, no failure.
- Prompt v20 (`planner/prompt.py:49`, `:118`): `picture_v20.md` = v19 + the named-person
  bullet (`:90`), clips for places / eras / events / objects with the three examples,
  the era rule (`:98`) and the `depicts` split (`:197`); `sound_v20.md` = v19's text.
  v19 files untouched. Snapshots recorded (`tests/fixtures/planner/*_v20.snapshot.md`).
- Fake plan: b02 India Gate is `named_place` (`planner/fake.py:332`); the recorded CLI /
  API replies follow. `compare_plan` / `examples.plan_match` count every named value
  (`reference/examples.py:238`); the editor and change box read `is_named` /
  `NAMED_DEPICTS` (`editor/__init__.py:250`, `editor/change.py:452`).
- Styles: the clip prose in all seven specs (explainer:211, fastfacts:216, footage:213,
  vishva:214, animated:180, educational:180, hitech:194) now says places / eras / events
  / objects may take clips, never a named person, plus the era rule; versions bumped
  (explainer 21, educational 19, animated 19, hitech 20, recipes 11) and pinned.
- Tests: `tests/test_named_split.py` (41). `test_never_ai_person` replaced-person test:
  a `named_person` now takes the named ladder and never reaches the generator door.
- For 102: read `record.judge.era` (`timeless` -> the light film / sepia grade). For
  110: extend `picture_v20.md`. Not done: Commons / Openverse have no video source, so
  "period first" among clips ranks the stock clips; archival stills come from the
  still ladder (web, Commons, Openverse). The `assets/__init__.py` module docstring
  (lines 20-35) still words the rule as "a named entity".

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026 (run05 King Saud, job `20260930-042239-302dc9`, phone 6.5/10):
"Clips are used smartly in every style, person stories included (desert, oil wells,
palaces, 1950s planes, cities); a named person is still never shown as a stock stranger."
