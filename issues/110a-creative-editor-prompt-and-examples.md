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

- [ ] The prompt section is present; the snapshot test is updated; the smoke is green.
- [ ] `examples.select` cross-style fill tested (a vishva job gets a footage example).
- [ ] The prompt's own examples cover place, era, object and event clips.

## Blocked by

099, 102, 103, 104, 107, 108, 109.
