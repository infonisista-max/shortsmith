# 082 — The operator's own 8+ shorts, and NKB v4 and Dyson v1, as worked examples

## Type

HITL — **parked until 079 (run05) is decided go.** Becomes AFK once unparked.

## Parent PRD

`issues/prd.md`

## What to build

Operator (grill, 29 Sep 2026): "my own shorts that I rate 8/10 or higher (and the NKB v4
and Dyson v1 I approved) can join as worked examples, so the system also learns my own
style."

- **Promoting a job.** A job rated ≥ 8 shows a button, "use as a worked example".
  - It copies the job's `out/inventory.json` (074, already a v2 card) to
    `docs/reference/inventory/own-<job_id>.json` with `tier: own`, the job's style and
    topic.
  - Nothing is promoted automatically, and a job without a v2 inventory can't be
    promoted.
- **The two approved shorts.** NKB v4 and Dyson v1 are local files under
  `work/reference/`. They go through 074's file path once, as `tier: anchor` cards.
- **Selection (077)** ranks `own` and `anchor` with Tier B in the tiebreak (the
  operator's own shorts first).

## Acceptance criteria

- [ ] Written when unparked.

## Blocked by

- `issues/074-self-inventory-on-every-job.md`
- `issues/077-worked-examples-for-the-planner.md`
- `issues/079-run05-learning-check.md`
