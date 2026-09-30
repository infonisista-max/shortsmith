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

## Acceptance criteria

- [ ] A Remotion test (flips from one year to another and lands on the spoken word) +
      bench.
- [ ] The grammar accepts it; effect_map points the two names at it.
- [ ] Smoke green.

## Blocked by

106.

## User stories addressed

Operator, 30 Sep 2026: 083.
