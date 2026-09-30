# 107 — Banners and the light-flare transition (083 part 2)

## Type

AFK (touches `src/remotion`)

## Parent PRD

`issues/prd.md`

## What to build

Built from the v2 cards' `motion` numbers (`docs/reference/inventory/`):
- **banner:** a top or lower banner sliding in (`banner_slide_down`, `date_banner_slide`,
  `text_banner_pop`), carrying words from the recording, safe-area aware.
- **light_flare** transition (`light_flare` / `light_burst`), plus `vertical_slits_zoom`
  if the cards give its numbers.
- Each is registered in `registry.json`, offered in the styles whose references use it,
  and has its `effect_map` entries pointed at it.

## Acceptance criteria

- [ ] Remotion tests + bench; typecheck green.
- [ ] The planner prompt's vocabulary (110's section) lists them; the grammar accepts them
      where the style allows.
- [ ] Smoke green.

## Blocked by

106.

## User stories addressed

Operator, 30 Sep 2026: 083.
