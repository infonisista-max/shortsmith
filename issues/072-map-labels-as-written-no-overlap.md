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

- [ ] Run04's b20 markers and bbox (copied into a test; no media) lay out with the
      labels "Riyadh", "Poland", "Greece", "United States". No two pill boxes intersect,
      no pill box covers another marker's dot, and every box is inside x 60–940 and the
      safe top/bottom zones.
- [ ] A property-style test over random marker sets inside a bbox: every layout the pass
      accepts has no overlaps. A set it cannot separate raises `LayoutError` naming the
      markers.
- [ ] `map.tsx` draws all pills before all dots. `npm run typecheck` and `npm test`
      pass, with a test on the draw order.
- [ ] The collision step is a `motion.map` front-matter number in every style that
      enables `map`, with bumped `version`s and updated pins.
- [ ] Render run04's b20 before and after, saved to `work/072/` (git-ignored), with the
      paths listed in the done note for the operator's phone verdict. The agent does not
      judge the look.
- [ ] Smoke passes T1–T13 on explainer, vishva and fastfacts.
- [ ] Ruff, pyright and every test file are green in foreground chunks.
- [ ] Done note: the amendment line for 9.3 (map labels as written, no overlap, dots on
      top) for the operator to paste. Also what to check on run05: every country's label
      sits by its own dot, and no label hides another.

## Blocked by

- Nothing.

## User stories addressed

- Operator, run04 QA (29 Sep 2026): "When I say the king lived in foreign countries
  (Greece etc.), 1-2 countries were matched wrong and shown wrong on the map."
