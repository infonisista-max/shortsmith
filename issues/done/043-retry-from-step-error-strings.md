# 043 — Retry from step and the fixed user-facing error strings

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

A failed job shows one plain sentence for the step that failed from a fixed table, with detail kept in `job.json` and the log, and offers "retry from this step", which re-enters the pipeline at that step reusing everything already fetched or generated: a planner failure re-plans only, a sourcing failure re-uses the per-job asset cache, a render failure re-renders from the existing plan and assets, a qa failure re-runs qa. Retries are new ledger rows when they pay.

Covers PRD `pipeline` (retry), `app` (error text). Decisions 11.1, 5.6, 9.1.

## Acceptance criteria

- [x] `pipeline.ERROR_TEXT` maps every step to one plain sentence; the page shows it, `job.json.error.detail` keeps the exception text.
- [x] `POST /jobs/<id>/retry` on a `failed` job re-queues it starting at `error.step`; the queue rules from 041 apply.
- [x] Reuse proven by tests with counting fakes: retry from `rendering` makes zero planner and zero source calls; retry from `sourcing` fetches only uncached beats; retry from `planning` re-transcribes nothing.
- [x] A job that fails twice at the same step keeps both errors in `job.log`.

## Blocked by

- Blocked by `issues/042-sweeper-disk-guard.md`

## User stories addressed

- User story 53

## Done

- The re-entry is a field, not a looser status machine: `jobs.requeue` is the only door
  out of `failed`, sending the job back to `uploaded` with `retry_from` set, and
  `can_transition` lets a job jump from `uploaded` to that step **and to no other**, so a
  job that was never requeued still cannot skip one. `pipeline.start_step` slices the
  step list there; every step before it keeps what it left on disk.
- `STEP_MESSAGES` is now `pipeline.ERROR_TEXT`, with a test that it holds one sentence
  per `jobs.STEPS`, so a new step cannot arrive without user-facing text.
- Two refusals the ticket did not list, both 409 with one sentence and the button hidden
  for the same reason (`app.retry_refusal`): a job that did not fail, and a job the
  sweeper has taken the input and work files from (2.2) - re-running a step without its
  files would only fail the job a second time.
- The per-job asset cache (5.6) was already what makes a sourcing retry cheap; the test
  proves it by taking a source down mid-run and counting the second run's searches.

## Notes for 044

- `_ledger_block` needs no retry-specific work: `jobs.amend` keeps `cost` across the
  requeue, so the failed run's rows and the retry's are one list on the page.
- `retry_from` stays on `job.json` after the run, so the job list (045) and the cost
  panels (044) can tell a retried job from a first-run one without reading `job.log`.
