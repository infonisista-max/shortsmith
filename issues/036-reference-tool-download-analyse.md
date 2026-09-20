# 036 — Reference library tool: download, frames, cut and motion analysis, README writer

## Type

HITL — needs new package: `yt-dlp` (`uv add yt-dlp`). The operator approves; then this ticket becomes AFK.

## Parent PRD

`issues/prd.md`

## What to build

`shortsmith reference add <url|channel> --category <c>` downloads a short into the git-ignored `work/reference/<category>/`, extracts frames with the documented ffmpeg command, measures the pattern data that needs no OCR or face detector (cuts per 10 s by scene-change detection, visual-change rate by frame-difference energy, transition density, sound-hit density by onset detection on the non-speech band), tags each figure MEASURED or ESTIMATED, and writes `docs/reference/<category>/README.md` in the existing format. The analyser is pure code over a video file and boundary-tested on a synthetic clip. Caption pages, mode timeline and hook description follow in 037.

Covers PRD `reference` (tool and analyser). Decisions 10.3, 12.2.

## Acceptance criteria

- [ ] `python -m shortsmith.reference add <url> --category <c>` downloads with yt-dlp, stores `work/reference/<category>/<id>.mp4` (git-ignored), extracts `frames/*.jpg` with the README's ffmpeg command.
- [ ] `reference.analyse(video) -> PatternData` measures cuts per 10 s, visual-change rate, transition density (fraction of cuts with motion blur or scale change in the adjacent frames), sound-hit density (onsets per 10 s in the non-speech band); each figure tagged MEASURED; caption pages, mode timeline and hook structure written as ESTIMATED placeholders until 037.
- [ ] The category README is created or appended in the existing `docs/reference/README.md` format with the entry, figures, tags and the source URL; the pack version is bumped.
- [ ] Boundary test, `tests/test_reference.py`: a synthetic clip with six hard cuts yields six cuts per 10 s; a clip with none yields zero; onset test on synthesized clicks.
- [ ] The tool never runs in tests or smoke; only the analyser does.

## Blocked by

- Blocked by `issues/023-sweep-detector-t6-catalogue-measure.md`

## User stories addressed

- User story 49
