# 007 — Day-3 seconds-per-frame measurement on the deployment box

## Type

HITL — the operator runs the bench on the laptop and on the target VPS and records the numbers; the agent cannot reach the deployment box.

## Parent PRD

`issues/prd.md`

## What to build

The 9.1 tracer-bullet measurement. Run `python -m shortsmith.bench` (from 004) with the real explainer composition on the laptop and on a 4 vCPU / 8 GB VPS, at concurrency 2, and record seconds per frame and total seconds for the fixture and the projected time for a 60 s short. If the VPS figure is above 0.5 s/frame, the knobs are concurrency and preview resolution, not the engine; record which knob was chosen.

Covers PRD "Deployment" day-3 measurement. Decision 9.1.

## Acceptance criteria

- [ ] `docs/bench.md` records, per box: CPU, RAM, Node version, Remotion version, concurrency, s/frame, total seconds for the 6 s fixture, projected minutes for a 60 s short, date.
- [ ] The VPS figure is compared to the 0.5 s/frame line; if over, the chosen knob and its new figure are recorded.
- [ ] The engine decision is written as confirmed or as "re-open 9.1" with the numbers; nothing else changes in this ticket.
- [ ] The laptop row alone completes this ticket; the VPS row is added when a deployment box exists.

## Blocked by

- Nothing; 004 is done.

## User stories addressed

- User story 58
- User story 66
