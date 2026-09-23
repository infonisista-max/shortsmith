# 042 — Sweeper and disk guard

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Retention as code with a clock injected: delete `input/` and `work/` for jobs older than 24 h from `uploaded`, delete the whole job directory at 7 days, never touch a running job, log each deletion to `job.log` and record `swept_at` in `job.json`. The same code path is an in-process background task every 15 minutes and a CLI with `--dry-run`. When free disk under the data dir is below 5 GB the upload form refuses new jobs with a plain message and the sweeper runs immediately.

Covers PRD `sweeper`, `app` disk guard. Decisions 2.2, 11.2.

## Acceptance criteria

- [x] `sweeper.sweep(data_dir, clock, dry_run) -> list[Action]`; each action names the job and what was deleted; dry-run returns the list and writes nothing.
- [x] `python -m shortsmith.sweeper --dry-run` prints the actions; without the flag it performs them.
- [x] The app runs the sweeper every 15 minutes as a background task; a running job (status not terminal) is never touched.
- [x] Free disk < 5 GB: the form refuses with "not enough disk, try later" and the sweeper runs at once.
- [x] Boundary tests, `tests/test_sweeper.py` with `FakeClock`: 23 h 59 min untouched, 24 h 01 min swept, running job untouched, 7-day full delete, dry-run writes nothing, `swept_at` recorded, log line written.

## Blocked by

- Blocked by `issues/041-worker-queue-limits.md`

## User stories addressed

- User story 55
- User story 56

## Done (24 Sep 2026)

- `sweeper.py` holds both ages as module constants (`WORKING_AFTER` 24 h,
  `JOB_AFTER` 7 d, both counted from `created_at`, the `uploaded` stamp) and the
  guard line (`MIN_FREE_BYTES` 5 GiB). Nothing new in `.env`: the numbers are
  decisions 2.2 / 11.2, not operator settings.
- "Never touch a running job" is read as `jobs.SETTLED` (the three terminal
  statuses plus `delivered`), which moved out of `app.py` into `jobs.py` so the
  page's elapsed clock and the sweeper share one definition. A queued or running
  job keeps every file, so a step can never lose the input of its successor.
- The 7-day pass takes `job.log` with the directory, so that deletion is a logger
  line and the returned `Action` only; the 24 h pass writes the `job.log` line and
  `swept_at` (a new optional field on `JobRecord`, so older job.json still loads).
- The disk guard reuses the day-limit shape: `closed=` replaces the form on `GET /`,
  `POST /jobs` answers 503 with `Retry-After: 900`, and both call `sweep` at once.
  Free space is an injected seam (`free_disk=`) so tests never need a full disk.
- The job page gains one warning line once `swept_at` is set, so an empty brief and
  "references: none" have a stated reason rather than looking like data loss.
