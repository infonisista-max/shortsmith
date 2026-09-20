# 028 — Motion graphics on the map: pin_drop, route_arrow, object_path

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The three map animations from 9.2 on the 020 base: animated marker drops at real coordinates, a draw-on route arrow along the projected polyline, and an object (plane, ship, arrow) moving along the path. Each is a beat kind with its own motion so the one-motion-per-beat rule holds, and each may carry a landed event for a floor hit.

Covers PRD render (`pin_drop`, `route_arrow`, `object_path`). Decisions 9.2, 9.3, 4.1, 7.1.

## Acceptance criteria

- [ ] `pin_drop`: markers drop in sequence with a spring settle; label fly-in after the pin lands; timing from the beat length.
- [ ] `route_arrow`: the route draws on from start to end over the beat with an arrowhead; the map may `wipe` to the region on enter when the style allows it.
- [ ] `object_path`: the chosen object sprite moves along the route with heading following the path tangent.
- [ ] All three take their pixels from `MapLayout`; no coordinates in the render spec come from the planner.
- [ ] Registered; explainer `requires_components` gains them.
- [ ] Unit tests on timing curves and tangent heading; smoke renders the FakePlanner's three map-animation beats and gates pass.

## Blocked by

- Blocked by `issues/020-maps-geodata-gazetteer.md`
- Blocked by `issues/026-hook-cards-finale-stamp-lower-third.md`

## User stories addressed

- User story 23
- User story 24
