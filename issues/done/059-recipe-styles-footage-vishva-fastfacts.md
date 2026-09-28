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

- [x] `styles.load_all` loads the three; each `requires_components` is present in the
      registry (`clip`, `flash`, `text_pop`, `sticker`, `bubble` and the rest).
- [x] `python -m shortsmith.smoke --style footage`, `--style vishva` and
      `--style fastfacts` each pass T1–T13. Each run's `work/render_spec.json` shows its
      recipe: a flash and clip beats in footage; text pops, a bubble, a sticker and a
      stacked panel in vishva; a beat mean ≤ 1.5 s and the title strip in fastfacts.
      Smoke explainer and hitech pass unchanged.
- [x] Resolver tests: "facts" → fastfacts, "dhruv" → footage, "vishva gyan" → vishva,
      "explainer" → explainer.
- [x] `npm run typecheck`, `npm test`, ruff, pyright, every test file green in foreground
      chunks.
- [x] Done note: the amendment lines (1.1 aliases, 3.1 beats for fastfacts, 4.1 kinds)
      for the operator to paste, and what to look at on run04: which style, overlays per
      60 s, flash count, whoosh count, clip share.

## Done (28 Sep 2026)

What shipped: `styles/footage.md`, `styles/vishva.md`, `styles/fastfacts.md` (status
shipped, version "1"), built from the explainer's front matter with the recipe numbers
from the inventory; `styles/README.md` gains the recipe trace table (each number, its
reference ids and the inventory field it came from). Captions, PIP, the 055 opening,
finale, cut and the bed/loudness numbers are the explainer's (a test pins it). Every
recipe has `flash` enabled (cap 5) and `sound.whoosh {6, 3.0, 0.8, [flash, pop]}`.

Two things the renderer could not do, added here:
- `split` stacked: `broll.motion.split.layout: stacked` (vishva; absent = `side`). Top
  picture, the title band between ("Delhi versus Mumbai"), bottom picture, each the
  card's full width. The card runs from under the top zone (badge overhang included)
  down to `card_max_bottom_y`, so the lower picture sits under the PIP circle like a
  full-screen still (above the circle each picture would have been a 4:1 letterbox).
  `SplitSpec.title_top` carries the band's place; split.tsx reads it.
- Title strip: optional `broll.title_strip` row (fastfacts: 5 words, y 262-366, Poppins in
  the caption weight, ink #111 on #FFD60A, 0.3 s slide), the plan's new `title_strip`
  field (grammar 4.1: 1-`words_max` words under a strip style, empty elsewhere), a new
  registry component `title_strip` drawn from frame 0 to the finale's first frame; text
  pops, bubbles and stickers are placed off it; T12 judges its box.

Other decisions:
- Resolver: multi-word aliases ("vishva gyan", "fast facts") count as phrases.
- Prompt v14: the picture file says when to write `title_strip`; the schema carries it;
  the sound file is v13's unchanged. Snapshots recorded.
- Fake planner: b03 already flashes; under a style allowing whooshes its whoosh is b03's
  one cue (`cues_per_beat_max` 1), so the pop's tick gives way there. Under a strip
  style it writes "Twelve words of nothing". Explainer plan unchanged.
- Smoke: `--style` accepts a shipped recipe (proves the form resolves the name to
  itself); a recipe's own overlays are judged under the fixture counts
  (`smoke.judged_specs`); `check_recipe` checks the flash + whoosh on b03, the stacked
  split, the strip until the finale.
- Fixture numbers kept: overlay caps per 60 s round to fewer than the fake's pair in
  6 s, so the smoke raises them the way `--bubbles` does; the grammar is untouched.

Known and left for run04's eye: in fastfacts the strip (y 262-366) covers the top edge
of a card or a side-by-side split, whose tops sit near y 235-280. No placement rule moves
cards under the strip yet.

Amendment lines for `docs/grill-decisions.md` (for the operator to paste):
- 1.1 (as amended by 059): aliases `footage` - footage, documentary, dhruv, cinematic;
  `vishva` - vishva, vishvagyan, "vishva gyan", desi, history; `fastfacts` - "fast
  facts", fastfacts, facts, fact, quick. The explainer drops fact, facts and dhruv. A
  multi-word alias counts as a phrase.
- 3.1 (as amended by 059): fastfacts beats `min_s` 0.5, `max_s` 3.0, set pieces 4.0, mean
  0.9-1.5 (target 1.2), density gap 1.0 s; footage target 2.2 (1.8-2.8, max 5.0); vishva
  target 2.6 (2.1-3.2).
- 4.1 (as amended by 059): `split` may draw `stacked` (two pictures top and bottom, the
  title band between) where the style's `motion.split.layout` says so; a style with a
  `broll.title_strip` row draws the plan's `title_strip` (the topic in at most
  `words_max` words) at the top of the frame until the finale.

What to look at on run04 (per short: the style, then read off `plan.validated.json` and
`render_spec.json`):
- Which style the style line resolved to (job.json `style`).
- Overlays per 60 s: text pops + bubbles + stickers (vishva aims ~15, footage ~6-9,
  fastfacts one pop per number).
- Flash count (cap 5 a minute) and whoosh count (cap 6, 3 s apart, only on a flash or a
  pop-in) - does the Dhruv flash-back-to-presenter read on the phone?
- Clip share of the runtime (footage up to 0.75, fastfacts 0.7, vishva 0.15) and how
  often clip beats fell to the still ladder (job.log "no usable clip").
- vishva: the stacked split with the circle over the lower picture; fastfacts: the strip
  over cards and splits.

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
