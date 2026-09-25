# 036 — Reference library tool: download, frames, cut and motion analysis, README writer

## Type

HITL — needs new package: `yt-dlp` (`uv add yt-dlp`). The operator approves; then this ticket becomes AFK. The approval waits on the tool verdicts required under "Reference tooling" below.

## Parent PRD

`issues/prd.md`

## What to build

`shortsmith reference add <url|channel> --category <c>` downloads a short into the git-ignored `work/reference/<category>/`, extracts frames with the documented ffmpeg command, measures the pattern data that needs no OCR or face detector (cuts per 10 s by scene-change detection, visual-change rate by frame-difference energy, transition density, sound-hit density by onset detection on the non-speech band), tags each figure MEASURED or ESTIMATED, and writes `docs/reference/<category>/README.md` in the existing format. The analyser is pure code over a video file and boundary-tested on a synthetic clip. Caption pages, mode timeline and hook description follow in 037.

Covers PRD `reference` (tool and analyser). Decisions 10.3, 12.2.

## Reference tooling

Read `docs/reference-tooling.md` and `docs/references.md` in full before proposing.

Before implementation, write into this ticket one verdict per tool in `docs/reference-tooling.md`: Gemini API, Demucs, PySceneDetect, and the Qwen cost escape hatch (Qwen is the operator's standing call: acknowledge it and say where it would slot in, do not re-decide it). Each verdict states:

- use or reject, with the reason; on reject, what this ticket does instead;
- dependency footprint (packages, binaries, model weights, GPU need, install size);
- impact on the `046` Docker image;
- per-reference API cost (units per reference and the resulting estimate; zero for local tools).

Silence on a tool is not a verdict.

Long-form input: `reference add` accepts a long-form video (Tier A `id00R-3OmJ0` in `docs/references.md`). The entry is tagged technique-only and its figures are excluded from every pacing statistic (cuts per 10 s, visual-change rate, transition density, sound-hit density, and anything averaged into the category).

## Acceptance criteria

- [ ] Tool verdicts for Gemini API, Demucs, PySceneDetect and Qwen are written in this ticket, each with use/reject and reason, dependency footprint, `046` Docker impact and per-reference API cost, before implementation starts.
- [ ] Analysis output includes an effect inventory per reference: every visual effect/animation observed, with timestamp, duration, and what it emphasises (word / number / image / speaker) - including effects that have no name in our component registry, listed as 'unregistered'.
- [ ] `python -m shortsmith.reference add <url> --category <c>` downloads with yt-dlp, stores `work/reference/<category>/<id>.mp4` (git-ignored), extracts `frames/*.jpg` with the README's ffmpeg command.
- [ ] `reference.analyse(video) -> PatternData` measures cuts per 10 s, visual-change rate, transition density (fraction of cuts with motion blur or scale change in the adjacent frames), sound-hit density (onsets per 10 s in the non-speech band); each figure tagged MEASURED; caption pages, mode timeline and hook structure written as ESTIMATED placeholders until 037.
- [ ] The category README is created or appended in the existing `docs/reference/README.md` format with the entry, figures, tags and the source URL; the pack version is bumped.
- [ ] Boundary test, `tests/test_reference.py`: a synthetic clip with six hard cuts yields six cuts per 10 s; a clip with none yields zero; onset test on synthesized clicks.
- [ ] The tool never runs in tests or smoke; only the analyser does.
- [ ] A long-form input is accepted and its entry is tagged technique-only; a test shows a technique-only entry is left out of the category's pacing statistics.

## Blocked by

- Nothing; 023 is done.

## User stories addressed

- User story 49
