# 051 — Cards and the split composite clear the measured PIP circle

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

013 measures the face and grows the circle to `pip.large_face_diameter` (340), upward from
the caption block's edge, so its top is 40 px above the style's fixed `pip.top`. The card
(`render.card_visual`) and the split composite (`render.split_visual`) still place their
bottom edge against `numbers.broll.pip_top - PIP_GAP_PX`, the fixed 960, so on a
large-face job the 32 px gap the reference cards keep above the circle is gone and the
circle overlaps the card by 8 px (928 vs 920). `build_spec` already holds the measured
`PipGeometry` but builds the visuals from the style number first.

Fix: the two placements read the circle top the render will actually draw. `build_spec`
derives the geometry (measured `pip`, else `fixed_pip`) before `_visuals` and `set_piece`,
and passes its `top` down; `BrollNumbers.pip_top` stops being the source of truth for
placement (keep it only if something else still needs the style value). Unmeasured specs
(the renderer's own tests, `fixed_pip`) place exactly as today, so 004/008 numbers hold.
No other placement (hook cards, list, wall, stamp, lower-third) changes.

Covers PRD `presenter` (3.3), `render` (4.1). Decisions 3.3, 6.3 (`PIP_GAP_PX`: "the
reference cards end ~35 px above the PIP circle"). Flagged in the 013 done-commit notes.

## Acceptance criteria

- [x] With a measured large-face `PipGeometry` (diameter 340, top 920) the card's lowest
      point over its beat (`render.card_bottom`) is `920 - PIP_GAP_PX`, never lower;
      with the normal circle (top 960) it is `960 - PIP_GAP_PX`, as today.
- [x] The same for the split composite's lowest point (tilt included).
- [x] `build_spec(pip=None)` places both exactly as before the ticket (existing
      `test_render` placement tests pass unchanged).
- [x] A pipeline-level test: a job whose fake detector reports a large face renders a
      RenderSpec where every card/split beat's bottom stays above the PIP top minus the gap.
- [x] Cards never fall below `broll.card_max_bottom_y` either (the `min(...)` stays).
- [x] Smoke green with T1–T13 passing on the fixture (the gate is all thirteen as of
      c9cf454; the fixture face is 40–42 %, so it takes the normal circle); the contact
      sheet PIP row is untouched.

## Done (2026-09-25)

`build_spec` derives the geometry it draws first (`pip or fixed_pip(...)`) and passes
`geometry.top` into `_visuals` and `set_piece`, so `card_visual` and `split_spec` place
against the circle the render actually draws. Both take a `pip_top` keyword; the shared
`_card_limit` keeps the `min(pip_top - PIP_GAP_PX, card_max_bottom_y)` clamp. When
`pip_top` is not given (the renderer's own direct-call tests) it falls back to
`BrollNumbers.pip_top`, the style value, which is kept for that fallback only; `build_spec`
always passes the geometry, so the style number is no longer the placement's source of
truth on any job. For `explainer` `fixed_pip(...).top == pip.top == 960`, so an unmeasured
spec places exactly as before (only `explainer` loads to `StyleNumbers` today; the three
drafts lack `broll.motion.list`). `render.split_bottom` is the split's `card_bottom`
twin (tilt included). No other placement changed; nothing under `src/remotion/` changed.

Tests: `test_render` parametrised card and split placement at tops 920 and 960, a
`split_bottom` tilt test, and a `build_spec` test with a large-face measurement that
also re-asserts the unmeasured numbers; `test_pipeline` runs a job through the default
`FakeFaceDetector` (520 px box, over 45 % of 1080, so diameter 340 / top 920 - the bug's
exact case, which failed red before the fix at 928 vs 920) and reads `render_spec.json`.

ruff clean, pyright 0 errors, pytest 1230 passed (run as four foreground chunks: the
whole suite takes ~10 min 15 s, over the 10-minute foreground cap); smoke ok, T1-T13
pass, the fixture job's `render_spec.json` shows pip 960/300 with the card and split
bottoms at 928 as before.

## Blocked by

- Nothing; 013 is done.

## User stories addressed

- User story 14
- User story 43
