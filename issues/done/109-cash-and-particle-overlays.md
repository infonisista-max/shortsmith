# 109 — Cash and particle overlays (083 part 4)

## Type

AFK (touches `src/remotion`)

## Parent PRD

`issues/prd.md`

## What to build

`currency_shower`, `cash_cascade` and `brain_particles_overlay`, built from the cards'
`motion` data: a light overlay on a money line (oil wealth, budgets) or a thinking line.
- Drawn in code; no stock asset needed.
- Capped per 60 s in front matter.
- Never over a face or the captions.

## Acceptance criteria

- [x] Remotion tests + bench; typecheck green.
- [x] The grammar accepts it on the styles whose references use it; effect_map points the
      names at it.
- [x] Smoke green.

## Blocked by

106.

## User stories addressed

Operator, 30 Sep 2026: 083.

## Done note (1 Oct 2026)

- Evidence: QjwDTLPLJ6c `currency_shower` 3.8 s and `cash_cascade` (2 in 179 s);
  zXK42RMPKUY `brain_particles_overlay` 1.7 s (1 in 58 s). **Derived, no card number**:
  count, size, fall_s, fade, opacity, colours, min_height_px, gap_px.
- Styles: `ParticleKindRow` / `ParticlesRow` (src/shortsmith/styles.py:195, :209), optional
  `broll.particles`, offered -> the `particles` component required. explainer v28
  (styles/explainer.md:145) {max_per_60s 1, min_height_px 240, gap_px 24, kinds.cash
  {count 14, size_px 160, fall_s 1.6, hold_max_s 3.8, fade_s 0.3, opacity 0.95, colors
  #C9C3A6 #B7C29A #D6CFB2}}; fastfacts v17 (styles/fastfacts.md:143) kinds.brain {count 70,
  size_px 10, fall_s 2.0, hold_max_s 1.7, fade_s 0.3, opacity 0.85, colors #7FDBFF #FFFFFF}.
- Contracts: `ParticlesPlan` / `Beat.particles` (src/shortsmith/contracts.py:487, :553),
  `ParticlesSpec` / `BeatSpec.particles` (:1553, :2080).
- Grammar: `PARTICLE_KINDS`, `particles_cap`, `_particles` (src/shortsmith/grammar.py:1588,
  :1591, :1598): kind offered, picture beat, word inside the beat, the cap; `at_s` from the
  word; a 3.1 change at its start.
- Render: `particles_spec` (src/shortsmith/render.py:1699): the safe band above the PIP
  circle or the caption block, gap_px off; with a face in it the larger band above/below;
  under min_height_px it is dropped and logged (109). Wired into build_spec (:3298).
- Remotion: src/remotion/components/particles.tsx (cash notes fall, brain dots rise in two
  lobes and twinkle, deterministic hash, clipped to its box), drawn in
  src/remotion/Short.tsx:229 before the PIP; Node test in src/remotion/tests/registry.test.mjs.
- Editor: `particles` droppable layer (src/shortsmith/editor/repairs.py:43, :111).
- effect_map: currency_shower, cash_cascade, brain_particles_overlay -> particles
  (assets/reference/effect_map.yaml). Prompt: "Cash and particle overlays"
  (src/shortsmith/planner/prompts/picture_v20.md:337); snapshots re-recorded.
- Bench `--effects` 109_cash / 109_brain. Tests: tests/test_particles.py (12, incl. a real
  Remotion render), test_bench +1.
- Loops: ruff, pyright, full pytest in chunks (1481 + 388 + 121 + 138 + 303 + 13 + 7
  passed), `shortsmith.smoke` T1-T13 pass, `npm run typecheck`, `npm test` 39/39.
