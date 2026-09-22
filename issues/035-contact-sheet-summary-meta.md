# 035 — Contact sheet summary panel, meta.json, copyable publishing text

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The evidence closes. The contact sheet's last row becomes the real summary panel: T1–T13 dots, critic E1–E10 scores with overall and the five fix notes, clamp count, ledger total and the soft-cap flag. `out/meta.json` records technical results, critic scores, human rating, reference category and pack version, prompt version, style spec version and the ledger. The job page shows title, description with credits and disclosure, and up to five hashtags as copyable text.

Covers PRD `contact_sheet` (summary), `pipeline` `meta.json`, `app` publishing text. Decisions 10.4, 5.4, 8.1, 8.3, 1.2, 11.1.

## Acceptance criteria

- [ ] Summary row per 10.4 with green/red dots for T1–T13, the critic block, clamp count, rescued count, ledger total and the over-soft-cap flag; `contact.jpg` stays under 2 MB with a 60 s job (test composes 60 frames).
- [ ] `out/meta.json` per 10.4 with `reference_pack_version` read from `docs/reference/README.md`, `prompt_version` from the plan, `style_version` from the spec front matter, the full ledger and the human rating when present; rewritten when the rating or performance changes.
- [ ] Job page shows `title`, description = plan description + credits + disclosure line, hashtags ≤ 5, each in a copy-to-clipboard block.
- [ ] Unit tests on panel layout, meta contents and the description assembly; smoke asserts `meta.json` validates against `contracts.Meta`.

## Blocked by

- Blocked by `issues/034-rating-calibration-youtube-fields.md`

## Notes from 016

- The strip line under each frame is done (`contact_sheet.strip_line`: beat id, mode letter as drawn, kind as drawn, origin letter U/W/C/O/P/X/G/L, red corner on rescued or downgraded beats). 10.4 also marks clamped beats (8.2); not drawn yet (`ValidatedPlan.clamps` carry `beat_id`).

## User stories addressed

- User story 32
- User story 43
- User story 51
