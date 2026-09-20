# 043 — Retry from step and the fixed user-facing error strings

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

A failed job shows one plain sentence for the step that failed from a fixed table, with detail kept in `job.json` and the log, and offers "retry from this step", which re-enters the pipeline at that step reusing everything already fetched or generated: a planner failure re-plans only, a sourcing failure re-uses the per-job asset cache, a render failure re-renders from the existing plan and assets, a qa failure re-runs qa. Retries are new ledger rows when they pay.

Covers PRD `pipeline` (retry), `app` (error text). Decisions 11.1, 5.6, 9.1.

## Acceptance criteria

- [ ] `pipeline.ERROR_TEXT` maps every step to one plain sentence; the page shows it, `job.json.error.detail` keeps the exception text.
- [ ] `POST /jobs/<id>/retry` on a `failed` job re-queues it starting at `error.step`; the queue rules from 041 apply.
- [ ] Reuse proven by tests with counting fakes: retry from `rendering` makes zero planner and zero source calls; retry from `sourcing` fetches only uncached beats; retry from `planning` re-transcribes nothing.
- [ ] A job that fails twice at the same step keeps both errors in `job.log`.

## Blocked by

- Blocked by `issues/042-sweeper-disk-guard.md`

## User stories addressed

- User story 53
