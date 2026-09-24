# 029 — label_flyin and counter components

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Sequential label fly-ins on the labelled diagram from 021 and an animated counter for number beats: digits count from a start value to the target over the beat, formatted per the style, landing with a stamp-style hit so the floor's bass fires on it.

Covers PRD render (`label_flyin`, `counter`). Decisions 9.2, 9.3, 4.2, 7.1.

## Acceptance criteria

- [x] `label_flyin`: labels from `DiagramLayout` enter one after another with spring fly-ins from the nearest frame edge, anchored per label; stagger from beat length.
- [x] `counter`: from/to values, unit and format from the plan; eases to the target and lands in the last 0.16 s with the stamp shake; placed in the top 60 %; counts as a `number` beat over the previous asset.
- [x] Registered; explainer `requires_components` gains them.
- [x] Unit tests on stagger timing and counter formatting (Indian and international digit grouping); smoke renders both beats and gates pass.

## Notes

- Built by one session that was cut off before it could commit. The next session
  checked the work against these criteria, ran every loop green (ruff, pyright,
  975 pytest, npm test and typecheck, smoke with T1-T4, T8 and T9 passing) and
  committed it.
- The contact sheet samples at 1 fps and does not include the counter beat (b06,
  2.5-3.0 s). The smoke checks the counter from its spec. The operator has not yet
  judged how it looks.

## Blocked by

- Blocked by `issues/021-charts-labelled-diagrams.md`
- Blocked by `issues/026-hook-cards-finale-stamp-lower-third.md`

## User stories addressed

- User story 19
- User story 24
