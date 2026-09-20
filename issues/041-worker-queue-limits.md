# 041 — Worker queue: depth and position, jobs per day, job-minute kill, upload size

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Harden the in-process worker from 002 into the 9.1/11.2 queue: one worker, one job at a time in submission order, queued jobs shown "queued, position N", `MAX_QUEUE` refusing a further submission with "try in an hour", `MAX_JOBS_PER_DAY` global, `MAX_JOB_MINUTES` after which the worker kills the step and marks the job `failed` at that step, and `MAX_UPLOAD_MB` enforced on the stream, not after the upload.

Covers PRD `pipeline` (queue), `app` messages. Decisions 9.1, 11.1, 11.2.

## Acceptance criteria

- [ ] A fourth submission with `MAX_QUEUE=3` is refused with "try in an hour"; the job page for a waiting job shows its position and updates as jobs finish.
- [ ] `MAX_JOBS_PER_DAY` counts jobs created since midnight IST; reaching it closes the form with a plain message.
- [ ] `MAX_JOB_MINUTES` exceeded → the running step's subprocess is killed, the job is `failed` at that step with "job exceeded N minutes"; the next job starts.
- [ ] The upload is streamed to disk and aborted past `MAX_UPLOAD_MB` without buffering the whole file.
- [ ] Tests with fakes and a fake clock: ordering of three submissions, refusal of the fourth, day limit at the boundary, minute kill with a stub step that sleeps, upload abort.

## Blocked by

- Blocked by `issues/040-passcode-signed-cookie-ip-block.md`

## User stories addressed

- User story 56
- User story 57
