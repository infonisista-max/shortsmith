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

## Notes

- Per `docs/reference-tooling.md` ("What these tools change"): a critic pass means the floor is cleared and never substitutes for the phone rating; an unrated job stays unrated. An unrated job may still be `passed` on the floor; once given, the rating is final and a rating < 6 un-passes it.

## Done note (2026-09-26, AFK session)

What landed:

- `jobs.py`: `Rating`, `Performance` and `CriticSummary` models on `JobRecord` (`rating`, `performance`, `critic`); `rate`, `set_performance`, `settle` (the only way among `delivered` / `passed` / `rejected`; `transition` still treats `passed` and `rejected` as terminal), `data_dir_of`.
- `qa/calibration.py` (reached as `qa.critic.calibration` too): `record`, `mode` / `mode_of`, `agreed_line`, `verdict`, `apply`; file is `<data_dir>/calibration.json`, one entry per rated job, replaced in place on a re-rating so a second look never counts twice.
- `qa/critic.py`: `run` takes its mode from the calibration (the `ADVISORY` constant is gone) and writes the summary onto `job.json.critic`.
- `pipeline.py`: after `qa -> delivered`, `calibration.apply` settles a blocking-critic job at once (`passed` at 7, else `rejected`); advisory stays `delivered` until rated.
- `performance.py`: `video_id`, `YouTube.views` (one GET on the Data API v3, key in the `x-goog-api-key` header, never in the URL), `from_settings`; recorded reply under `tests/fixtures/youtube/videos.json`. Retention is not on the Data API (Analytics needs OAuth), so it stays hand-typed.
- `app.py`: `POST /jobs/<id>/rating`, `POST /jobs/<id>/performance`, the feedback template, "critic agreed N of last 5" in the critic panel, the rating cell on the job list. `config.Settings.youtube_api_key`.

Decisions taken here (not in the ticket text):

- A re-rating is allowed and the verdict follows the latest rating (`passed -> rejected` and back), logged as `<from> -> <to> by rating N/10`. "The rating is final" is read as "final over the critic", not immutable.
- A job is judged under the mode its critic ran in (`job.json.critic.advisory`), not the mode at rating time: that is the badge the page showed and the report the calibration compared.
- An unavailable critic never counts as a match, and cannot block: under either mode the rating alone decides such a job, so an API outage never rejects a short.
- Fewer than five rated jobs: the same four matches flip the mode (four of four is blocking).
- No ledger row for the YouTube pull: free quota, like Pexels / Pixabay / Freesound.

For the operator:

- `.env.example` is outside this agent's write set; please add under the CRITIC lines: `YOUTUBE_API_KEY=` with the comment "read-only Data API v3 pull of the view count for a published URL (14.1a); unset leaves views hand-typed; never an upload".
- The full `uv run pytest -q` run now exceeds the agent's 10-minute foreground limit; this session ran it in file-group chunks. Worth splitting the slow render tests behind a marker in a later infra ticket.

## Verification note (2026-09-26, second AFK session)

The first session was killed after its done note and before the commit. This session found the dirty tree, matched it to this ticket, re-ran every loop in the foreground and committed it:

- `uv run ruff check .` and `uv run pyright`: clean.
- `uv run pytest -q` in four foreground file-group chunks covering all 46 test files: 247 + 670 + 439 + 16 = 1372 passed, 0 failed.
- `uv run python -m shortsmith.smoke`: ok, `delivered`, T1-T13 pass, critic 7/10 advisory; read `out/qa.json` and `job.json` of a kept run: `critic` summary present (`scored`, 7, advisory, fake), `rating` and `performance` null until typed.
- Nothing under `src/remotion/` changed, so the npm loops did not apply.
- `meta.json` carrying the three fields is 035's half of the shared criterion and stays with 035.

## Blocked by

- Blocked by `issues/033-vision-critic.md`

## User stories addressed

- User story 46
- User story 47
- User story 48
