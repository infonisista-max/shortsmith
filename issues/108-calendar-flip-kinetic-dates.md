# 108 — Calendar flip and kinetic dates (083 part 3)

## Type

AFK (touches `src/remotion`)

## Parent PRD

`issues/prd.md`

## What to build

`calendar_flip` / `calendar_page_peel`, built from the cards' `motion` data: a year or
date lands as a calendar page flipping or peeling to the spoken year. Vishva scripts carry
many years, and today every year is the same yellow stamp (12 stamps in run05). The
planner may choose it for a year beat instead of a stamp; its numbers live in front
matter.

**Stamp placement on maps (operator, 30 Sep 2026, folded in here):** run05 b07's yellow
stamp still lands over the named country after 104, because stamp placement does not know
where the map's content is. On a map beat, the stamp (and a calendar, if one lands there)
avoids the named area's box, the target circle, the angled tag and the marker pills that
104 draws (`render.py` ~2092/2428 already keep the tag clear of the stamp; do the
reverse). If no spot is free, it moves to the free corner with the least map content.
Margins go in front matter.

## Acceptance criteria

- [ ] Test: a map beat with `region: Saudi Arabia` and a stamp puts the stamp's box
      outside the highlighted country's box, the circle, the tag and every pill; with no
      free spot, it goes to the emptiest corner.

- [ ] A Remotion test (flips from one year to another and lands on the spoken word) +
      bench.
- [ ] The grammar accepts it; effect_map points the two names at it.
- [ ] Smoke green.

## Blocked by

106.

## User stories addressed

Operator, 30 Sep 2026: 083.
