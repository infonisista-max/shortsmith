# 110a — The creative-editor section in the picture prompt, and worked examples across styles

## Type

AFK. The first of three parts of the old 110 (split 1 Oct 2026 under the context-budget
rule). The causes and the operator's words are in `issues/done/110-the-planner-edits-like-a-creative-human.md`.

## Parent PRD

`issues/prd.md`

## What to build

- **The creative-editor section in `picture_v20.md`** (099 created it, and 103, 102 and
  107-109 each added a vocabulary line; bump to v21 only if the repo's version rule
  requires it for this size of change):
  - For each script the planner reads the story and chooses from the **full vocabulary**,
    listed in one place:
    - clips for places, eras, objects and events (099);
    - the picture treatments photo / crop_fill / backdrop / polaroid / card (103);
    - the camera moves (102);
    - every transition, light_flare included (107);
    - text treatments: stamp, text_pop, banner, bubble, lower_third, calendar (107, 108);
    - maps with the highlight, target circle and tag (104); counters and charts;
      overlays (particles, 109);
    - pacing changes: a burst of short beats against a held beat.
  - It plans as a human editor would: what this line needs, what the previous two beats
    did, and what would surprise without distracting. It **varies**, so no two reels feel
    like one template, and says in each beat's `why` what it chose and why.
  - **Operator taste (30 Sep 2026), verbatim intent:** moving footage is a range, not a
    rule. The planner decides per script how much really fits. The low end is a target,
    never a gate: short of good clips → stills, a logged reason, delivered. It never
    forces a bad clip to hit a number. The same picture treatment never runs back to back.
  - Remove the narrow clip examples ("cheese", "the sun", "a busy market") and the
    "opening is a clip only for a concept" limit, if 099 left them.
- **Worked examples across styles** (`reference/examples.py:102`): when fewer than 2
  own-style examples show footage, `examples.select` adds a Tier A card from another
  style on a near topic, labelled as a vocabulary example, not a style example.
- The fake planner, `fixture.smoke_specs` and the prompt snapshot follow.

## Acceptance criteria

- [x] The prompt section is present; the snapshot test is updated; the smoke is green.
- [x] `examples.select` cross-style fill tested (a vishva job gets a footage example).
- [x] The prompt's own examples cover place, era, object and event clips.

## Blocked by

099, 102, 103, 104, 107, 108, 109.

## Done note (1 Oct 2026)

- Version: v20 extended in place, not bumped - the v20 comment already said "110 extends it"
  and 107-109 added their vocabulary paragraphs to v20 the same way; the change is recorded
  in `src/shortsmith/planner/prompt.py:55`.
- Prompt: "The creative editor (the standing rule for every job)" opens How to plan
  (`src/shortsmith/planner/prompts/picture_v20.md:16-46`, before the speaker's-order rule
  at `:48`): read the story, then for each line what it needs / what the previous two
  beats did / a surprise that does not distract; vary so no two reels feel like one
  template; one-line `why` per beat. The full vocabulary in one place: clips with the
  prompt's own place / era / object / event examples ("desert dunes at dusk", "an old
  Arabian palace"; "a 1950s oil field"; "an oil tanker at sea"; "a plane taking off",
  "a rocket launch"), the five treatments, the nine camera moves, all eight transitions
  (light_flare incl.), stamp / text_pops / banner / bubbles / lower_third / calendar, the
  map with highlight / circle / tag, counter, chart, particles and stickers, and pacing
  (a burst of short beats against a held beat - the NKB reference runs 0.68 s to long
  held beats, mean 2.31 s, docs/reference/README.md). Operator taste as written: footage a
  range, not a rule, decided per script within `broll.clip_max_fraction`; the low end a
  target, never a gate (a still with a logged reason, delivered); never force a bad clip;
  a missing clip never fails the job; the same picture treatment never runs back to back
  (also in Picture treatments, `:139`); a named person never a stock stranger and never AI.
- Removed: the "cheese" / "the sun" / "a busy market" concept-only clip case (now `:147`:
  wherever footage shows the line better, in every style, the opening too) and the
  "opening is a clip only for a concept" limit (now `:88`: any subject but a named person).
- Contract: `Beat.why` (`src/shortsmith/contracts.py:577`, in the reply schema);
  `WorkedExample.vocabulary` (`:152`).
- Cross-style examples (`src/shortsmith/reference/examples.py:109-140`): `select` takes the
  own-style pick as before; when fewer than `FOOTAGE_EXAMPLES_MIN` (2, `:58`) of it
  `shows_footage` (a `full_footage` beat or a `moving_footage` shot, `:129`), it adds one
  Tier A card of another style (`is_vocabulary`, `:136`) that shows footage, the job's
  topic first, else any, then by id. `for_job` reads `all_references` (`:208`) and marks
  it; `section` prints `VOCABULARY_NOTE` (`:230`) and heads it "Vocabulary example"
  ("a vocabulary example, not a style example"). On the real library a vishva history job
  now gets FbaBcWgMIEY, ePTZVwipoAM + id00R-3OmJ0 (Tier A history, 172 s of footage).
- Fake planner: `FAKE_WHY` on every beat (`src/shortsmith/planner/fake.py:290`, `:418`);
  the recorded CLI / API replies carry the same `why`. `fixture.smoke_specs` needed no
  change (no number moved; the smoke judges the same plan). Snapshots re-recorded
  (`tests/fixtures/planner/picture_v20.snapshot.md`, `sound_v20.snapshot.md`).
- Tests: `tests/test_creative_editor.py` (15); `test_worked_examples` (a vishva select now
  gets the footage card) and `test_planner_prompt` (the opening-clip needle) follow.
- Loops: ruff, pyright clean; pytest in chunks, every file (681 + 557 + 488 + 289 + 352 +
  13 + 7 + 111 passed); `shortsmith.smoke` delivered, T1-T13 pass. src/remotion untouched.
- Left for 110b / 110c: `clip_share_target` and the variety numbers in front matter, the
  soft rules, vishva re-derived, the variety line.
