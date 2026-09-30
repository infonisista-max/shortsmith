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

- [x] Test: a map beat with `region: Saudi Arabia` and a stamp puts the stamp's box
      outside the highlighted country's box, the circle, the tag and every pill; with no
      free spot, it goes to the emptiest corner.

- [x] A Remotion test (flips from one year to another and lands on the spoken word) +
      bench.
- [x] The grammar accepts it; effect_map points the two names at it.
- [x] Smoke green.

## Blocked by

106.

## User stories addressed

Operator, 30 Sep 2026: 083.

## Done note (30 Sep 2026)

- Evidence: the v2 cards carry no calendar entry (M78CO3Ybr7U's 57.7 s is a plain cut
  "to calendar demonstration"); the v1 cards give the on-screen lengths: QjwDTLPLJ6c
  `calendar_flip` 1.4 s, M78CO3Ybr7U `calendar_page_peel` 1.5 s, so lead_s 0.25 +
  flip_s 0.4 + hold_max_s 0.85 = 1.5 s. **Derived, no card number**: flip_s 0.4 (the
  slowest card entrance), lead 0.25, the page 440 x 340 with an 80 px header and type
  120 -> 64 px ("29 FEB 2024" fits), white page / red header, chars_max 12; the caps:
  explainer 1 a minute (M78, Qjw one each), vishva 2 (no vishva card has one; the ticket's
  run05 carried 12 year stamps), stamp_margin_px 24 (the text pop's clearance).
- Contracts: `CalendarPlan` / `Beat.calendar` (src/shortsmith/contracts.py:472),
  `CalendarSpec` (:1509), `MapLayout.highlight_box` (:1991). Styles: `CalendarRow`
  (src/shortsmith/styles.py:171), optional `broll.calendar`, offered -> required.
  explainer v27 `broll.calendar` {max_per_60s 1, chars_max 12, lead_s 0.25, flip_s 0.4,
  hold_max_s 0.85, width_px 440, height_px 340, header_px 80, size_px 120, min_size_px 64,
  page #FFFFFF, ink #111111, header #E53935, header_ink #FFFFFF} (styles/explainer.md:153);
  vishva v17 the same with max 2 (styles/vishva.md:152); `motion.map.stamp_margin_px: 24`
  in the five map styles (fastfacts / footage v16, hitech v25).
- Grammar: `_calendars` (src/shortsmith/grammar.py:1509): offered, picture or map beat,
  never with a stamp (3.1: one landed event), from != to, chars_max, word inside the beat,
  `calendar_cap`; `at_s` from the word; a 3.1 change at its landing.
- Render: `calendar_spec` (src/shortsmith/render.py:1649): the stamp's spot, peel ends on
  the word (`land_s` = at_s, `flip_start_s` = at - flip_s, `appear_s` = that - lead_s,
  none before the beat), off a detected face (`calendar_clear_of` :1634).
- Map fold-in: `map_content` (:1538: the country's box - `infographics._paths_box`,
  src/shortsmith/infographics.py:1023, from the fill's own path points -, the circle, the
  tag, each marker pill and dot); `clear_spot` (:1574: the nearest spot in the stamp band,
  x and y, keeping the margin, else the corner covering the least content);
  `stamp_off_map` (:1605) / `calendar_off_map` (:1625); build_spec lays the map bare,
  moves the stamp / page, logs `... moved off the map's content (clear|corner) (108)`,
  then lays the map round them (:3235) so the tag and names still avoid the stamp.
  Run05 b07 (Saudi Arabia, Riyadh): the stamp moves above the country.
- Remotion: components/calendar.tsx (pop in, page peels about its binding with
  rotateX, lands flat on the new date), Short.tsx (stamp layer), types.ts, registry;
  Node test registry.test.mjs (108).
- Editor: `calendar` is a droppable layer. effect_map: calendar_flip,
  calendar_page_peel -> calendar. Prompt: "Calendar pages" (picture_v20.md:328);
  snapshots re-recorded. Bench: `--effects` adds 108_calendar_flip, 108_calendar_landed,
  108_map_stamp.
- Tests: tests/test_calendar_flip.py (18, incl. the Saudi Arabia stamp test, the emptiest
  corner, a real Remotion flip 1937 -> 1938 landing on the word), test_bench; every test
  file green in chunks, ruff, pyright, smoke T1-T13, npm typecheck + test green.
- Frames (scratchpad): 108_map_stamp.png (b07-style, stamp above Saudi Arabia),
  108_calendar_flip.png, 108_calendar_landed.png.
- Note: a 340 px page on a big country map rarely finds a free spot and goes to a corner;
  the fake plan carries no calendar, so the smokes draw none.
