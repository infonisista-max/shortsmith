# 103 — More ways to show a picture: the red card becomes one choice of several

## Type

AFK (touches `src/remotion`)

## Parent PRD

`issues/prd.md`

## Why

`assets/__init__.py:350-360` `classify` turns every landscape or low-res image into the
same red-ringed tilted card (9 of 17 photos in run05). That is "the same image pop-ups
again and again".

## What to build (operator's picks, 30 Sep 2026)

- New treatments, each a registered component with its numbers in front matter:
  - **blurred full-bleed backdrop:** the image sharp in the middle over a blurred,
    enlarged copy of itself filling 9:16;
  - **face-aware crop-to-fill:** full screen, cropped around the face or subject (the
    existing face detector), with a slow move;
  - **polaroid / photo drop:** a white-bordered print that drops and settles with a soft
    shadow, its angle varied per use within a front-matter range;
  - **the red card** stays, capped per 60 s (front matter);
  - any other picture treatment the reference cards' `shows`/`motion` record, when an
    existing component can carry it (added to `effect_map`).
- `classify` no longer decides the look. It says what the image **allows** (fits full
  screen? has a face? resolution). The planner (110's standing rule) picks among the
  allowed treatments per image, and the renderer falls back to an allowed one if the pick
  does not fit.
- **The same treatment never runs back to back.** This is a soft grammar rule with
  keep_soft (094); the editor swaps in another allowed treatment.

## Acceptance criteria

- [x] Each treatment renders in a Remotion test and in the bench.
- [x] A low-res landscape image may take any of backdrop / polaroid / card; a face image
      may take crop-to-fill.
- [x] Grammar: two consecutive beats with the same treatment → a soft violation, and the
      editor's repair swaps it (test).
- [x] Style specs list the treatments in `requires_components`; `styles.load_all` green.

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026: "the same image pop-ups again and again"; "the LLM picks per image
like an editor and varies them, so the same treatment never runs back to back."

## Done (30 Sep 2026)

- Vocabulary: `PictureTreatment` = photo, crop_fill, backdrop, polaroid, card
  (src/shortsmith/contracts.py:252); the planner's pick is `Beat.treatment`
  (contracts.py:495, in the reply schema); `VisualSpec.treatment` gains the three and
  `CardSpec` carries the polaroid's `drop_px` / `drop_s` / `shadow_px`.
- `classify` no longer decides the look: it says the image fits full screen or not;
  `assets.allowed_treatments` (src/shortsmith/assets/__init__.py:377) lists what the image
  allows - `photo` when it fits, `crop_fill` when a face is found and it covers 1080x1920
  within `crop_fill.max_upscale`, backdrop / polaroid / card always (sized to its
  resolution). A beat with a `treatment` is sourced on size alone (`_planned`, :400).
- The renderer picks (`render.pick_treatment`, src/shortsmith/render.py:817): the
  planner's pick when allowed, not the previous beat's in `no_repeat_treatments` and (a
  card) under the cap; else the first of the style's `treatments` order that passes;
  never fails. A beat with no `treatment` uses the old classify answer as its pick, so
  run05's nine cards in a row now come out capped and varied (test). Wired in `_visuals`
  (render.py:1057) with the 3.3 detector's face per file (`face_in`, build_spec,
  render.py:2645); builders `backdrop_visual` :849, `polaroid_visual` :886 (tilt spread
  over the range by `polaroid_tilt` :879; the lower-third label on its thick bottom),
  `crop_fill_visual` :924 (the split pane's `pane_focus` framing); a number beat carrying
  a print on never drops it again (:966).
- Components: `backdrop`, `crop_fill`, `polaroid` (src/remotion/components/*.tsx,
  registry.json, registry.ts, drawn in Short.tsx's photo layer); the card's body is shared
  as `CardBody` (src/remotion/components/card.tsx:34). Node tests
  src/remotion/tests/registry.test.mjs:383, :397.
- Front matter (explainer 24, fastfacts / footage / vishva 14, hitech 23):
  `broll.treatments: [photo, crop_fill, backdrop, polaroid, card]` (also the fallback
  order), `no_repeat_treatments: [backdrop, polaroid, card]`, `card_max_per_60s: 3` (the
  approved references: NKB 2 archival cards in 60 s, Dyson 3 in 57.5 s); motion rows
  `backdrop` {scale 1.0->1.06, width_px 1080, max_upscale 2.0, blur_px 36, brightness
  0.45 - the card's cover numbers}, `crop_fill` {1.0->1.08, max_upscale 2.5, face_y 0.38},
  `polaroid` {width_px 760, border_px 20, bottom_px 84, max_upscale 1.5, tilt -6..6,
  drop_px 240, drop_s 0.3 (the wall's spring), shadow_px 36, blur_px 36, brightness 0.45}
  (styles/explainer.md:108). The three are in every one's `requires_components`;
  `styles._check_treatments` (src/shortsmith/styles.py:468) refuses a shipped spec that
  offers a treatment it does not require. docs/components.md has the three rows.
- Grammar soft rules (`grammar.treatments`, src/shortsmith/grammar.py:743): a repeat of a
  `no_repeat_treatments` one on consecutive beats, more card treatments than the cap, a
  treatment the style does not offer or on a non-still beat. Editor repair: one
  `treatment:<name>` swap per treatment that is neither the beat's nor a neighbour's
  (`_treatment_swaps`, src/shortsmith/editor/__init__.py:215; `repairs.set_treatment`,
  src/shortsmith/editor/repairs.py:277); `fallback_for` takes the first swap on a
  `treatment` problem (:246); the style's order is passed from the pipeline
  (src/shortsmith/pipeline.py:642).
- Prompt: picture_v20.md gains the "Picture treatments" section
  (src/shortsmith/planner/prompts/picture_v20.md:84) and the entity line points to it;
  snapshots re-recorded. The bigger creative-editor section is 110's.
- Reference cards: the v2 `shows` record full stills with zoom (crop_fill / photo),
  cards, grids (wall) and splits, all carried now; the only other picture look named is a
  "cutout", which no existing component carries, so effect_map.yaml is unchanged.
- Bench: `python -m shortsmith.bench --treatments OUT [--image PATH]`
  (src/shortsmith/bench.py:138) renders one 15-frame beat per treatment and saves
  `103_<treatment>.png`; run on run05's img_modi (face) and ref4 (870x614 landscape).
  Frames in the session scratchpad (not committed).
- Tests: tests/test_treatments.py (30), tests/test_bench.py; every test file green in
  chunks, smoke T1-T13 pass, npm typecheck and test green.
