# 085 — Style numbers drafted by code from the reference cards

## Type

HITL — **parked until new reference URLs are added (081).** The operator approves every
change as a diff.

## Parent PRD

`issues/prd.md`

## What to build

Part (1) of what learning produces (grill, 29 Sep 2026). It comes after the sound
vocabulary and the worked examples, and only when new URLs are added. Today the recipe
styles' numbers were written by hand from the inventories (059, trace table in
`styles/README.md`).

- **A command** `reference draft-style <style>` reads every v2 card tagged with that style
  and proposes the front-matter numbers the cards can support:
  - beat targets from shots per 10 s;
  - clip fraction and median clip length;
  - overlay caps per 60 s by kind;
  - SFX caps by kind (tick, whoosh);
  - `bed_changes_max`.
- **Output:** a diff against `styles/<style>.md` plus an updated trace table. It is never
  applied without the operator's yes. Tier A, Tier B and own are never pooled
  (decision 10.3).

## Acceptance criteria

- [ ] Written when unparked.

## Blocked by

- `issues/081-reference-url-shortlist-history-geopolitics.md`
