# 038 — Seed the reference library: at least three shorts per category

## Type

HITL — operator-approved input per 10.3: candidate URLs are researched by the paired review chat, Shubham approves the list, the tool does the rest. The agent's part is running the tool and checking the README output.

## Parent PRD

`issues/prd.md`

## What to build

Run `shortsmith reference add` for ≥ 3 shorts in each seeded category (history, geopolitics, finance, product, motivation, science, and any the day-14 recordings need) and keep Shubham's two approved shorts as the calibration anchors. Only analysis is committed; media stays git-ignored.

Covers PRD "Operator-supplied inputs". Decisions 10.3.

## Acceptance criteria

- [ ] `docs/reference/<category>/README.md` exists for every seeded category with ≥ 3 entries, each with measured figures and tags.
- [ ] The approved NKB and Dyson shorts remain in the pack as anchors with their phone ratings recorded.
- [ ] No media under `docs/`; `work/reference/` is git-ignored; the pack version is recorded in `docs/reference/README.md`.

## Blocked by

- Blocked by `issues/037-reference-analyser-ocr-modes-hook.md`

## User stories addressed

- User story 45
- User story 49
