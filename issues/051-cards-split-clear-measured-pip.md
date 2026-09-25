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

- [ ] With a measured large-face `PipGeometry` (diameter 340, top 920) the card's lowest
      point over its beat (`render.card_bottom`) is `920 - PIP_GAP_PX`, never lower;
      with the normal circle (top 960) it is `960 - PIP_GAP_PX`, as today.
- [ ] The same for the split composite's lowest point (tilt included).
- [ ] `build_spec(pip=None)` places both exactly as before the ticket (existing
      `test_render` placement tests pass unchanged).
- [ ] A pipeline-level test: a job whose fake detector reports a large face renders a
      RenderSpec where every card/split beat's bottom stays above the PIP top minus the gap.
- [ ] Cards never fall below `broll.card_max_bottom_y` either (the `min(...)` stays).
- [ ] Smoke green with T1–T13 passing on the fixture (the gate is all thirteen as of
      c9cf454; the fixture face is 40–42 %, so it takes the normal circle); the contact
      sheet PIP row is untouched.

## Blocked by

- Nothing; 013 is done.

## User stories addressed

- User story 14
- User story 43
