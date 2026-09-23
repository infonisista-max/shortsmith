# 021 — Charts from planner series and labelled diagrams with code-rendered labels

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The other two infographic kinds. `chart` is drawn in code from the planner's `series` and `labels` in the style palette. `infographic` (labelled diagram) is a label-free base image, sourced through the asset step or generated with "no text, no labels" appended, plus code-rendered `labels: [{text, x%, y%, anchor}]`; labels appear statically here and fly in from 029. Text never goes inside a generated image.

Covers PRD `infographics` (charts, diagrams), render `chart` and `infographic`. Decisions 9.2, 9.3, 5.5.

## Acceptance criteria

- [x] `infographics.resolve_chart(recipe) -> ChartLayout` supports bar, line and a two-value comparison, scales axes from the real series, formats numbers per the style, and refuses an empty or mismatched series with a validation error.
- [x] Remotion `chart` component draws the layout with the style palette, axis labels outside the safe area, and a title strip; registered.
- [x] `infographics.resolve_diagram(recipe, asset) -> DiagramLayout` converts percentage positions to pixels on the classified asset and asserts labels stay inside the safe area.
- [x] The generator prompt for a diagram base always appends "no text, no labels"; the asset step marks the asset as a diagram base so it is never shown as a bare `photo`.
- [x] Remotion `infographic` component composes the base and the labels; registered.
- [x] Unit tests: chart scaling on known series, percentage to pixel mapping, safe-area rejection for a label at y 95 %.
- [x] Smoke: FakePlanner's `chart` and `infographic` beats render; gates pass.

## Blocked by

- Blocked by `issues/019-image-generator.md`

## User stories addressed

- User story 23

## Notes

- Both kinds are measured in Python (`infographics.py`) and animated by the components,
  the same division of labour as the set pieces of 026 / 027. Every count, duration and
  number format comes from `broll.motion.chart` / `broll.motion.infographic` in the
  style front matter (1.2); the geometry constants are this engine's look.
- A bad chart series is refused, a label outside the safe area is refused, but labels
  past `labels_max` are cut, not refused: dropping a data point lies about the data,
  losing a label does not.
- The planner prompt went to `v3` (the picture file gained the infographic rules). The
  hand-built planner fixtures under `tests/fixtures/claude_cli/` and
  `tests/fixtures/anthropic/` were regenerated from `FakePlanner` so their `chart` and
  `infographic` beats carry the new fields and pass the grammar.
- Verified: ruff, pyright, 901 pytest, `npm test`, `npm run typecheck`, and the smoke —
  T1 T2 T3 T4 T8 T9 pass; the chart frame (b06) and the diagram labels (b07) were read
  off the render. Taste verdict on the look is still the operator's.
- Next: `029-label-flyin-counter` makes these labels fly in rather than appear.
