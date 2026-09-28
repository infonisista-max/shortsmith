# 072 — Map labels say the name as written, never cover another label, and every dot stays visible

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Run04 (job `20260928-140620-f774e1`, vishva). Operator's phone verdict: "When I say the
king lived in foreign countries (Greece etc.), 1-2 countries were matched wrong and shown
wrong on the map."

What happened:

- The line is "…बेटियां और बेटे दोनों पॉलेंड, ग्रीस, अमेरिका इन जैसे देशों में रहते थे"
  (words 131–133, 43.04–44.74 s).
- Beat b20 (42.0–46.3 s in the output) is a map with `bbox [-125, 10, 60, 65]`. Its
  markers are Riyadh, Poland, Greece and United States (`plan.json:792-843`).
- Every name resolved to the right place (`geo.py` exact lookup). Nothing was
  mis-matched. What the operator saw was the drawing:
  1. The pill shows the gazetteer's canonical name, not the planner's
     (`infographics.py:679-681,701`). "United States" became "United States of America",
     a 504 px pill.
  2. A pill always sits to the right of its dot, at the dot's y. It flips left only at
     the right rail (`infographics.py:683-686`), and nothing checks pills against each
     other. The USA (lat 39.54) and Greece (39.49) share a row. In `render_spec.json`
     (`:4438-4462`), the USA pill spans x 285–789 and Greece's starts at x 721.
  3. `map.tsx:74-96` draws each marker, dot and pill together, in array order. The USA
     comes last, so "United States of America" covers Greece's pill *and* Greece's dot.
     Riyadh's pill (flipped left) sits right under it.

  On a phone, that reads as "USA is where Greece is".

Operator decisions (run04 QA, 29 Sep 2026):

- **Label = name as written.** The pill shows the name the planner wrote (`markers[].name`).
  The gazetteer supplies the coordinate only.
- **No overlapping pills.** After the first layout, a collision pass tries, per
  overlapping pill: flip to the other side of its dot, then step it up or down (the step
  in `motion.map` front matter) until it overlaps no other pill and no other marker's
  dot, and stays inside the safe band (`safe_area.py`). The order is fixed and
  deterministic. If none works, the build fails with a `LayoutError` naming the markers,
  as a label outside the safe area does today.
- **Dots above pills.** The renderer draws every pill first and every dot after, so a
  dot is never hidden.

Not in scope: the operator did not ask for a spoken-places rule. The planner's unspoken
Riyadh marker stays allowed.

## Acceptance criteria

- [x] Run04's b20 markers and bbox (copied into a test; no media) lay out with the
      labels "Riyadh", "Poland", "Greece", "United States". No two pill boxes intersect,
      no pill box covers another marker's dot, and every box is inside x 60–940 and the
      safe top/bottom zones.
- [x] A property-style test over random marker sets inside a bbox: every layout the pass
      accepts has no overlaps. A set it cannot separate raises `LayoutError` naming the
      markers.
- [x] `map.tsx` draws all pills before all dots. `npm run typecheck` and `npm test`
      pass, with a test on the draw order.
- [x] The collision step is a `motion.map` front-matter number in every style that
      enables `map`, with bumped `version`s and updated pins.
- [x] Render run04's b20 before and after, saved to `work/072/` (git-ignored), with the
      paths listed in the done note for the operator's phone verdict. The agent does not
      judge the look.
- [x] Smoke passes T1–T13 on explainer, vishva and fastfacts.
- [x] Ruff, pyright and every test file are green in foreground chunks.
- [x] Done note: the amendment line for 9.3 (map labels as written, no overlap, dots on
      top) for the operator to paste. Also what to check on run05: every country's label
      sits by its own dot, and no label hides another.

## Blocked by

- Nothing.

## Done (29 Sep 2026)

- **Label = name as written.** `infographics._marker_layouts` measures and draws the
  planner's `markers[].name`. The gazetteer supplies `lat`/`lon` only. Run04's USA pill
  is now "United States" (x 285–572) instead of "United States of America" (x 285–789).
- **Collision pass.** Each pill's candidates come in a fixed order. First its own side
  (right of the dot, or left when the right rail is near), then the other side. Then
  each step up and down by `motion.map.label_step_px`, on both sides, up to
  `label_steps_max` steps. A candidate is kept only if it is inside the safe area
  (x 60–940, y 250 to `card_max_bottom_y`) and covers no other marker's dot (the dot
  plus its ring). The pass then gives one pill to each marker so that no two pills meet.
  It picks the arrangement with the least total movement: a pill that is already clear
  stays put, and a flip is tried before a step. Ties go to the earlier marker. It is a
  small depth-first search that drops later candidates each choice would cover and stops
  on any branch that cannot beat the best found so far. There are at most
  `markers_max` (6) markers, so it stays fast.
  - A marker with no candidate, or a set the pass cannot separate, raises
    `infographics.LayoutError`, which names the markers. It is a subclass of
    `InfographicError`, so `render.map_layout` still turns it into a `RenderError`
    naming the beat.
- **Deviation from the ticket's literal wording.** The ticket describes moving "per
  overlapping pill" in marker order. On run04's b20, that greedy order fails. Riyadh's
  pill is flipped left by the rail, and it overlaps Greece's first pill by 0.13 px.
  Every step for Greece then hits either Poland's pill (right side) or Poland's dot
  (left side). The least-movement search keeps the same order of preference (stay, flip,
  step) and the same determinism, and it finds: Poland flipped left, Greece up one step.
- **Style numbers.** `motion.map.label_step_px: 24` and `label_steps_max: 3` (at most
  72 px, just over one pill height of 64.6 px, so a pill can clear a neighbour directly
  above or below it). They are in explainer (15), hitech (14), footage, vishva and
  fastfacts (5). educational and animated have no map row and stay at 13. Pins are
  updated in `test_styles`, `test_recipe_styles`, `test_speech_band_margin` and
  `test_bed_audible`, and `styles/README.md` names the two numbers. They are starting
  values for the phone verdict.
- **Dots above pills.** `map.tsx` splits `Marker` into `MarkerPill` and `MarkerDot`.
  `MapBase` (static markers) and `PinDrop` (028) draw every pill first and every dot
  after, and the splash ring goes with the dot. `registry.test.mjs` checks the order in
  both files.
- **Run04 b20 after the fix** (dot → pill box as left, top, right, bottom):
  Riyadh (790, 896) → 599, 864, 767, 928 (unchanged). Poland (690, 766) → 500, 733,
  667, 798 (flipped left). Greece (698, 831) → 721, 775, 887, 840 (one step up).
  United States (262, 831) → 285, 799, 572, 864.
- **For the operator's phone verdict** (git-ignored, the agent does not judge the look):
  - before: `work/072/before_0.jpg` (mid-drop) and `work/072/before_1.jpg` (landed),
    taken from run04's `out/short.mp4`;
  - after: `work/072/after_b20.mp4` (b20 alone over the same presenter span),
    `work/072/after_0.jpg` and `work/072/after_1.jpg`;
  - to regenerate: `uv run python work/072/render_b20.py`.
- Tests: `tests/test_map_labels.py` (new) covers run04's b20 through the bundled
  gazetteer, a flip case, the style numbers, a 300-set random property test with seed
  72 (it asserts that both accepted and refused sets occur), and an unseparable set.
- Loops: ruff and pyright are green, and all 62 test files are green in foreground
  chunks. Smoke passes T1–T13 on explainer, vishva and fastfacts, and the kept
  explainer `qa.json` was read. `npm run typecheck` and `npm test` (28) are green.

**Amendment line for the operator to paste:**

- 9.3: "A map label says the name the planner wrote; the gazetteer gives the coordinate
  only. No label covers another label or another marker's dot. A label that would flips
  to the other side of its dot, then steps up or down by the style's
  `motion.map.label_step_px` (at most `label_steps_max` steps), always inside the safe
  area; a map that cannot be separated fails the build naming its markers. Every dot is
  drawn above every label."

**Check on run05:** every country's label sits next to its own dot, no label hides
another label or a dot, and every label reads as the spoken name. Confirm or change the
24 px step and the 3-step limit.

## User stories addressed

- Operator, run04 QA (29 Sep 2026): "When I say the king lived in foreign countries
  (Greece etc.), 1-2 countries were matched wrong and shown wrong on the map."
