# 020 — Maps: bundled geodata and gazetteer, geocoder with fake, projected map base with markers

## Type

HITL — needs new assets and packages: the Natural Earth vector data (countries, coastlines, major cities, ~25 MB, public domain) and a ~10k-place gazetteer bundled under `assets/geo/`, plus `d3-geo` (and `topojson-client` if TopoJSON is used) in the Node project for projection. The operator approves the downloads and packages; then this ticket becomes AFK.

## Parent PRD

`issues/prd.md`

## What to build

The first infographic kind composed in code, never generated as an image. The planner writes `map: {region | bbox, markers: [{name}], route?, object?}` and the `infographics` module resolves it: markers are placed by real coordinates from the bundled gazetteer with a Nominatim fallback cached per job, the region is projected and cropped, and the layout is handed to the Remotion `map` component, which draws the base from the bundled geodata with the style palette and static markers. Animated pins, routes and moving objects come in 028.

Covers PRD `infographics` (maps), render `map`. Decisions 9.2, 9.3, 12.1, 13.1.

## Acceptance criteria

- [ ] `assets/geo/` holds the Natural Earth layers and the gazetteer with a `LICENSE` note; both load with no network.
- [ ] `infographics.Geocoder` interface; `GazetteerGeocoder` looks names up locally, `NominatimGeocoder` is the fallback with per-job cache under `work/geo/`; `FakeGeocoder` holds a ten-place table; planner-supplied coordinates are ignored (test: a plan with wrong lat/lon still places the marker at the gazetteer's point).
- [ ] `infographics.resolve_map(recipe) -> MapLayout` with projection, crop to region or bbox with padding, marker pixel positions, route polyline pixels; projection maths unit-tested on known cities.
- [ ] Remotion `map` component draws land, coast and borders from the bundled data with the style palette and places markers with labels outside the safe area; registered in the registry.
- [ ] A geocoding miss on a marker is a validation error naming the place, never a guessed point.
- [ ] Smoke: FakePlanner's `map` beat renders a map of a region with two fake-geocoded markers; T1–T4, T9 pass.

## Blocked by

- Blocked by `issues/016-asset-step-ladder-rights.md`

## User stories addressed

- User story 23
- User story 60
