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

- [ ] A test per caller (opening, concept+generate, main fallback, replaced) proves no
      generation for a named person, with fakes.
- [ ] A named place, era or object may still be generated as the last rung.
- [ ] No job fails because of the guard (smoke green).

## Blocked by

None (reads 099's split if present).

## User stories addressed

Operator, 30 Sep 2026: "never AI for a named real person must apply everywhere, not only
to re-sourced beats."
