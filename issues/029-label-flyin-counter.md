# 029 — label_flyin and counter components

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Sequential label fly-ins on the labelled diagram from 021 and an animated counter for number beats: digits count from a start value to the target over the beat, formatted per the style, landing with a stamp-style hit so the floor's bass fires on it.

Covers PRD render (`label_flyin`, `counter`). Decisions 9.2, 9.3, 4.2, 7.1.

## Acceptance criteria

- [ ] `label_flyin`: labels from `DiagramLayout` enter one after another with spring fly-ins from the nearest frame edge, anchored per label; stagger from beat length.
- [ ] `counter`: from/to values, unit and format from the plan; eases to the target and lands in the last 0.16 s with the stamp shake; placed in the top 60 %; counts as a `number` beat over the previous asset.
- [ ] Registered; explainer `requires_components` gains them.
- [ ] Unit tests on stagger timing and counter formatting (Indian and international digit grouping); smoke renders both beats and gates pass.

## Blocked by

- Blocked by `issues/021-charts-labelled-diagrams.md`
- Blocked by `issues/026-hook-cards-finale-stamp-lower-third.md`

## User stories addressed

- User story 19
- User story 24
