# 059 — Three recipe styles from the references: `footage`, `vishva`, `fastfacts`

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Operator, run03 verdict 27 Sep 2026: "every video comes out in exactly the same style";
directive: learn the styles from the references, "a mix of these styles can produce
many successful shorts". The reference inventory (036: `docs/reference/inventory/*.json`
and `GAPS.md`, 12 shorts, ESTIMATED) measured them. In the paired review of 28 Sep 2026
the operator picked three recipes. Each is a new shipped style spec in `styles/`, built
from those measured numbers. A fourth (the presenter full-frame over a picture) waits
on a background-removal decision and is not part of this ticket.

| style | references | what it looks like (targets, ESTIMATED) |
| --- | --- | --- |
| `footage` | Dhruv Rathee Shorts `S5j-2CWYYwM`, Dhruv `ATkSnL_CdLg`, Facts' Mine `VSJzviqMO7k`, `cKxkAjYHXbk` | A shot every ~2.2 s (refs 4.0–5.2 per 10 s). Full-screen moving clips (058) are the base: `clip_max_fraction` 0.75 (refs 49–82 %), median clip ~2 s. The presenter sits in the PIP over the clips; full-frame presenter at argument turns (≤ 0.25), entered with a `flash` (060) — the Dhruv move. Stamps or text pops on numbers about 1 per 10 s; a sticker at most every ~20 s; SFX about 1.2 per 10 s. |
| `vishva` | the operator's own Vishva Gyan shorts `FbaBcWgMIEY`, `ePTZVwipoAM`, `nBihHUlYOQk` (Tier B, proven on his audience) | A shot every ~2.6 s (refs 3.2–4.9 per 10 s). Full-screen stills (057) are the base, clips ≤ 0.15. Dense overlays, about 2.5 per 10 s (refs 1.5–5.7): text pops pinned on the picture (061), bubbles (063), stickers (062). Stacked panels — two pictures, top and bottom — about a quarter of the runtime (refs 18–39 %); if `split` draws only side by side, add the stacked option to it here. SFX about 1.3 per 10 s. |
| `fastfacts` | NeelFacts `Q2pquJ2FlzA`, FactTechz `zXK42RMPKUY` | A shot every ~1.2 s (refs 7.0–9.3 per 10 s; `beats.min_s` 0.5). Clips up to 0.7 of the runtime, full-screen stills otherwise. A fixed title strip at the top for the whole short (the topic in ≤ 5 words; `Q2pquJ2FlzA` and `VSJzviqMO7k` do it) — reuse the card or lower-third drawing if it fits. A text pop on every number. Asset bounds (`unique_assets_*_per_60s`) scaled to the pace; reuse still ≤ 2 (056). SFX about 1.2 per 10 s. |

In all three:

- Captions are explainer's, number for number (run03: "subtitles perfect").
- PIP geometry, the 055 opening, the finale, the bed at −14 dB (056) and the loudness
  targets are explainer's.
- `flash` is in `enter_transitions`; whooshes are allowed under 060's rule with
  `sound.whoosh: {max_per_60s: 6, min_gap_s: 3.0, max_len_s: 0.8, on: [flash, pop]}`
  (refs: whooshes in all 12, median about 3.5 per 60 s).
- `status: shipped`, `version: "1"`, the five prose sections written for the planner.
- The style README gains one table: each recipe, its reference ids and where each
  number came from, so the operator can trace every number.

Aliases (amends 1.1): `footage` — footage, documentary, dhruv, cinematic; `vishva` —
vishva, vishvagyan, vishva gyan, desi, history; `fastfacts` — fast facts, fastfacts,
facts, fact, quick. Explainer drops `fact`, `facts` and `dhruv` so those words reach the
new styles. The upload page offers the three because they are shipped.

## Acceptance criteria

- [ ] `styles.load_all` loads the three; each `requires_components` is present in the
      registry (`clip`, `flash`, `text_pop`, `sticker`, `bubble` and the rest).
- [ ] `python -m shortsmith.smoke --style footage`, `--style vishva` and
      `--style fastfacts` each pass T1–T13. Each run's `work/render_spec.json` shows its
      recipe: a flash and clip beats in footage; text pops, a bubble, a sticker and a
      stacked panel in vishva; a beat mean ≤ 1.5 s and the title strip in fastfacts.
      Smoke explainer and hitech pass unchanged.
- [ ] Resolver tests: "facts" → fastfacts, "dhruv" → footage, "vishva gyan" → vishva,
      "explainer" → explainer.
- [ ] `npm run typecheck`, `npm test`, ruff, pyright, every test file green in foreground
      chunks.
- [ ] Done note: the amendment lines (1.1 aliases, 3.1 beats for fastfacts, 4.1 kinds)
      for the operator to paste, and what to look at on run04: which style, overlays per
      60 s, flash count, whoosh count, clip share.

## Blocked by

- `issues/057-images-fill-the-frame.md`
- `issues/058-moving-footage-clips.md`
- `issues/060-flash-transition-whoosh-allowance.md`
- `issues/061-text-pop.md`
- `issues/062-stickers-fluent-emoji.md`
- `issues/063-speech-thought-bubbles.md`

## User stories addressed

- Operator, 27 Sep 2026 (run03): "all videos coming with exactly same style ... with
  learnings from urls, the system will have much broader styles to incorporate."
- Operator, 27 Sep 2026: the six facts references "can be taken as base for the system,
  system can try to replicate these styles and play with these styles".
