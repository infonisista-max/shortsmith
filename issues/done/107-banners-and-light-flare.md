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

- [x] Remotion tests + bench; typecheck green.
- [x] The planner prompt's vocabulary (110's section) lists them; the grammar accepts them
      where the style allows.
- [x] Smoke green.

## Blocked by

106.

## User stories addressed

Operator, 30 Sep 2026: 083.

## Done note (30 Sep 2026)

- Evidence: the v2 cards give entrances only for effects (transitions carry no `motion`),
  so the numbers come from the effect entries and the v1 cards' durations (the v1 names
  live in `tests/fixtures/reference/inventory_v1/`). Banner: slide 0.3 s (M78CO3Ybr7U
  `date_stamp`, ePTZVwipoAM `indus_war_tag`), hold 2.0 s (longest ref, bL3rUtUPYsc
  `barabar_banner`), 5 words (longest ref banners), size 0.85-0.9 of the width -> the safe
  band. **Derived, not in the cards**: the bar height 104 / type 60->36 / top_y 262 (the
  059 title strip's, itself the Q2pquJ2FlzA header banner), gap_px 24 (the text pop's
  clearance), colours from the descriptions (M78 "black and red", ePTZ "yellow banner").
  Light flare: 0.3 s (all 13 QjwDTLPLJ6c flash_transition entries; v1 0.2-0.4 s), 4 a
  minute (13 in 176 s); **derived**: core `#FFF4D6` / glow `#FF9F1C` from the words
  "orange-white exposure burn", "warm yellow-white", and the sweep from_x 0.2 -> to_x 0.8
  at y 0.3 (upper third, above the circle).
- `vertical_slits_zoom` not built: the cards give only a 0.2 s duration (v2 names it
  `shutter_slice`, unregistered, no slit count or motion); it stays mapped to `zoom`.
- Contracts: `Banner` / `Beat.banner` (src/shortsmith/contracts.py:460, 521),
  `BannerSpec` (:1470), `LightFlareNumbers` and the optional `Transitions.light_flare`
  (:2085, :2110); `Transition` gains `light_flare`.
- Styles: `styles.BannerRow` (src/shortsmith/styles.py:147), optional `broll.banner`;
  `_check_offered` (:553) refuses an enabled flare without its row and a shipped style
  that offers a banner / flare without requiring it. explainer v26: `broll.banner`
  {max_per_60s 1, words_max 5, slide_s 0.3, hold_max_s 2.0, top_y 262, height_px 104,
  gap_px 24, size_px 60, min_size_px 36, fill #111111, ink #FFFFFF, bar #E53935, bar_px 10}
  (styles/explainer.md:147), `transitions.light_flare` {duration_s 0.3, core #FFF4D6,
  glow #FF9F1C, from_x 0.2, to_x 0.8, y 0.3, max_per_60s 4} (:161), light_flare in
  `enter_transitions` and `sound.whoosh.on`. vishva v16: `broll.banner` with max 2, fill
  #FFD60A, ink #111111 (styles/vishva.md:146). Other styles offer neither (their refs
  do not flare; the footage/fastfacts banners are text pops in v2).
- Grammar: `_banners` (src/shortsmith/grammar.py:1428: style must offer it, picture beat,
  1-words_max words, word inside the beat, `banner_cap`, `at_s` written from the word);
  a banner is a 3.1 change at its landing; `light_flare_cap` (:1585) and never two in a
  row in `_transitions`.
- Render: `banner_spec` (src/shortsmith/render.py:2485): safe band x 60-940, top at top_y,
  low one gap_px above the circle (pip) or the caption block, type fitted, too wide fails
  naming the beat; pops / bubbles / stickers keep off it (:2834).
- Remotion: components/banner.tsx (slides in clipped to its box), components/light_flare.tsx
  (radial burst screened over both pictures, peak on the cut), Short.tsx, transitions.tsx,
  types.ts, registry.json/ts; Node tests registry.test.mjs (107 x2).
- Editor: `banner` is a droppable layer (repairs.py, editor/__init__.py, change.py).
- effect_map: banner_slide_down, date_banner_slide, text_banner_pop, text_banner -> banner;
  light_flare, light_burst -> light_flare. Analyser transitions set gains light_flare.
- Prompt: picture_v20.md light_flare line (:87) and "Banners" (:321); snapshots re-recorded.
- Fake plan: b10 (wall) enters with light_flare where enabled (explainer), else cut, so the
  smoke's "every enabled transition" check covers it; recorded CLI/API replies updated.
- Bench: `python -m shortsmith.bench --effects OUT` (src/shortsmith/bench.py:198, 229).
  Frames (scratchpad, not committed): 107_banner_top.png, 107_banner_bottom.png,
  107_light_flare.png.
- Tests: tests/test_banners_flare.py (21, incl. a real Remotion render), test_bench; every
  test file green in chunks, ruff, pyright, smoke T1-T13, npm typecheck + test green.
- Not done: banners do not avoid a face on the picture (the refs lay them over it); a
  stamp moved up off a face could meet a top banner.
