# 002 — Upload form → server-side validation → job page polling

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The creator's first real path: open the page, upload a recording with a brief, a style line and optional references, press one button, land on the job page and watch the status change. Validation is server-side per 2.1 and returns a plain rejection sentence. A minimal in-process worker runs the job's steps one at a time in submission order (only ingest and the fake transcriber exist yet). No passcode yet (ticket 040), no style resolution yet (ticket 008; store the raw style line).

Covers PRD `ingest`, the first routes of `app`, the first version of `pipeline` (the worker), and the `jobs` list helper. Decisions 2.1, 2.2, 11.1. Page templates are stdlib string templating to avoid a new package.

## Acceptance criteria

- [x] `GET /` shows the upload form: video file, brief textarea (placeholder: topic / angle / must-say facts / hook wish), style text field, up to eight reference files each with a one-line caption field, the 3.3 framing guideline line, one submit button.
- [x] `POST /jobs` validates per 2.1 with ffprobe: one video and one audio stream, duration 20 s–8 min, mean volume ≥ −50 dBFS ("no speech found"), 1.5x upscale rule for the 1080x1920 centre crop ("record vertical or in 4K"), any orientation with the "vertical works best for PIP" warning, brief 40–1500 chars, ≤ 8 references, ≤ 20 MB each, images ≥ 600 px short side, upload ≤ `SHORTSMITH_MAX_UPLOAD_MB`.
- [x] Rejections return the form with one plain sentence and no job directory is created.
- [x] Accepted uploads write `input/raw.mp4`, `input/brief.md` verbatim, `input/refs/<n>_<slug>.<ext>` and `input/refs.json` with caption, original name, dimensions and `rights: owner_supplied` per 2.2, then redirect to `/jobs/<id>`.
- [x] The worker runs jobs one at a time in submission order in-process; a second submission while one runs is `uploaded` and waits.
- [x] `GET /jobs/<id>` returns HTML with the step list from 11.1 and the current step highlighted, elapsed time, and re-polls `GET /jobs/<id>.json` every 3 s; the JSON is `job.json`.
- [x] Boundary tests via the FastAPI test client on synthetic inputs: brief 39/40 chars, upscale 1.49x/1.51x, volume −49/−51 dBFS, duration 19.9/20 s, nine references, 599/600 px short side.
- [x] Every user-supplied string (brief, style line, reference captions, filenames) and any model-generated text is HTML-escaped with `html.escape` wherever it is interpolated into a page template, including the rejection re-render of the form; a test posts `<script>alert(1)</script>` as the brief and as a reference caption and asserts that both the rejection re-render and the job page contain it only in escaped form.
- [x] Smoke uses `ingest` directly on the fixture (not HTTP) and the job reaches `transcribing` through the worker path.

## Done — 20 Sep 2026

- `ingest.Limits` carries every 2.1 number as a default; the checks (`check_video`, `check_brief`, `check_references`) are pure functions over `VideoInfo`/`ReferenceInfo` so the boundary tests run on plain data, and the same values are hit again through the FastAPI test client on ffmpeg-generated clips. The rejection sentences live in `ingest` and are parameterised from `Limits`.
- The fixture is 6 s but 2.1 rejects under 20 s, so smoke passes `Limits(min_duration_s=6.0)` and nothing else; looping the fixture was rejected because it would slow every later render step in smoke.
- The upscale rule is `1920 / min(height, width * 16/9)`, i.e. the scale needed to fill 1080x1920 from the largest 9:16 centre crop: landscape 1080p is 1.78x (reject), 4K landscape 0.89x (accept with the PIP warning).
- Mean volume comes from ffmpeg `volumedetect` (`ffmpeg.mean_volume_db`); test clips at −49/−51 dBFS use PCM audio in `.mov` so the level survives encoding exactly. `.mov` uploads are stored as `input/raw.mov`; `job.json.input.file` names which.
- `refs.json` rows are `contracts.ReferenceRecord` (`id: ref<n>`, `file` relative to `input/`, `kind: image|clip`, caption, original name, dimensions, size, `rights: owner_supplied`). Reference dimensions come from ffprobe, so no image library was needed (Pillow arrives with 006).
- `job.json` gained `input` (`InputSummary`: file, original name, duration, dimensions, size, reference count) and `warnings` (the PIP orientation note). `jobs.find` validates the id pattern before touching the filesystem; `jobs.list_jobs` is the 11.1 last-fifty helper for ticket 045.
- `pipeline.run_job` is the synchronous step runner (uploaded → transcribing → `work/asr.json` → planning, stops there until 003); any step exception marks the job `failed` at that step with the fixed sentence from `STEP_MESSAGES` and the traceback in `detail`. `pipeline.Worker` wraps it in a FIFO queue on one daemon thread; `run_next()` drains one job synchronously so tests and smoke exercise the worker code path without threads. Restart recovery of `uploaded` jobs, queue depth and the job-minute kill are ticket 041.
- `app.create_app(settings, transcriber=..., limits=..., start_worker=...)` is the factory; the module-level `app` is what `uvicorn shortsmith.app:app` serves and loads `.env` at import. Only the fake transcriber exists, so the app defaults to it until ticket 012 wires Groq. Templates are `string.Template` files under `src/shortsmith/templates/`. Rejections re-render the form with status 422 and keep the brief, style line and captions (escaped). The job page's inline script fetches the JSON every 3 s, updates elapsed time and reloads on a status change.
- `tests/__init__.py` was added so `tests/conftest.py` helpers (`Media`, a per-session cache of synthetic clips and stills) import cleanly under pyright strict.
- The full test run is about 65 s, most of it ffmpeg generating boundary clips once per session.

## Blocked by

- Blocked by `issues/001-walking-skeleton.md`

## User stories addressed

- User story 1
- User story 4
- User story 5
- User story 7
- User story 8
- User story 52
- User story 57
