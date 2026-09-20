# 033 — Vision critic: score interface, model implementation, fake, critic panel on the job page

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The editorial gate that runs on every job from day one, advisory until calibrated (034). `score(inputs) -> CriticReport` with a vision-model implementation through the Anthropic SDK, model from `CRITIC_MODEL`, and a fake with fixed scores. Inputs per 10.3: contact sheet, PIP strip, hook strip, plan summary text, stem balance report, transcript, the approved-shorts anchors from `docs/reference`, and the category's pattern data when present (039 wires the measured library). Output is E1–E10 with one reason each, overall, up to five fix notes, written to `qa.json` and shown on the job page. The planner sets the category from a fixed list.

Covers PRD `qa.critic`, `pipeline` critic step, `app` critic panel. Decisions 10.2, 10.3, 12.1.

## Acceptance criteria

- [ ] `contracts.CriticReport`: E1–E10 each `{score 1–10, reason}` for hook, B-roll relevance, mode variation, density, captions, PIP framing, sound, payoff, integrity, embarrassment; `overall`; `fix_notes` ≤ 5; `model`; `advisory: bool`.
- [ ] `qa.critic.build_inputs(job)` assembles the 10.3 inputs including a plan summary (beat count, mode fractions, density, clamps, rescued beats, asset origins) and the stem balance report; `PicturePlan` gains `category` from a fixed list validated by the grammar.
- [ ] `VisionCritic.score` sends one Messages call with the images and text and parses the report; `FakeCritic` returns fixed scores and reasons; every critic call is a ledger row.
- [ ] The pipeline runs the critic after the technical gate on every `delivered` job; a critic API failure marks the report `unavailable` and never blocks delivery while advisory.
- [ ] Job page critic panel: ten lines with score and reason, overall, fix notes, model name, "advisory" badge.
- [ ] Recorded request/response JSON under `tests/fixtures/critic/`; tests assert input assembly, request construction, parsing; smoke uses `FakeCritic` and asserts a report is in `qa.json`.

## Blocked by

- Blocked by `issues/032-gate-t8-t11-t12-t13.md`

## User stories addressed

- User story 36
- User story 45
