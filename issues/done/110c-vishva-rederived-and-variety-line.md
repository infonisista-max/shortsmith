# 110c — vishva re-derived from the references, a variety line on every job, and where the rule lives

## Type

AFK. The third of three parts of the old 110 (split 1 Oct 2026).

## Parent PRD

`issues/prd.md`

## What to build

- **vishva.md re-derived:**
  - `wipe` goes into the transitions (`vishva.md:88` left it out, although it is built);
  - "full-screen stills are the base" (`:210`) and `clip_max_fraction: 0.15` (`:95`) are
    replaced by `clip_share_target: [0.20, 0.40]` (operator, 30 Sep 2026);
  - its numbers are checked against the reference frames and the facts references'
    moving-footage data (GAPS.md, 27-92 % moving), not taste. The Done note records what
    was checked.
- **A variety line in the job's inventory** (074's table): treatments used, clip share
  against the target, transitions used, repeats. Red rows are logged only; they are not a
  gate.
- **Where the rule lives** (the answer for the operator): `styles/README.md` names the
  prompt section, the style front matter + "creative editor" prose, the soft rules in
  `grammar.py`, and `reference/examples.py`.

## Acceptance criteria

- [x] vishva's front matter carries the range and `wipe`; `styles.load_all` green.
- [x] The variety line is present on the smoke job's inventory (test).
- [x] `styles/README.md` names every place the rule lives.
- [x] The full chunked suite and smoke are green.

## Blocked by

110b.

## Done note (1 Oct 2026)

- **vishva v18** (`styles/vishva.md`): `wipe` in `enter_transitions` (`:125`; its row was
  already in `transitions`) and in the whoosh triggers (`:260`, every moving enter + pop
  as in every style); `clip_share_target: [0.20, 0.40]` kept (`:136`) with the reference
  check in the comment beside it (`:132-135`). Prose: "full-screen stills are the base"
  replaced by "each line gets the picture it needs" (Recipe, `:302`); the number beat now
  takes a chart, calendar or new picture first and may carry on the previous asset
  (`:304`); reuse is for callbacks and payoffs, a number beat is never made to reuse
  (`:307`); "`wipe` is enabled here" (Transitions, `:311`).
- **Reference check (what was checked):** the frames under `work/reference/` were not
  used; the committed cards were (`docs/reference/inventory/*.json` `styles`, and the
  moving-footage column of `GAPS.md`). Vishva's own Tier B cards: FbaBcWgMIEY 0 %,
  ePTZVwipoAM 0 % (100 % stills), nBihHUlYOQk 19 % (8 % full-screen footage) - all
  under the low end 0.20: they are the stills-by-spec reels 110 names as the problem,
  so they do not contradict the operator's decision to raise it. The 60 s facts cards:
  M78CO3Ybr7U 22, bL3rUtUPYsc 27, cKxkAjYHXbk 35, VSJzviqMO7k 38, zXK42RMPKUY 38,
  S5j-2CWYYwM 45 % - five of six inside [0.20, 0.40], S5j above the top. No outright
  contradiction: the range is kept, unchanged. The approved old-engine shorts are 0 %
  clips (110b's note); the beat tables (`work/beat-tables.md`) were not re-read here.
  `wipe`: no vishva card registers a non-cut enter at 5 fps (110b), so the references
  neither show nor forbid it; it goes in on the operator's words (110: built, left out).
- **Variety line** (`src/shortsmith/reference/variety.py:37`, names `:29-32`): treatments
  used (tally, beside `broll.treatments`), clip share of the runtime against
  `clip_share_target` (red outside), transitions used (tally, beside
  `enter_transitions`; red under `non_cut_min_share`), repeats (showings past
  `reuse_max` via `grammar.reuse`, the same treatment back to back, enters past
  `enter_run_max`; red above 0). Written into `out/inventory.json` under `variety` after
  the card or the not-analysed reason (`reference/own.py:141`, `_add_variety` `:177`;
  `load` strips the key, `load_variety` `:196`); each red row is a `job.log` line
  `inventory: variety: ... (logged, never a gate)`; `OwnInventory.variety`
  (`contracts.py:2391`) in `meta.json`; its own table on the job page
  (`app.py:1479`, shown even when not analysed). Smoke checks it (`smoke.py:1568`).
- Fake planner: the wall's light flare now falls back to `wipe` before `spring`
  (`planner/fake.py:156`), so the vishva smoke draws every enabled enter (b08 springs).
- `styles/README.md:57`: "Where the creative-editor rule lives".
- Loops: ruff, pyright clean; all 94 test files green in foreground chunks after the last
  source edit; `python -m shortsmith.smoke` ok (T1-T13 pass). src/remotion untouched.
