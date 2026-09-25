# 037 — Reference analyser: caption pages by OCR, presenter mode timeline, hook description

## Type

HITL — needs new package: an OCR engine (`pytesseract` with a Tesseract binary, or `easyocr`/`rapidocr-onnxruntime`), whichever `uv add` and the machine allow. The operator picks and approves; then this ticket becomes AFK. Face detection reuses the 013 package. The approval waits on the tool verdicts required under "Reference tooling" below.

## Parent PRD

`issues/prd.md`

## What to build

The remaining measured figures: caption pages per 10 s from OCR on a 4 fps strip (page changes = text changes), B-roll fraction and presenter mode timeline from face size per frame (full / PIP / off), and the hook structure in the first 2 s as a frame strip plus a vision description through the critic's model. The README figures flip from ESTIMATED to MEASURED.

Covers PRD `reference` (analyser extras). Decisions 10.3, 12.2.

## Reference tooling

Read `docs/reference-tooling.md` and `docs/references.md` in full before proposing.

Before implementation, write into this ticket one verdict per tool in `docs/reference-tooling.md`: Gemini API, Demucs, PySceneDetect, and the Qwen cost escape hatch (Qwen is the operator's standing call: acknowledge it and say where it would slot in, do not re-decide it). Weigh Gemini and Qwen3-VL directly against the OCR candidates above and against the critic's model for the hook description. Each verdict states:

- use or reject, with the reason; on reject, what this ticket does instead;
- dependency footprint (packages, binaries, model weights, GPU need, install size);
- impact on the `046` Docker image;
- per-reference API cost (units per reference and the resulting estimate; zero for local tools).

If `036` already records a verdict for a tool that this ticket does not use, cite it by one line instead of repeating it. If `036` has no verdict for that tool, write the full verdict here. Silence on a tool is not a verdict.

The real short for "`reference add` on a real short" comes from `docs/references.md`.

## Acceptance criteria

- [ ] Tool verdicts for Gemini API, Demucs, PySceneDetect and Qwen are written in this ticket (or cited from an existing `036` verdict), each with use/reject and reason, dependency footprint, `046` Docker impact and per-reference API cost, before implementation starts.
- [ ] Caption pages per 10 s from OCR text changes on a 4 fps strip; a synthetic clip with drawn caption pages at known times yields the known count.
- [ ] Mode timeline: face box per frame → `full` (large), `pip` (small circle region), `off` (none); B-roll fraction derived; tested on a synthetic clip with a face that changes size.
- [ ] Hook structure: first 2 s at 4 fps written as `hook_strip.jpg` and described by one vision call (ledger row in a `reference` step); the description is tagged ESTIMATED.
- [ ] README entries carry all figures with correct tags; `reference add` on a real short fills every field.

## Blocked by

- Blocked by `issues/036-reference-tool-download-analyse.md`

## User stories addressed

- User story 49
