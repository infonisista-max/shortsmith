# 006 — Technical gate T1–T4, frames-only contact sheet, job page shows the short → `delivered`

## Type

HITL — needs new package: `pillow` (`uv add pillow`) for composing `contact.jpg`. The operator approves; then this ticket becomes AFK. Pillow is later reused by 010 (text measurement), 016 (aspect classification, fake PNGs) and 019 (fake generator).

## Parent PRD

`issues/prd.md`

## What to build

The tracer bullet closes: every job ends in `delivered` or `failed` with a named check. `qa.technical` runs T1–T4 in order and writes `out/qa.json`; any failure stops delivery and names the check. The contact sheet is composed with frames only (hook strip, one frame per second, time labels, safe-area outlines) and the summary panel is a placeholder row that later tickets fill. The job page shows the short, the contact sheet, download links and the qa results. Smoke asserts T1–T4.

Covers PRD `qa.technical` (T1–T4), `contact_sheet` (frames), `app` job page on `delivered`, `pipeline` `qa → delivered` semantics. Decisions 6.3, 10.1, 10.4, 11.1.

## Acceptance criteria

- [ ] `qa.technical.run(job) -> QaReport` runs in order and stops at the first FAIL: T1 codec/container/geometry via ffprobe (H.264 in mp4, 1080x1920, 30 fps, one audio stream); T2 frame count = round(duration × 30); T3 duration ≤ 60.000 s, beats contiguous within 0.011 s, finale 0.8–1.2 s (finale check reads the plan); T4 master −14.0 ± 0.5 LUFS and TP ≤ −1.5 dBTP via ebur128.
- [ ] `out/qa.json` lists every check with pass/fail and a detail string; the failing check name is in `job.json.error.message`.
- [ ] Each of T1–T4 has a unit test with a passing and a failing synthetic input (wrong size, dropped frame, over-long, quiet master).
- [ ] `contact_sheet.compose(job) -> Path` writes `out/contact.jpg` per 10.4: row 1 the hook strip (first 2 s at 4 fps), then one frame per second at 270 px wide, six per row, a time label per frame, the 6.3 safe-area rectangles as thin outlines on the first frame of each row, a per-frame strip line placeholder, a last summary row with T1–T4 dots; under 2 MB; layout and size unit-tested.
- [ ] Pipeline: `qa` pass and the four files `short.mp4`, `contact.jpg` exist → `delivered` (rights.json and credits.md join the rule in 016); `qa` fail → `failed` at step `qa`.
- [ ] `GET /jobs/<id>` on `delivered` shows the short inline, the contact sheet, download links for the short, and the T1–T4 results; on `failed` shows the plain sentence for the step.
- [ ] Smoke runs the whole path on the fixture and asserts T1–T4 pass and the job is `delivered`; total under 90 s.

## Notes from 005

- `ffmpeg.measure_loudness(path)` (loudnorm analysis pass: integrated, true peak, LRA) and `ffmpeg.video_md5(path)` exist; T4 and revision proof (a) can build on them or on `ebur128` directly.
- The mix is voice only until 022; smoke already asserts the short is within ±1.0 LUFS of −14 and the picture md5 matches.

## Blocked by

- Blocked by `issues/005-ffmpeg-cut-voice-mux.md`

## User stories addressed

- User story 43
- User story 44
- User story 52
- User story 62
