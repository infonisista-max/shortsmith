# 005 — ffmpeg presenter cut, voice stem and final mux → out/short.mp4

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The other half of the hybrid engine from 9.1. Before the Remotion render, the presenter cut is built from the plan's kept and cut spans (word removal and the cold-open lift with `keep | drop`) and re-encoded once to constant-frame-rate H.264 with no B-frames. The voice stem is produced through the research §5 voice chain (mono fold, high-pass 80 Hz, compressor, two-pass loudnorm −19 LUFS / −3 dBTP). After the render, the silent picture and the voice stem are muxed with `-c:v copy` into `out/short.mp4`. No music yet (ticket 022); the master loudnorm and limiter run on the voice alone so T4 can pass in 006.

Covers PRD `presenter` (cut list only; face measurement is 013), the ffmpeg half of `render`, the voice part of `sound`. Decisions 3.4, 7.3, 9.1.

## Acceptance criteria

- [x] `presenter.cut_list(plan) -> list[Span]` derives kept spans from the plan's `cut` and the hook's `original_position`; with `drop` the lifted span is absent at its original place, with `keep` it stays; unit-tested on the fake plan.
- [x] `render.cut_presenter(job)` writes `work/cut.mp4`: CFR 30 fps, H.264, `-bf 0`, 1080x1920 centre crop obeying the 1.5x rule; ffprobe in a test confirms `has_b_frames=0` and constant frame rate.
- [x] `render.voice_stem(job)` writes `work/stems/voice.wav` through the §5 voice chain verbatim: mono fold inside the graph, high-pass 80 Hz, compressor −18 dB ratio 2.5, two-pass loudnorm −19 LUFS / −3 dBTP.
- [x] `render.mux(job)` runs master two-pass loudnorm −14 LUFS / −1.5 dBTP plus limiter 0.891 on the mix (voice only for now) and muxes with `-c:v copy` into `out/short.mp4`; a test proves the video stream md5 of `work/picture.mp4` and `out/short.mp4` are identical (revision proof (a) from 10.1).
- [x] Stems are always written beside the mix under `work/stems/`.
- [x] The Remotion composition (004) now uses `work/cut.mp4` as the presenter source; PIP and full-frame show real presenter pixels from the fixture.
- [x] Smoke produces `out/short.mp4`, 6 s, with audio, and the job reaches `rendering → qa` (qa is a placeholder pass until 006).

## Done 2026-09-21

- Cut list semantics: the cold-open span is always first (the 3.4 lift); under `drop` it is removed from its original place, under `keep` it plays twice. The fake plan's `original_position` changed `keep` → `drop` (one field): its cold open sits at the head, so the lift is a no-op reorder and the smoke short stays 6 s; under `keep` it would have played 0–0.5 s twice.
- The short is as long as the cut list (`presenter.total_duration`), not the transcript. Moving word times onto the cut timeline is left to the pager (010); `presenter.output_time(spans, t)` is the pure helper for it.
- 1.5x rule: `presenter.crop_window` is the one geometry for the upload check (ingest imports it) and the cut; it raises `UpscaleExceeded` before ffmpeg starts.
- Master: loudnorm's linear mode is impossible whenever the voice's peaks would pass −1.5 dBTP at target (most speech), and its dynamic mode lands about 0.5 LU off a fresh measurement. `render.master` corrects the requested target by the measured error and re-runs (≤ 4 passes, 0.2 LU tolerance) so T4's ±0.5 holds; the chain itself is unchanged. The 0.891 limiter runs with `level=false`: its auto-level would re-gain the output to 0 dB.
- `Renderer.render` is now the whole `rendering` step; `FakeRenderer` writes empty placeholders for the cut, stems, picture and short.
- For 006: `ffmpeg.measure_loudness` and `ffmpeg.video_md5` are the T4 and revision-proof primitives.

## Blocked by

- Blocked by `issues/004-remotion-captions-pip-composition.md`

## User stories addressed

- User story 12
- User story 30
- User story 58
