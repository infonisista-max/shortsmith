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

- [ ] Each treatment renders in a Remotion test and in the bench.
- [ ] A low-res landscape image may take any of backdrop / polaroid / card; a face image
      may take crop-to-fill.
- [ ] Grammar: two consecutive beats with the same treatment → a soft violation, and the
      editor's repair swaps it (test).
- [ ] Style specs list the treatments in `requires_components`; `styles.load_all` green.

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026: "the same image pop-ups again and again"; "the LLM picks per image
like an editor and varies them, so the same treatment never runs back to back."
