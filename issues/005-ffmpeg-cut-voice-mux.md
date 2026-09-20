# 005 — ffmpeg presenter cut, voice stem and final mux → out/short.mp4

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The other half of the hybrid engine from 9.1. Before the Remotion render, the presenter cut is built from the plan's kept and cut spans (word removal and the cold-open lift with `keep | drop`) and re-encoded once to constant-frame-rate H.264 with no B-frames. The voice stem is produced through the research §5 voice chain (mono fold, high-pass 80 Hz, compressor, two-pass loudnorm −19 LUFS / −3 dBTP). After the render, the silent picture and the voice stem are muxed with `-c:v copy` into `out/short.mp4`. No music yet (ticket 022); the master loudnorm and limiter run on the voice alone so T4 can pass in 006.

Covers PRD `presenter` (cut list only; face measurement is 013), the ffmpeg half of `render`, the voice part of `sound`. Decisions 3.4, 7.3, 9.1.

## Acceptance criteria

- [ ] `presenter.cut_list(plan) -> list[Span]` derives kept spans from the plan's `cut` and the hook's `original_position`; with `drop` the lifted span is absent at its original place, with `keep` it stays; unit-tested on the fake plan.
- [ ] `render.cut_presenter(job)` writes `work/cut.mp4`: CFR 30 fps, H.264, `-bf 0`, 1080x1920 centre crop obeying the 1.5x rule; ffprobe in a test confirms `has_b_frames=0` and constant frame rate.
- [ ] `render.voice_stem(job)` writes `work/stems/voice.wav` through the §5 voice chain verbatim: mono fold inside the graph, high-pass 80 Hz, compressor −18 dB ratio 2.5, two-pass loudnorm −19 LUFS / −3 dBTP.
- [ ] `render.mux(job)` runs master two-pass loudnorm −14 LUFS / −1.5 dBTP plus limiter 0.891 on the mix (voice only for now) and muxes with `-c:v copy` into `out/short.mp4`; a test proves the video stream md5 of `work/picture.mp4` and `out/short.mp4` are identical (revision proof (a) from 10.1).
- [ ] Stems are always written beside the mix under `work/stems/`.
- [ ] The Remotion composition (004) now uses `work/cut.mp4` as the presenter source; PIP and full-frame show real presenter pixels from the fixture.
- [ ] Smoke produces `out/short.mp4`, 6 s, with audio, and the job reaches `rendering → qa` (qa is a placeholder pass until 006).

## Blocked by

- Blocked by `issues/004-remotion-captions-pip-composition.md`

## User stories addressed

- User story 12
- User story 30
- User story 58
