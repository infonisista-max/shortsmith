# 037 — Reference analyser: caption pages by OCR, presenter mode timeline, hook description

## Type

HITL — needs new package: an OCR engine (`pytesseract` with a Tesseract binary, or `easyocr`/`rapidocr-onnxruntime`), whichever `uv add` and the machine allow. The operator picks and approves; then this ticket becomes AFK. Face detection reuses the 013 package.

## Parent PRD

`issues/prd.md`

## What to build

The remaining measured figures: caption pages per 10 s from OCR on a 4 fps strip (page changes = text changes), B-roll fraction and presenter mode timeline from face size per frame (full / PIP / off), and the hook structure in the first 2 s as a frame strip plus a vision description through the critic's model. The README figures flip from ESTIMATED to MEASURED.

Covers PRD `reference` (analyser extras). Decisions 10.3, 12.2.

## Acceptance criteria

- [ ] Caption pages per 10 s from OCR text changes on a 4 fps strip; a synthetic clip with drawn caption pages at known times yields the known count.
- [ ] Mode timeline: face box per frame → `full` (large), `pip` (small circle region), `off` (none); B-roll fraction derived; tested on a synthetic clip with a face that changes size.
- [ ] Hook structure: first 2 s at 4 fps written as `hook_strip.jpg` and described by one vision call (ledger row in a `reference` step); the description is tagged ESTIMATED.
- [ ] README entries carry all figures with correct tags; `reference add` on a real short fills every field.

## Blocked by

- Blocked by `issues/036-reference-tool-download-analyse.md`
- Blocked by `issues/013-presenter-face-measurement.md`

## User stories addressed

- User story 49
