# 026 — Hook cards, finale, stamp and lower_third components

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The mandatory set-pieces and the two overlay kinds. The two-beat hook renders: cold open with punch-in, then hook cards with the title in caption typography and three cards from plan assets in priority order, one centred card when fewer than three exist. The finale card carries the presenter in its centre circle for 0.8–1.2 s with captions hidden. `stamp` is rotated text landing in 0.16 s with shake, palette yellow/green/red, top 60 % only; number and quote beats stamp over the previous beat's asset with its Ken Burns continued. `lower_third` is name plus role with a 0.35 s fade at y 1150–1240, suppressed on beats with a two-line caption page.

Covers PRD render (`hook_cards`, `finale`, `stamp`, `lower_third`). Decisions 3.2, 3.4, 4.1, 4.2, 6.1, 6.3, 7.1 (floor hits already fire on these events).

## Acceptance criteria

- [x] `hook_cards` component: title ≤ 8 words in caption typography, three cards from `hook.card_asset_ids` in order, spring fly-ins, one centred card when fewer than three assets resolved; never a blank frame.
- [x] Cold-open beat renders `full` with the research §2 punch-in.
- [x] `finale` component: style palette card, presenter cut in the centre circle, length from `finale.length` within 0.8–1.2 s, captions absent from the finale word (already paged that way in 010; the renderer asserts no page overlaps).
- [x] `stamp` component: rotation, land 0.16 s with shake, palette from front matter, geometry clamped to the top 60 % (y < 1152) and outside the right 140 px; number/quote beats reuse the previous asset with continued Ken Burns and no new asset in the manifest.
- [x] `lower_third` component: fade 0.35 s, y 1150–1240, suppressed where `beats_with_two_lines` says so; entity beats with a `lower_third` event render it.
- [x] All four registered; the explainer's `requires_components` gains them.
- [x] Unit tests on RenderSpec construction: fewer than three hook assets → one card; stamp above y 1152 rejected; lower-third suppression on a two-line beat.
- [x] Smoke: the fixture short opens with the two-beat hook and ends with the finale; gates pass.

## Notes from 010

- `RenderSpec.beats_with_two_lines` (beat ids a two-line page overlaps in time) is already filled from `work/captions.json`; `types.ts` has the field. Captions are already absent from the finale beat's start (pages end at or before it).

## Blocked by

- Blocked by `issues/016-asset-step-ladder-rights.md`
- Blocked by `issues/010-caption-pager-full-rules.md`

## Notes from 016

- Rescued beats carry their stamp word in `work/assets.json` (`BeatAsset.stamp`, rung 3 and 4; the beat's own event text, else the longest query word). A rung-4 beat arrives in the RenderSpec as `pip` with no visual: the stamp over the gradient is this ticket's to draw.
- Hook cards and the finale find their assets through `manifest.aliases` (planned id -> id actually shown, None for rung 4); `rights.shown` already counts every hook card on the hook-cards beat.
- The card's caption strip shows the beat's `lower_third` text today (`render._visuals`); decide here whether the lower-third is suppressed on card beats or the strip takes other text. The ring on a `ring` event lands at the framing's focus 0.2 s into the beat.

## What was done

- Every set piece is **measured and placed in Python**, animated in TSX: `BeatSpec` gained
  `hook` / `finale` / `stamp` / `lower_third` / `punch_in`, so a geometry rule is a unit test
  on a spec, never a frame grab. `captions.measure` was lifted out of `text_width` so the set
  pieces measure titles and labels in the same bundled fonts the pager uses.
- The stamp is **clamped, not rejected**: the AC asks for both, and clamping is what the
  other line of the same AC says. The text shrinks in 4 px steps from 92 px until it fits
  between the left margin and the 140 px right rail, then the tilted box is pushed up until
  it ends above `broll.stamp_max_y_fraction * 1920`. A long stamp word therefore lands small
  rather than failing the build.
- The finale **is** a build failure, twice: a beat outside `finale.min_s`–`max_s`, or any
  caption page running into it (6.1), raises `RenderError` rather than reaching the screen.
- 4.2's "reuse the previous asset" is `render.continued`: a `number` / `quote` beat on the
  same asset id picks the Ken Burns up at the previous beat's `scale_to` and carries the same
  rate, never restarting, and does not advance the motion index.
- The 016 question is answered: **the card strip wins**. A beat whose card already shows the
  lower-third text draws no separate label, so the two never double up.
- Style front matter supplies the four `broll.motion` rows, both y bands, the card count,
  the stamp palette name and `finale.min_s`/`max_s`; reference-frame geometry stays in
  `render.py` constants next to the 016 card constants.

Loops: ruff, pyright (0 errors), pytest (816 passed), `npm run typecheck`, `npm test` (8),
and the smoke all pass. `out/qa.json` read directly: T1 T2 T3 T4 T8 T9 all `passed: true`.
Contact sheet confirms the two-beat hook (cold open → title plus three cards), stamps on
b03/b06, the b04 card strip with no duplicate label, and the finale circle with the payoff
word.

## Notes for next iteration

- Every stamp takes its palette's **lead colour**. Picking the green payoff or the red
  counter needs a sentiment field the plan does not carry; 030 or the critic tickets may want
  to add one rather than guessing from the text.
- `LOWER_THIRD_PAD_X` (24) exists in `render.py` for the width measurement and again as a
  literal in `lower_third.tsx`. They agree today; if either moves the label will mis-measure.
- The finale reuses the hook's card sources, so a short whose hook resolved nothing shows the
  circle and payoff word alone. That is the "never a blank frame" rule holding, not a bug.

## User stories addressed

- User story 11
- User story 13
- User story 19
- User story 31
