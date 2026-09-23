# 027 — list, split and wall set-piece components

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Three tier-1 set-pieces the planner may use up to `set_piece_max_s`: `list` (sequential items appearing with spring fly-ins), `split` (two assets side by side, for two-entity beats, in the news-card composite pattern from 5.2 with circular logo badge and title strip), and `wall` (a grid of cards for a many-item beat). Each takes assets from the manifest through the same classification and re-dress rules.

Covers PRD render (`list`, `split`, `wall`). Decisions 4.1, 5.2, 5.3, 9.2, 9.4.

## Acceptance criteria

- [x] `list` component: up to six items, each with text and optional asset, sequential spring entry, text outside the safe area.
- [x] `split` component: two re-dressed portraits or cards side by side, circular badge overlapping a corner, title strip with highlighted keywords; supports two-entity beats.
- [x] `wall` component: 2×2 to 3×3 grid of cards with staggered entry and Ken Burns on each cell.
- [x] All three read the assets by id from the manifest; a missing asset is a render-spec error, never a blank cell.
- [x] Registered; explainer `requires_components` gains them; the grammar's set-piece max applies (already in 009).
- [x] Unit tests on spec construction for each; smoke renders the FakePlanner's `list`, `split` and `wall` beats and gates pass.

## Blocked by

- Blocked by `issues/026-hook-cards-finale-stamp-lower-third.md`

## Notes for 030

- `broll.motion` gained a `list`, `split` and `wall` row; `explainer.requires_components`
  is now `[captions, pip, hook_cards, finale, stamp, lower_third, list, split, wall]`.
  030 completes the list with the remaining tier-1 components and the six transitions.
- The fake plan's b08/b09/b10 carry real `items`, so the smoke exercises all three.
  The item assets are ids other beats already source, so the asset count is unchanged.
- The wall's entry stagger is a fixed `i * 0.1 s` and is not compressed to the beat: on
  the 6 s fixture a 0.5 s wall beat leaves the last cell mid-flight at the cut. Real
  wall beats run to `set_piece_max_s`, so this is a fixture-scale artifact, not a bug -
  but 033's critic may want the stagger fitted to the beat length.

## User stories addressed

- User story 15
- User story 24
