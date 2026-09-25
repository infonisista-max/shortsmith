# 047 — Gate command: the day-14 printout

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

`python -m shortsmith.gate` reads the `meta.json` of the five gate jobs (named by id or picked as the five most recent `delivered` jobs with a rating) and prints the three-of-five table, per-component status for every tier-1 component, the cost distribution of passing jobs with the proposed soft cap at p90 and a hard cap above it, the critic-versus-phone match count, and the reference library count per category, listing anything incomplete by name. Nothing is hidden and nothing is cut.

Covers PRD `gate`, `ledger` distribution. Decisions 14.1, 11.3, 9.2, 10.2, 10.3.

## Acceptance criteria

- [ ] Table: one row per job with `delivered`, T1–T13 result, phone rating, critic overall; pass line "≥ 6/10 on 3 of 5" evaluated and printed.
- [ ] Component status from the registry against the full tier-1 list, each `implemented` or `incomplete` with a one-line reason from a maintained `docs/components.md` table.
- [ ] Cost distribution from all `passed` jobs' ledgers: min, median, p90, max, proposed soft (p90) and hard caps; fewer than ten metered jobs prints "insufficient data (N of 10)".
- [ ] Critic-versus-phone match count from `data/calibration.json`; reference counts per category from the README files.
- [ ] Every incomplete item is listed by name at the end; exit code is 0 only when the table passes and no item is incomplete.
- [ ] Tests on synthetic `meta.json` sets: 3 of 5 passes, 2 of 5 fails, missing component listed.

## Blocked by

- Blocked by `issues/035-contact-sheet-summary-meta.md`

## User stories addressed

- User story 39
- User story 50
