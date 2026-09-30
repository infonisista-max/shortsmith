# 100 — Never AI for a named real person, on every path

## Type

AFK

## Parent PRD

`issues/prd.md`

## Why

096 put the rule on re-sourced beats only. `Generating.make` (`assets/generate.py:361`)
has no guard, and three callers can generate for a named person:
- `source_opening` (`assets/__init__.py:1401`), which also forces past the cap;
- the concept + `source_intent=generate` path (`:1482-1484`), which checks `subject_kind`
  only;
- the main still ladder fallback (`:1503`).

## What to build

- One guard **inside `Generating.make`** (the single door): a beat that depicts a named
  person (099's `named_person`, or the old `named_entity` when its subject is a person) is
  never generated, whatever the caller. The refusal is logged, not raised.
- The caller then takes 096's ladder: owner reference → a real photo of that person
  already shown → the gradient. An opening beat falls to the gradient, as in 096.

## Acceptance criteria

- [x] A test per caller (opening, concept+generate, main fallback, replaced) proves no
      generation for a named person, with fakes.
- [x] A named place, era or object may still be generated as the last rung.
- [x] No job fails because of the guard (smoke green).

## Done note

- One guard in the single door: `Generating.make` refuses any beat `names_a_person`
  (`assets/generate.py:162`, check at `:382`) with a job-log note
  (`generation: bNN depicts a named person, who is never generated (100) ...`), never an
  error. `PERSON_DEPICTS` (`generate.py:159`) already holds 099's `named_person`; until
  099 lands the old `named_entity` counts as a person on any non-`concept` beat (an
  `entity` beat cannot tell a person from a place, so it is read the safe way). A
  `concept` beat depicting a `named_entity` (a named era, event, object) may still be
  generated.
- Callers unchanged: the opening falls to the gradient; the still ladder takes a real
  photo of that person already shown (rung 3), else the gradient; a concept beat's
  `generate` intent falls through to search. Module docstring `assets/__init__.py:29`.
- Tests: `tests/test_never_ai_person.py` (the door, a named place/era, and one per
  caller: opening, concept+generate, main fallback, replaced). Three older tests that
  expected an illustrated named person now expect the gradient
  (`test_assets.py` named opening and run04 b05, `test_assets_f1.py`).
- Note for 099: an `entity` beat depicting a named place is refused today; once
  `named_place` etc. exist, drop the `named_entity` fallback for them.

## Blocked by

None (reads 099's split if present).

## User stories addressed

Operator, 30 Sep 2026: "never AI for a named real person must apply everywhere, not only
to re-sourced beats."
