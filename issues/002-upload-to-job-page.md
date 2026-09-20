# 002 — Upload form → server-side validation → job page polling

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The creator's first real path: open the page, upload a recording with a brief, a style line and optional references, press one button, land on the job page and watch the status change. Validation is server-side per 2.1 and returns a plain rejection sentence. A minimal in-process worker runs the job's steps one at a time in submission order (only ingest and the fake transcriber exist yet). No passcode yet (ticket 040), no style resolution yet (ticket 008; store the raw style line).

Covers PRD `ingest`, the first routes of `app`, the first version of `pipeline` (the worker), and the `jobs` list helper. Decisions 2.1, 2.2, 11.1. Page templates are stdlib string templating to avoid a new package.

## Acceptance criteria

- [ ] `GET /` shows the upload form: video file, brief textarea (placeholder: topic / angle / must-say facts / hook wish), style text field, up to eight reference files each with a one-line caption field, the 3.3 framing guideline line, one submit button.
- [ ] `POST /jobs` validates per 2.1 with ffprobe: one video and one audio stream, duration 20 s–8 min, mean volume ≥ −50 dBFS ("no speech found"), 1.5x upscale rule for the 1080x1920 centre crop ("record vertical or in 4K"), any orientation with the "vertical works best for PIP" warning, brief 40–1500 chars, ≤ 8 references, ≤ 20 MB each, images ≥ 600 px short side, upload ≤ `SHORTSMITH_MAX_UPLOAD_MB`.
- [ ] Rejections return the form with one plain sentence and no job directory is created.
- [ ] Accepted uploads write `input/raw.mp4`, `input/brief.md` verbatim, `input/refs/<n>_<slug>.<ext>` and `input/refs.json` with caption, original name, dimensions and `rights: owner_supplied` per 2.2, then redirect to `/jobs/<id>`.
- [ ] The worker runs jobs one at a time in submission order in-process; a second submission while one runs is `uploaded` and waits.
- [ ] `GET /jobs/<id>` returns HTML with the step list from 11.1 and the current step highlighted, elapsed time, and re-polls `GET /jobs/<id>.json` every 3 s; the JSON is `job.json`.
- [ ] Boundary tests via the FastAPI test client on synthetic inputs: brief 39/40 chars, upscale 1.49x/1.51x, volume −49/−51 dBFS, duration 19.9/20 s, nine references, 599/600 px short side.
- [ ] Every user-supplied string (brief, style line, reference captions, filenames) and any model-generated text is HTML-escaped with `html.escape` wherever it is interpolated into a page template, including the rejection re-render of the form; a test posts `<script>alert(1)</script>` as the brief and as a reference caption and asserts that both the rejection re-render and the job page contain it only in escaped form.
- [ ] Smoke uses `ingest` directly on the fixture (not HTTP) and the job reaches `transcribing` through the worker path.

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
