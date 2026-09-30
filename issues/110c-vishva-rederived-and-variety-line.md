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

- [ ] vishva's front matter carries the range and `wipe`; `styles.load_all` green.
- [ ] The variety line is present on the smoke job's inventory (test).
- [ ] `styles/README.md` names every place the rule lives.
- [ ] The full chunked suite and smoke are green.

## Blocked by

110b.
