# 083 — The next effects from GAPS.md, built from the v2 motion data

## Type

HITL — **parked until 079 (run05) is decided go.** The operator picks which effects.

## Parent PRD

`issues/prd.md`

## What to build

Operator, 25 Sep 2026: learn the references' effect and animation vocabulary. The grill
of 29 Sep 2026 agreed: the vocabulary is **recorded** now (073's per-effect `motion`
data), one effect (the article highlighter, 078) is **built** now, and the rest are built
here from real data.

Candidates in `docs/reference/inventory/GAPS.md`, grouped:

- **Map target circle and angled label:** `ePTZVwipoAM` 26 s, 48 s.
- **Banners:** a top or lower banner sliding in (`banner_slide_down`, `date_banner_slide`,
  `text_banner_pop`).
- **Props in the presenter's hands:** `glowing_sun_prop`, `prop_pop_in`,
  `3d_globe_overlay`. These need background removal or hand tracking (the 059 fourth
  recipe's open decision).
- **Cut-out reaction pops:** `reaction_cutout_pop`, `money_fan_and_crown`.
- **Kinetic counters and calendar flips:** `calendar_flip`, `calendar_page_peel`.
- **Particle and cash overlays:** `currency_shower`, `cash_cascade`,
  `brain_particles_overlay`.
- **Unregistered transitions:** `light_flare` / `light_burst`, `vertical_slits_zoom`,
  `wipe`.

## Acceptance criteria

- [x] After the v2 re-run and any 081 additions, re-run `reference gaps` and rank the
      groups by reference count.
- [x] The operator picks 1–3. Each becomes its own AFK ticket, built from the cards'
      `motion` numbers.

## Blocked by

- `issues/073-reference-card-v2.md`
- `issues/079-run05-learning-check.md`

## Done note (30 Sep 2026)

Unparked by the operator after run05 (6.5/10). Picked: all four groups plus the null fill:
**106** (nulls to existing components), **107** (banners + light flare), **108** (calendar
flip), **109** (cash/particle overlays). The map target circle is in **104**. Props in hands
and cut-out reaction pops stay open in GAPS.md (they need background removal).
