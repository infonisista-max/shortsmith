# 021 — Charts from planner series and labelled diagrams with code-rendered labels

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The other two infographic kinds. `chart` is drawn in code from the planner's `series` and `labels` in the style palette. `infographic` (labelled diagram) is a label-free base image, sourced through the asset step or generated with "no text, no labels" appended, plus code-rendered `labels: [{text, x%, y%, anchor}]`; labels appear statically here and fly in from 029. Text never goes inside a generated image.

Covers PRD `infographics` (charts, diagrams), render `chart` and `infographic`. Decisions 9.2, 9.3, 5.5.

## Acceptance criteria

- [ ] `infographics.resolve_chart(recipe) -> ChartLayout` supports bar, line and a two-value comparison, scales axes from the real series, formats numbers per the style, and refuses an empty or mismatched series with a validation error.
- [ ] Remotion `chart` component draws the layout with the style palette, axis labels outside the safe area, and a title strip; registered.
- [ ] `infographics.resolve_diagram(recipe, asset) -> DiagramLayout` converts percentage positions to pixels on the classified asset and asserts labels stay inside the safe area.
- [ ] The generator prompt for a diagram base always appends "no text, no labels"; the asset step marks the asset as a diagram base so it is never shown as a bare `photo`.
- [ ] Remotion `infographic` component composes the base and the labels; registered.
- [ ] Unit tests: chart scaling on known series, percentage to pixel mapping, safe-area rejection for a label at y 95 %.
- [ ] Smoke: FakePlanner's `chart` and `infographic` beats render; gates pass.

## Blocked by

- Blocked by `issues/019-image-generator.md`

## User stories addressed

- User story 23
