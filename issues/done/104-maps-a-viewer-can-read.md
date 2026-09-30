# 104 — Maps a viewer can read: the named country filled and named, a minimum span, the target circle

## Type

AFK (touches `src/remotion`)

## Parent PRD

`issues/prd.md`

## Why

Run05 b08/b09 (0:13-0:16):
- The editor's b09 repair framed on the markers only (bbox about 3°x5°), so Riyadh sat on
  empty blue. `infographics.py:926-936` has no minimum span.
- `map.tsx:112-165` draws land, borders, coast and one pill per marker: no country names,
  no fill for the named country, no region label.
- b07 drew a lone Riyadh dot, with the stamp over the country.
- Land `#2F5597` is close to the background `#1F3B73`.
- The travelling glyph sits on the endpoint dot.

## What to build

- **Minimum span** in degrees (`map.min_span_deg`, front matter) for every map, the
  editor's repair included: the frame widens around the markers to at least that.
- **The named country or region** gets a highlighted fill (front-matter colour) and a
  name label; neighbouring countries in view get small name labels (collision rules from
  072).
- **Target circle + angled label** (083, `ePTZVwipoAM` 26 s, 48 s): a circle drawn round
  the named place with an angled label, numbers from the card's `motion` data.
- **A dot is never unlabelled:** a marker with no name is dropped, not drawn.
- The travelling object is drawn beside the endpoint dot, never over it.
- **Land/sea contrast:** the land colour is re-picked so land and sea can be told apart on
  a phone, checked against the reference map frames.
- Country names come from the local geo data (`geo.py`; no network).

## Acceptance criteria

- [x] A 3°x5° repair bbox renders at the minimum span (test).
- [x] A map with `region: Saudi Arabia` fills and names Saudi Arabia; neighbours are named.
- [x] No unnamed marker in any render spec (test).
- [x] Remotion tests + a bench frame; typecheck green; smoke green.

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026, finding 1: "framed so tight on Kuwait-Riyadh that the place can't
be read ... no country names or borders, a lone unlabeled dot at 0:13."

## Done (30 Sep 2026)

- Minimum span: `infographics._widened` (src/shortsmith/infographics.py:696) widens every
  crop, the editor's bbox repair included, to `map.min_span_deg` (12) about its middle;
  the old 1-degree `MIN_SPAN_DEG` constant is gone. Run05 b09's 3 x 5 box now shows Iraq,
  Kuwait, Saudi Arabia, the Gulf, Bahrain and Qatar.
- Named country: `resolve_map` fills the region's land rings (`geo.BasePaths.land_by_name`,
  src/shortsmith/geo.py:604) in `map.highlight`; `_target` (infographics.py:855) draws the
  circle round the region's point (`circle_size` 0.6 of the band, drawn in
  `circle_draw_s` 0.3 s - ePTZVwipoAM `red_circle_india`) and its tag at `tag_tilt_deg`
  -8, sliding in over `tag_slide_s` 0.3 s (`indus_war_tag`), on the circle's top rim,
  else bottom, else middle, clear of the markers and the beat's stamp (render passes it:
  src/shortsmith/render.py:2092, 2428). No room: the country is named flat instead.
- Neighbours: `_country_names` (infographics.py:893) names up to `names_max` 6 countries
  in view at `name_font_px` 30, most populous first, at the bundled gazetteer's label
  point (`geo.country_points`, geo.py:161; no network), stepped by 072's
  `label_step_px`, dropped when they would cover a marker, the tag, the stamp or another
  name. A country that is a marker (Kuwait) is not named twice.
- No unnamed dot: `map_recipe` and `resolve_map` drop a marker with a blank name
  (infographics.py:675, 1029).
- The object stops beside the endpoint dot: `object_end_t` (infographics.py:1087,
  contracts.py:1837), read by src/remotion/components/object_path.tsx:38.
- Land/sea: land re-picked `#2F5597` -> `#E3D9C0` (explainer, fastfacts, footage, vishva;
  contrast >= 7 against both sea stops), hitech `#0F2A44` -> `#3E6E96`; the highlight is
  teal `#1F9E89` (hitech lime `#A3E635`) so the yellow marker dot stays visible on it.
  Tested by contrast ratio (tests/test_map_readable.py). The ePTZVwipoAM frames are not in
  `work/reference/` (no network here), so the colours were checked against run05's
  frames and the card numbers only - Shubham's phone verdict is still the judge.
- Contracts: `MapNameLayout`, `MapTargetLayout` (contracts.py:1727, 1740); TS types and
  `CountryNames` / `TargetCircle` in src/remotion/components/map.tsx:117, 147; the fill
  under the borders at map.tsx:230; older specs without the fields still render.
- Style keys (all five map styles; versions explainer 22, hitech 21, recipes 12):
  `min_span_deg, highlight, names_max, name_font_px, name_color, circle_color, circle_px,
  circle_size, circle_draw_s, tag_font_px, tag_tilt_deg, tag_slide_s, tag_fill, tag_ink`.
- `red_circle_india` and `map_target_circle` repointed to `map`
  (assets/reference/effect_map.yaml:101, 45).
- Tests: tests/test_map_readable.py (11), src/remotion/tests/registry.test.mjs:347.
  Stills (not committed): run05 b07 / b09 before and after in the session scratchpad.
- Not done here: the stamp itself still lands over the country on b07 (the tag and names
  now avoid it); moving stamps off a map is a separate call.
