# 034 — Phone rating, calibration streak, advisory to blocking, YouTube performance fields

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The feedback loop. The job page has a 1–10 slider and a note stored on `job.json.rating`; `data/calibration.json` tracks whether the critic's pass/fail matched the phone verdict on each rated job; after four of five consecutive matches the critic becomes blocking (pass line 7/10) and the page shows "critic agreed N of last 5". Published URL, views and retention are manual fields on the job page, or a read-only YouTube Data API pull when a key is supplied, never an upload.

Covers PRD `qa.critic` (calibration), `jobs` rating and performance fields, `app`. Decisions 10.2, 10.3, 10.4, 14.1(a).

## Acceptance criteria

- [ ] `POST /jobs/<id>/rating` stores `{score, note, rated_at}`; the slider and note render with the stored value.
- [ ] `qa.critic.calibration.record(job)` appends `{job_id, critic_pass, phone_pass, matched}` with critic pass = overall ≥ 7 and phone pass = rating ≥ 6; `mode()` returns `blocking` when the last five have ≥ 4 matches, else `advisory`; the page shows "critic agreed N of last 5".
- [ ] While advisory: `passed` = rating ≥ 6, `rejected` = rating < 6; while blocking: `passed` requires critic ≥ 7 and, when given, rating ≥ 6; `rejected` on either failing; a `delivered` job stays downloadable when `rejected`.
- [ ] `POST /jobs/<id>/performance` stores published URL, views, retention; `YOUTUBE_API_KEY` set → a read-only Data API pull fills views for a stored URL; tests on recorded JSON.
- [ ] `job.json` and `meta.json` (035) carry rating, critic scores and performance.
- [ ] Unit tests: streak arithmetic at 3 of 5 and 4 of 5, mode flip and flip-back, status semantics in both modes.

## Notes from 045

- The job list (`GET /jobs`, `app.render_job_list` / `_job_row`) already has a rating column, which shows `-` for now because `job.json` has no rating yet. When `rating` lands on `JobRecord`, put its score in that cell (`<td>-</td>` in `_job_row`).

## Blocked by

- Blocked by `issues/033-vision-critic.md`

## User stories addressed

- User story 46
- User story 47
- User story 48
