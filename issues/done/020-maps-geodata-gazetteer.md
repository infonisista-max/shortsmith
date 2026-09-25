# 020 — Maps: bundled geodata and gazetteer, geocoder with fake, projected map base with markers

## Type

HITL — needs new assets and packages: the Natural Earth vector data (countries, coastlines, major cities, ~25 MB, public domain) and a ~10k-place gazetteer bundled under `assets/geo/`, plus `d3-geo` (and `topojson-client` if TopoJSON is used) in the Node project for projection. The operator approves the downloads and packages; then this ticket becomes AFK.

## Parent PRD

`issues/prd.md`

## What to build

The first infographic kind composed in code, never generated as an image. The planner writes `map: {region | bbox, markers: [{name}], route?, object?}` and the `infographics` module resolves it: markers are placed by real coordinates from the bundled gazetteer with a Nominatim fallback cached per job, the region is projected and cropped, and the layout is handed to the Remotion `map` component, which draws the base from the bundled geodata with the style palette and static markers. Animated pins, routes and moving objects come in 028.

Covers PRD `infographics` (maps), render `map`. Decisions 9.2, 9.3, 12.1, 13.1.

## Acceptance criteria

- [x] `assets/geo/` holds the Natural Earth layers and the gazetteer with a `LICENSE` note; both load with no network.
- [x] `infographics.Geocoder` interface; `GazetteerGeocoder` looks names up locally, `NominatimGeocoder` is the fallback with per-job cache under `work/geo/`; `FakeGeocoder` holds a ten-place table; planner-supplied coordinates are ignored (test: a plan with wrong lat/lon still places the marker at the gazetteer's point).
- [x] `infographics.resolve_map(recipe) -> MapLayout` with projection, crop to region or bbox with padding, marker pixel positions, route polyline pixels; projection maths unit-tested on known cities.
- [x] Remotion `map` component draws land, coast and borders from the bundled data with the style palette and places markers with labels outside the safe area; registered in the registry.
- [x] A geocoding miss on a marker is a validation error naming the place, never a guessed point.
- [x] Smoke: FakePlanner's `map` beat renders a map of a region with two fake-geocoded markers; T1–T4, T9 pass.

## Blocked by

- Nothing; 016 is done.

## User stories addressed

- User story 23
- User story 60

## Done note (ceremony 2026-09-25/26)

Operator decisions at the ceremony, all honoured:

1. **Projection and clipping in Python, no `d3-geo`, no new npm package.** `geo.Mercator` (Web-Mercator maths, `fit` to a bbox in a pixel box), `clip_ring` (Sutherland–Hodgman) and `clip_line` (Liang–Barsky) cut the projected geometry to the frame, and `svg_path` writes it to a tenth of a pixel with sub-pixel steps dropped. The `map` component draws path strings; it never sees a coordinate. One projection serves the base and the markers, and `MapLayout` carries its numbers (`scale`, the centre) so 028 animates on the same maths.
2. **1:50m layers, gzipped and committed** under `assets/geo/` with `LICENSE` and `README.md` naming Natural Earth, public domain, version **5.2.0-pre**. Real sizes from the build: countries 242 features 3.08 MB raw → 0.83 MB; coastline 1,428 features 1.64 MB → 0.51 MB; land boundaries 390 features 0.76 MB → 0.18 MB; `gazetteer.json` 1.18 MB. Folder total 2.7 MB.
3. **Gazetteer from Natural Earth only**: 7,912 places = 242 countries + 34 regions (continents, UN subregions, World Bank regions, World) + 294 admin-1 states (the rider: Russia, USA, India's 36, Indonesia, China, Brazil, Canada, Australia, South Africa) + 7,342 populated places, with English, local and Hindi aliases and ISO codes. Built by `python -m shortsmith.geo_build work\geo_raw` (the README has the download commands).
4. **Nominatim fallback off by default** (`GEOCODER_FALLBACK=none`); enabled, it sends `User-Agent: shortsmith/0.1 (self-hosted YouTube Shorts editor; single operator)`, waits a second between requests, caches every hit and miss in `<job>/work/geo/nominatim.json`, and a service failure is an error naming the place.

Design points a later session should know:

- A shared name resolves area first (country > region > state > city), then by population: `region: "Delhi"` gets the state's bbox, a marker "Delhi" its label point; "Victoria" is the Canadian city. Country bboxes use only polygons at least 5 % of the largest, so France is the mainland. Russia's bbox still spans the antimeridian (its polygons do); a Russia-wide map is wrong until a wrap rule exists.
- The crop is the region's bbox widened to hold every marker and route point, padded by `broll.motion.map.padding`, fitted into the band (x 60–940, y 330–`card_max_bottom_y`). A city as region shows `CITY_SPAN_DEG` = 3° across.
- Marker labels sit right of the dot and flip left near the right rail; a label the safe area cannot hold fails the build like a diagram label (9.3).
- A `map` beat is in `assets.NOT_SOURCED`: no picture, no manifest row, no rights row; its rights are the bundled LICENSE. The fake plan's hook cards therefore point at `a8` (the split beat's searched asset) instead of the old map asset `a4` (the chart's `a5` is a number-beat reuse alias, which collapses the hook to one card).
- Grammar (`_maps`, `_overlays`): region or bbox required, bbox is west < east within ±180 and south < north within ±85, 1–`markers_max` named markers, a route is ≥ 2 names; `pin_drop` / `route_arrow` / `object_path` only on a map, the latter two need a route, `object_path` needs `object`.
- Planner prompt went to **v5** (map section in the picture file; the sound file is a copy of v4). Snapshots recorded; the CLI and API planner fixtures regenerated from `FakePlanner`.
- `RemotionRenderer(geocoder=...)`: the app should pass `geo.from_settings(settings)` (not wired in `app.py` this session; the default is the bundled gazetteer, which is what `GEOCODER_FALLBACK=none` means anyway). Wire it when the fallback is first enabled.
- Render-spec size for the India crop: 333 paths, ~226 KB of path text. A continent crop is larger; a `World` map is the worst case and untested for size.

Operator to-do after this commit:

- Paste into `.env.example` (052 pattern, bare optional keys):
  ```
  # 020: map markers come from the bundled gazetteer; `nominatim` adds the network
  # fallback (one request a second, cached per job under work/geo/). Free, unmetered.
  GEOCODER_FALLBACK=none
  NOMINATIM_URL=https://nominatim.openstreetmap.org
  ```
- Delete `work\geo_raw\` (19 MB populated-places file and the other raw downloads are build input only; `work/` is git-ignored so nothing was committed).
- Phone verdict on the map look (`SHORTSMITH_SMOKE_KEEP=1` smoke, beat b05 at 2.0–2.5 s): the land/coast/border colours are style numbers in `broll.motion.map`.

Verified: ruff, pyright, pytest (1,219 pass), `python -m shortsmith.smoke` (47.6 s, T1–T13 pass, `out/qa.json` read), `npm run typecheck`, `npm test` (14 pass). The map frame was read off the kept render: land, coast and borders drawn, Delhi north-east of Mumbai on the west coast, labels inside the safe band.

Next: `028-pin-drop-route-arrow-object-path` (AFK) takes `MapLayout.markers[].x/y`, `route` and `object`; `030` rejoins `map` to its registry list (already in `requires_components` here).
