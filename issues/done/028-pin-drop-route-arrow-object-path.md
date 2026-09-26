# 028 — Motion graphics on the map: pin_drop, route_arrow, object_path

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The three map animations from 9.2 on the 020 base: animated marker drops at real coordinates, a draw-on route arrow along the projected polyline, and an object (plane, ship, arrow) moving along the path. Each is a beat kind with its own motion so the one-motion-per-beat rule holds, and each may carry a landed event for a floor hit.

Covers PRD render (`pin_drop`, `route_arrow`, `object_path`). Decisions 9.2, 9.3, 4.1, 7.1.

## Acceptance criteria

- [x] `pin_drop`: markers drop in sequence with a spring settle; label fly-in after the pin lands; timing from the beat length.
- [x] `route_arrow`: the route draws on from start to end over the beat with an arrowhead; the map may `wipe` to the region on enter when the style allows it.
- [x] `object_path`: the chosen object sprite moves along the route with heading following the path tangent.
- [x] All three take their pixels from `MapLayout`; no coordinates in the render spec come from the planner.
- [x] Registered; explainer `requires_components` gains them.
- [x] Unit tests on timing curves and tangent heading; smoke renders the FakePlanner's three map-animation beats and gates pass.

## Done note (2026-09-26)

Design, on the 020 base and the overlay shape the contracts and grammar already had
(the three animations are `overlays` on the one `map` beat, whose own motion is
`travel`; the fake plan's b05 carries all three):

- **Timing is one rule in Python** (`infographics.map_timeline`): the present motions
  share the first `MOTIONS_IN_FRACTION` (0.8) of the beat in order - pins drop (a
  `PIN_STAGGER_MAX_S` 0.2 s stagger, `PIN_DROP_MAX_S` 0.3 s fall and settle, a
  `LABEL_POP_MAX_S` 0.2 s label pop after the landing), the route draws on
  (`ROUTE_DRAW_MAX_S` 0.8 s), the object travels (`OBJECT_TRAVEL_MAX_S` 1.5 s). A long
  beat keeps the ceilings; a short one scales every phase by the one factor that fits
  the window, so the order and proportions hold at any length. An absent motion is 0 s
  and the rest close up. `MapLayout.landed_s` is when the last one has landed. On the
  0.5 s fixture beat the factor is 0.133: pins 0.09 s, route 0.11 s, plane 0.2 s.
- **Tangent heading in Python** (`infographics.route_segments`): the projected route as
  legs with `t0`/`t1` fractions of the length and `heading_deg` in screen degrees
  (atan2 with y down: 0 east, 90 south). Zero-length legs are dropped. The TS
  `pointAlong` only lerps inside a leg; the arrowhead and the sprite turn by the leg's
  heading. `route_path` and `route_length_px` are written in Python so the SVG dash
  draw-on needs no DOM measurement.
- **Every pixel is the layout's**: the resolver takes the beat's `overlays` and its
  length (`render.map_layout` passes both); the plan names places only. The resolver
  refuses `route_arrow` / `object_path` without a route and `object_path` without an
  object (the grammar already does; the resolver is safe on its own).
- **Components**: `map.tsx` now exports `Marker` and draws the markers static only when
  the beat has no `pin_drop`; `pin_drop.tsx` drops the same `Marker` with a Remotion
  spring stretched to `pin_drop_s`, a splash ring and the label pop; `route_arrow.tsx`
  is the dash draw-on with a polygon arrowhead at the tip; `object_path.tsx` draws the
  plane / ship / arrow as inline SVG silhouettes (no picture sourced), mirrored across
  its axis when heading west so a ship's cabin stays up. Layer order in `Short.tsx`:
  base, route, pins, object.
- **The `wipe` criterion** needs nothing new: the map beat's `enter` already goes
  through the 030 transition dispatcher, which refuses a name the style does not enable
  (explainer has no `wipe`; hitech does, and its smoke run uses it on b04).
- **Landed event**: a map beat may still carry the beat-level `event` (stamp or
  lower-third) and gets its floor hit through the existing path at the beat's start.
  Not done: moving that hit to `landed_s` (the moment the plane arrives), which would
  also need a delayed stamp. Follow-up if the operator wants the hit on the arrival.

Verified: ruff, pyright, pytest in foreground chunks (all files), `npm run typecheck`,
`npm test` (21), `python -m shortsmith.smoke` (explainer, 50.2 s, T1-T13 pass,
`out/qa.json` read) and `--style hitech` (46.9 s, T1-T13 pass). Frames read off the kept
explainer render at 2.15 / 2.28 / 2.40 s: both pins landed with labels, the route drawn
with the arrowhead at Mumbai, the plane mid-route heading south-west, then arrived.
`docs/components.md` flips the three rows to implemented (b05 under both styles); the
gate's component section is now all-implemented and its tests say so.

Operator to-do: phone verdict on the map motion (`SHORTSMITH_SMOKE_KEEP=1` smoke, beat
b05 at 2.0-2.5 s). The sizes are engine constants in `infographics` (`PIN_DROP_PX`,
`ROUTE_PX`, `ARROW_PX`, `OBJECT_PX`); the timing ceilings likewise. If the phone says the
0.5 s fixture beat is too busy, that is the fixture's beat length, not the rule: a real
map beat is 2-4 s.

## Blocked by

- Blocked by `issues/020-maps-geodata-gazetteer.md`
- Note (board audit 2026-09-25): this ticket is AFK-typed but starts only after the HITL 020 maps work lands, since every animation takes its pixels from 020's `MapLayout`. 026 is done.

## User stories addressed

- User story 23
- User story 24
