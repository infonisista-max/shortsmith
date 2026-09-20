# 039 — Critic anchors on category pattern data and the approved shorts

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The critic's rubric prompt now includes the job category's measured pattern data and frames from the reference library plus the approved-shorts anchors with their phone ratings, so a score means "matches what top shorts measurably do" and a 6 and an 8 are calibrated to Shubham's verdicts. With no library entry for a category the critic says so in the report rather than scoring against nothing.

Covers PRD `qa.critic` (inputs from the library). Decisions 10.2, 10.3.

## Acceptance criteria

- [ ] `qa.critic.build_inputs` loads `docs/reference/<category>/README.md` figures and up to N reference frames per entry (N from config) and the anchors' figures and ratings; the prompt states the category's measured ranges beside the job's own plan summary numbers.
- [ ] Missing category → `CriticReport.notes` records "no reference data for <category>" and the ten lines are still scored against the anchors only.
- [ ] `meta.json` records `reference_pack_version` and the category used.
- [ ] Tests: input assembly with a fixture README, missing-category path, prompt snapshot on recorded inputs.

## Blocked by

- Blocked by `issues/033-vision-critic.md`
- Blocked by `issues/036-reference-tool-download-analyse.md`

## User stories addressed

- User story 45
