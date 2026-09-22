# 048 — `hitech` smoke render end to end

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Prove the style system works beyond `explainer` before day 14: the `hitech` draft's front matter is completed with its own numbers, palette, transition subset (cut/fade/wipe/zoom) and `requires_components`, and the fixture renders end to end under it with every fake. Not judged, not shipped; `status` stays `draft` and its aliases still redirect to `explainer` on the page.

Covers PRD "Further Notes" slice 10. Decisions 1.4, 9.2, 9.4.

## Acceptance criteria

- [ ] `styles/hitech.md` passes the loader with `status: draft` and a complete `requires_components` list against the registry.
- [ ] `python -m shortsmith.smoke --style hitech` renders the fixture with the hitech numbers and palette, uses `wipe` on at least one beat, and passes T1–T13.
- [ ] The upload form still resolves "hitech" to `explainer` with the notice; a test asserts it.
- [ ] `docs/components.md` records which components the hitech render exercised.

## Notes from 008

- `styles/hitech.md` is a complete draft spec (status `draft`, own palette, transitions cut/fade/wipe/zoom, `requires_components: [captions, pip, spec_stamp, glow_ring, counter]`). The resolver never picks a draft, so the smoke render has to select it directly: `jobs.create(..., style="hitech")` or a `Resolution(name="hitech", ...)` into `ingest.accept`, with `PlanStyle.status` set to `draft`. The loader accepts unbuilt components on a draft.

## Blocked by

- Blocked by `issues/030-transition-vocabulary-registry-complete.md`
- Blocked by `issues/032-gate-t8-t11-t12-t13.md`

## User stories addressed

- User story 3
- User story 65
