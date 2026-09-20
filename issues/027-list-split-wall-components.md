# 027 — list, split and wall set-piece components

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Three tier-1 set-pieces the planner may use up to `set_piece_max_s`: `list` (sequential items appearing with spring fly-ins), `split` (two assets side by side, for two-entity beats, in the news-card composite pattern from 5.2 with circular logo badge and title strip), and `wall` (a grid of cards for a many-item beat). Each takes assets from the manifest through the same classification and re-dress rules.

Covers PRD render (`list`, `split`, `wall`). Decisions 4.1, 5.2, 5.3, 9.2, 9.4.

## Acceptance criteria

- [ ] `list` component: up to six items, each with text and optional asset, sequential spring entry, text outside the safe area.
- [ ] `split` component: two re-dressed portraits or cards side by side, circular badge overlapping a corner, title strip with highlighted keywords; supports two-entity beats.
- [ ] `wall` component: 2×2 to 3×3 grid of cards with staggered entry and Ken Burns on each cell.
- [ ] All three read the assets by id from the manifest; a missing asset is a render-spec error, never a blank cell.
- [ ] Registered; explainer `requires_components` gains them; the grammar's set-piece max applies (already in 009).
- [ ] Unit tests on spec construction for each; smoke renders the FakePlanner's `list`, `split` and `wall` beats and gates pass.

## Blocked by

- Blocked by `issues/026-hook-cards-finale-stamp-lower-third.md`

## User stories addressed

- User story 15
- User story 24
