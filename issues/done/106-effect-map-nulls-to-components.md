# 106 — The GAPS names get their closest existing component (083 part 1)

## Type

AFK (data edit)

## Parent PRD

`issues/prd.md`

## What to build

`assets/reference/effect_map.yaml:79-100` has 19 GAPS names as `null`, so the worked
examples drop them. Map the obvious ones (operator pick, 30 Sep 2026):

| GAPS name | Component |
| --- | --- |
| number_badge_pop, numbered_tag | stamp |
| tag_pangea, tag_supercontinent, text_badge_pop, stacked_labels | text_pop |
| text_banner | lower_third (→ banner once 107 lands) |
| persistent_header_banner | title_strip |
| label_slide | label_flyin |
| countdown_number_one / _two | counter |
| red_circle_india | map target circle (104), else pin_drop |
| cartoon_scientist | sticker |

The names that 107-109 build get pointed at their new components when those land.
Anything still without a fit stays `null` and stays listed in GAPS.md.

## Acceptance criteria

- [x] effect_map loads, and the worked examples (077) now show these effects.
- [x] Tests that read effect_map are updated; no test lists the old nulls.

## Done note

- `assets/reference/effect_map.yaml:76-101`: the 13 operator picks mapped (stamp,
  text_pop, lower_third, title_strip, label_flyin, counter, pin_drop, sticker - all
  registered). `text_banner` and `red_circle_india` carry a comment to repoint them when
  107 (banner) and 104 (map target circle) land. Still null, and still listed in
  `docs/reference/inventory/GAPS.md` (unchanged: it lists what the renderer cannot draw):
  alternate_logo_reveal, bloodstain_splatter, brand_network_radial_diagram,
  negative_temperature_gauge, shutter_slice, spellcheck_squiggly_underline,
  sun_energy_orb, volkswagen_central_reveal, magical_horse_entry.
- Tests: `tests/test_worked_examples.py:170` (`GAPS_PICKS`, the map holds every pick)
  and `:188` (the worked examples built from the live cards now show
  `<component> (closest to <name>)` for them). No test listed the old nulls.
- 107-109's names are not mapped here (their components do not exist yet).

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026: "I lean to including 083."
