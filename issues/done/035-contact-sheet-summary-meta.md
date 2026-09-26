# 035 — Contact sheet summary panel, meta.json, copyable publishing text

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The evidence closes. The contact sheet's last row becomes the real summary panel: T1–T13 dots, critic E1–E10 scores with overall and the five fix notes, clamp count, ledger total and the soft-cap flag. `out/meta.json` records technical results, critic scores, human rating, reference category and pack version, prompt version, style spec version and the ledger. The job page shows title, description with credits and disclosure, and up to five hashtags as copyable text.

Covers PRD `contact_sheet` (summary), `pipeline` `meta.json`, `app` publishing text. Decisions 10.4, 5.4, 8.1, 8.3, 1.2, 11.1.

## Acceptance criteria

- [x] Summary row per 10.4 with green/red dots for T1–T13, the critic block, clamp count, rescued count, ledger total and the over-soft-cap flag; `contact.jpg` stays under 2 MB with a 60 s job (test composes 60 frames).
- [x] `out/meta.json` per 10.4 with `reference_pack_version` read from `docs/reference/README.md`, `prompt_version` from the plan, `style_version` from the spec front matter, the full ledger and the human rating when present; rewritten when the rating or performance changes.
- [x] Job page shows `title`, description = plan description + credits + disclosure line, hashtags ≤ 5, each in a copy-to-clipboard block.
- [x] Unit tests on panel layout, meta contents and the description assembly; smoke asserts `meta.json` validates against `contracts.Meta`.

## Done (26 Sep 2026)

- `contact_sheet`: the summary panel is `DOTS_H` plus seven `LINE_H` lines (`SUMMARY_LINES` = critic line + five fix notes + the counts line); `panel_lines(report, cost, counts)` is the pure text, `panel_line_box` the geometry, the overall's dot is green at 7+ and red under (`CRITIC_PASS`). The counts line is pinned to the bottom slot. `counts_line` / `clamped_beats` read `plan.validated.json`; a clamped beat now gets the red corner (10.4, the 016 note). The pipeline composes the sheet twice: once for the critic to score, once with the scores drawn (`_qa` calls `gate.contact_sheet` again after `critic_module.run`).
- `contracts.Meta` (+ `TechnicalResult`); `CostRow`, `Rating`, `Performance`, `CriticSummary`, `RATING_MIN/MAX`, `ViewsSource` moved from `jobs` into `contracts` (jobs re-exports them under the old names) so `Meta` carries them without an import cycle.
- `meta.py`: `build(job)` / `write(job)` / `load(job)` / `pack_version(readme)`. Written by `pipeline.run_job` after the verdict settles, and by the rating and performance routes after every save. `delivered` = T1–T13 pass and the four deliverables exist; `status` is the settled one.
- `docs/reference/README.md` carries `Pack version: 1` (the 036 tool bumps it). Every `styles/*.md` carries `version: "1"` (a required `FrontMatter` key, documented in `styles/README.md`); `_plan` records it on `job.json.style_version` beside `prompt_version`.
- `publishing.py`: `assemble(plan, credits)` and `load(job)`; the page's `publishing.html` block has three `<pre>` blocks with clipboard buttons. `meta.json` is served under `OUT_FILES` and linked beside `qa.json`.
- Smoke: `check_meta`, `check_publishing`, the panel's critic and counts lines are drawn, and the critic's sheet is the same size as, but not the same bytes as, the recomposed file.
- Not done here: the 047 gate reads this file; `meta.json` has no `title`/`hashtags` (the page has them, `plan.json` keeps them).

## Blocked by

- Blocked by `issues/034-rating-calibration-youtube-fields.md`

## Notes from 016

- The strip line under each frame is done (`contact_sheet.strip_line`: beat id, mode letter as drawn, kind as drawn, origin letter U/W/C/O/P/X/G/L, red corner on rescued or downgraded beats). 10.4 also marks clamped beats (8.2); not drawn yet (`ValidatedPlan.clamps` carry `beat_id`).

## User stories addressed

- User story 32
- User story 43
- User story 51
