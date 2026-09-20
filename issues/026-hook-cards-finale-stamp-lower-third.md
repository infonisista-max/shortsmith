# 026 — Hook cards, finale, stamp and lower_third components

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The mandatory set-pieces and the two overlay kinds. The two-beat hook renders: cold open with punch-in, then hook cards with the title in caption typography and three cards from plan assets in priority order, one centred card when fewer than three exist. The finale card carries the presenter in its centre circle for 0.8–1.2 s with captions hidden. `stamp` is rotated text landing in 0.16 s with shake, palette yellow/green/red, top 60 % only; number and quote beats stamp over the previous beat's asset with its Ken Burns continued. `lower_third` is name plus role with a 0.35 s fade at y 1150–1240, suppressed on beats with a two-line caption page.

Covers PRD render (`hook_cards`, `finale`, `stamp`, `lower_third`). Decisions 3.2, 3.4, 4.1, 4.2, 6.1, 6.3, 7.1 (floor hits already fire on these events).

## Acceptance criteria

- [ ] `hook_cards` component: title ≤ 8 words in caption typography, three cards from `hook.card_asset_ids` in order, spring fly-ins, one centred card when fewer than three assets resolved; never a blank frame.
- [ ] Cold-open beat renders `full` with the research §2 punch-in.
- [ ] `finale` component: style palette card, presenter cut in the centre circle, length from `finale.length` within 0.8–1.2 s, captions absent from the finale word (already paged that way in 010; the renderer asserts no page overlaps).
- [ ] `stamp` component: rotation, land 0.16 s with shake, palette from front matter, geometry clamped to the top 60 % (y < 1152) and outside the right 140 px; number/quote beats reuse the previous asset with continued Ken Burns and no new asset in the manifest.
- [ ] `lower_third` component: fade 0.35 s, y 1150–1240, suppressed where `beats_with_two_lines` says so; entity beats with a `lower_third` event render it.
- [ ] All four registered; the explainer's `requires_components` gains them.
- [ ] Unit tests on RenderSpec construction: fewer than three hook assets → one card; stamp above y 1152 rejected; lower-third suppression on a two-line beat.
- [ ] Smoke: the fixture short opens with the two-beat hook and ends with the finale; gates pass.

## Blocked by

- Blocked by `issues/016-asset-step-ladder-rights.md`
- Blocked by `issues/010-caption-pager-full-rules.md`

## User stories addressed

- User story 11
- User story 13
- User story 19
- User story 31
