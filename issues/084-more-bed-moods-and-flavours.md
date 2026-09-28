# 084 — More bed moods and flavours in the approved library

## Type

HITL — **parked until 079 (run05) is decided go.** Same yes/no listening as 075.

## Parent PRD

`issues/prd.md`

## What to build

075's first batch covers `tense_dramatic`, `investigative_pulse`,
`mysterious_curiosity`, `calm_ambient`, `middle_east` and `indian`. This ticket fills
the rest of `assets/audio/moods.yaml`:

- moods: `eerie_scifi`, `upbeat_electronic`, `energetic_beat`;
- flavours: `east_asian`, `european`;
- any mood the v2 cards (073) show that the list lacks.

Each is marked `active` once it has approved beds. 076 then lets the planner pick it.

## Acceptance criteria

- [ ] A shortlist per new slot built with 075's tool, the operator's yes/no, and the
      moods marked `active`.

## Blocked by

- `issues/075-audio-shortlist-and-approved-library.md`
- `issues/079-run05-learning-check.md`
