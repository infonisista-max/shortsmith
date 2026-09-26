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

- Nothing; 032 is done.

## User stories addressed

- User story 36
- User story 45

## Done (2026-09-26)

- `contracts.CriticReport` / `CriticLine` / `CRITIC_LINES` (E1-E10 in order, score 1-10, one
  reason each, `overall`, `fix_notes` <= 5, `model`, `advisory`, `status` scored | unavailable,
  `category`, `notes`); `QaReport.critic` carries it in `out/qa.json`.
- `contracts.CATEGORIES` (history, geopolitics, finance, product, motivation, science,
  technology, health, other) and `PicturePlan.category` (default `other`, so plans from
  before 033 load); the grammar rejects a name outside the list at plan level (rule 10.3).
- Prompt v6: the picture file gained the `category` rule (list in words, and in the schema's
  field description); the sound file is unchanged; snapshots recorded.
- `qa.critic`: `Critic` interface, `FakeCritic` (fixed scores, records its inputs),
  `VisionCritic` (one Messages call: rubric and anchors as cached system blocks; pattern data,
  plan summary, stem balance, transcript and the notes as text; the contact sheet, the PIP
  strip and the hook strip as JPEG images, each introduced by a line), `build_inputs(job)`,
  `parse_reply`, `unavailable`, `from_settings`, `run(job, critic)`.
- Pipeline: the `qa` step runs the critic after the gate, the sheet and the deliverables
  check; `CriticError` -> `unavailable` report, job still `delivered`; `BudgetExceeded`
  propagates (fails the job at `qa`, 11.3). `run_job` / `Worker` / `create_app` take `critic`.
- Config: `CRITIC=fake|api` (default `api`, needs `ANTHROPIC_API_KEY` at startup, no `none`),
  `CRITIC_MODEL` (default `claude-sonnet-5`). Ledger: provider `critic` with the planner's four
  token units; `prices.example.yaml` has the block.
- Job page: critic panel (ten lines, overall, fix notes, model, category, advisory badge, the
  input notes; one sentence when unavailable). Smoke: the fake critic scores the real render
  and `check_critic` proves the three strips were real; the summary line carries the verdict.
- Fixtures under `tests/fixtures/critic/`: `request.json` is recorded from the code's own
  builder (image data masked) and the whole sent body is asserted against it; `reply.json`
  and `refusal.json` are SDK-shaped replies. Tests in `tests/test_qa_critic.py` plus the
  pipeline, app, config, ledger, grammar, prompt and smoke additions.
- HITL ceremony (2026-09-26): the afk iteration timed out after the loops with the tree
  dirty; the operator audited the WIP, had `request.json` aligned and asserted, and
  finished it in this session.

Operator notes:

- `.env.example` could not be edited from this session (the path is denied to the agent):
  please add `CRITIC=api` and `CRITIC_MODEL=claude-sonnet-5` lines beside the judge's.
- `prices.yaml` (git-ignored) needs the `critic:` block from `prices.example.yaml`, or the
  server stops at startup naming `critic` (5.6); `CRITIC=fake` also runs without it.
- The contact sheet's summary row still points at qa.json for the critic scores: the critic
  scores the sheet after it is composed, so drawing them into it is 035's redraw.
- `advisory` is a module constant (`qa.critic.ADVISORY`) until 034 derives it from
  `data/calibration.json`.
