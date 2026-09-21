# 041 — Worker queue: depth and position, jobs per day, job-minute kill, upload size

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Harden the in-process worker from 002 into the 9.1/11.2 queue: one worker, one job at a time in submission order, queued jobs shown "queued, position N", `MAX_QUEUE` refusing a further submission with "try in an hour", `MAX_JOBS_PER_DAY` global, `MAX_JOB_MINUTES` after which the worker kills the step and marks the job `failed` at that step, and `MAX_UPLOAD_MB` enforced on the stream, not after the upload.

Covers PRD `pipeline` (queue), `app` messages. Decisions 9.1, 11.1, 11.2.

## Acceptance criteria

- [x] A fourth submission with `MAX_QUEUE=3` is refused with "try in an hour"; the job page for a waiting job shows its position and updates as jobs finish.
- [x] `MAX_JOBS_PER_DAY` counts jobs created since midnight IST; reaching it closes the form with a plain message.
- [x] `MAX_JOB_MINUTES` exceeded → the running step's subprocess is killed, the job is `failed` at that step with "job exceeded N minutes"; the next job starts.
- [x] The upload is streamed to disk and aborted past `MAX_UPLOAD_MB` without buffering the whole file.
- [x] Tests with fakes and a fake clock: ordering of three submissions, refusal of the fourth, day limit at the boundary, minute kill with a stub step that sleeps, upload abort.

## Done (21 Sep 2026)

- `config.Settings` gained `max_queue=3`, `max_jobs_per_day=10`, `max_job_minutes=30` (env `MAX_QUEUE`, `MAX_JOBS_PER_DAY`, `MAX_JOB_MINUTES`, rows in `.env.example`). No new dependency.
- Queue depth counts the running job, the waiting jobs and the slots the upload route has reserved (operator-accepted reading: one running plus two waiting refuses the fourth). `Worker.reserve()`/`release()`/`submit(reserved=True)` let `POST /jobs` hold a slot before it reads the body, so a refused upload costs nothing and a rejected upload gives the slot back. Refusal: 503, `Retry-After: 3600`, the form re-rendered with "N shorts are already in the queue; try in an hour."
- `Worker.position(job_dir)` is the 1-based place among waiting jobs; the running job has none. The job page shows "(queued, position N)" beside the status for an `uploaded` job that is waiting; the JSON carries `queue_position` and the poll script reloads when it changes, so the number moves as jobs finish.
- Day limit: `jobs.created_since(data_dir, since)` counts `created_at` from job.json; the app compares against the most recent midnight in IST, a fixed UTC+5:30 offset from the stdlib (`zoneinfo` on Windows would need `tzdata`). At the limit GET / renders the notice in place of the form and POST /jobs answers 503 with a `Retry-After` of the seconds to the next midnight. `ingest.accept` now takes the app clock so the count and the fake clock agree.
- Job-minute kill: new `subproc.py`. `subproc.run(argv)` is the one subprocess launcher; it registers the child with the `Watchdog` guarding the current thread's job (thread-local, set by `run_job` via `subproc.guarded`). The watchdog polls the injected clock; past the deadline it kills every registered child, and a child launched after the deadline is killed on registration. `subproc.run` then raises `Killed`. Whichever way the step ends afterwards (exception or return), `run_job` checks the clock and fails the job at that step with "The job exceeded N minutes and was stopped." and the worker moves on. `ffmpeg.run` delegates to `subproc.run`, so ffmpeg, Remotion and the Claude CLI are all killable once they arrive. A step with no subprocess (today's fakes) cannot be interrupted; it fails on return when the deadline has passed.
- Streamed upload limit: `app.limited_receive` wraps the ASGI `receive` and raises `BodyTooLarge` on the chunk that crosses the limit, so nothing after it is pulled from the server; the limit is the video cap plus nine references plus 1 MB of framing slack (nine so a ninth reference still gets the count sentence). A `Content-Length` above the limit is refused before the body is read. Both answer 413 with the form and "The recording must be N MB or smaller."; the exact per-file checks in `ingest` are unchanged.
- Templates: `upload.html` is now the page chrome with `$body`; the form moved to `upload_form.html` so the day-limit notice can replace it.
- Tests: `test_config` (defaults, env names), `test_jobs` (`created_since` at the instant), `test_pipeline` (fourth refused, reservation accounting, positions moving, running job counted, child process killed under a clock that jumps 31 minutes with the next job then running, in-process step failing on return at exactly the limit, 29.9 minutes untouched), `test_app` (fourth upload 503 and no slot held, positions on page and JSON, day limit closed at 23:59:59 IST and open at 00:00:00 IST, settings reach the worker, 4 MB body against a 1 MB limit refused before any probe, oversized Content-Length refused, the receive limiter pulls exactly the chunks up to the crossing one).

## Candidate ticket, not done here

- Restart recovery: jobs left `uploaded` when the process restarts are never re-queued; jobs caught mid-step stay in that status. Tickets 002 and 003 deferred this to 041, but it is not in 041's acceptance criteria, so it was left out on the operator's instruction. Suggested shape: the lifespan re-queues `uploaded` jobs in id order at startup; mid-step jobs belong to 043 (retry from step).

## Blocked by

- Blocked by `issues/040-passcode-signed-cookie-ip-block.md`

## User stories addressed

- User story 56
- User story 57
