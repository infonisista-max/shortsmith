# 042 — Sweeper and disk guard

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Retention as code with a clock injected: delete `input/` and `work/` for jobs older than 24 h from `uploaded`, delete the whole job directory at 7 days, never touch a running job, log each deletion to `job.log` and record `swept_at` in `job.json`. The same code path is an in-process background task every 15 minutes and a CLI with `--dry-run`. When free disk under the data dir is below 5 GB the upload form refuses new jobs with a plain message and the sweeper runs immediately.

Covers PRD `sweeper`, `app` disk guard. Decisions 2.2, 11.2.

## Acceptance criteria

- [ ] `sweeper.sweep(data_dir, clock, dry_run) -> list[Action]`; each action names the job and what was deleted; dry-run returns the list and writes nothing.
- [ ] `python -m shortsmith.sweeper --dry-run` prints the actions; without the flag it performs them.
- [ ] The app runs the sweeper every 15 minutes as a background task; a running job (status not terminal) is never touched.
- [ ] Free disk < 5 GB: the form refuses with "not enough disk, try later" and the sweeper runs at once.
- [ ] Boundary tests, `tests/test_sweeper.py` with `FakeClock`: 23 h 59 min untouched, 24 h 01 min swept, running job untouched, 7-day full delete, dry-run writes nothing, `swept_at` recorded, log line written.

## Blocked by

- Blocked by `issues/041-worker-queue-limits.md`

## User stories addressed

- User story 55
- User story 56
