# 019 — Image generator: Gemini direct REST, fake, prompt templates, cap, disclosure

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Ladder rung 2 becomes real. The `ImageGenerator` interface with a Gemini adapter over direct REST (no SDK, `httpx`), a fake that writes a solid 1080x1920 PNG with the prompt burned in, two prompt templates selected by the planner's `depicts`, always 9:16, the per-short cap, one retry on API error, and the generated block in the rights row so the AI disclosure line and T9's named-entity rule apply.

Covers PRD `assets` (generator), `rights` (generated rows). Decisions 4.2, 5.4, 5.5, 5.6, 12.1, 13.1.

## Acceptance criteria

- [ ] `ImageGenerator.generate(prompt, size) -> GeneratedImage`; `GeminiImageGenerator` posts to `IMAGE_GEN_ENDPOINT` with `IMAGE_GEN_MODEL`, one retry on error, then "nothing generated" and the ladder moves to rung 3; `FakeImageGenerator` writes the PNG with the prompt text drawn on it.
- [ ] Prompt templates built by code: `scene` → "<style look> photograph, vertical 9:16: <scene>, <mood>, <lighting>, realistic" with "no faces clearly visible" only when no person is intended; `named_entity` → "<style illustration look>, vertical 9:16, illustration of <scene>, clearly stylised, not a photograph"; always appended: no text, no watermarks, no logos; the look strings come from style front matter.
- [ ] `IMAGE_GEN=none` makes rung 2 a no-op; `gen_max_per_short` from the style caps generation and the cap hit skips to rung 3; each generation is a ledger row priced per image.
- [ ] Rights row `generated: {model, prompt, render, depicts}`; `depicts: named_entity` always uses the illustration template so T9 passes; the description ends with "Some scenes are AI-generated illustrations" when any row is generated.
- [ ] Generated files are cached by sha256(prompt + model) in `work/assets/` so retries re-generate nothing.
- [ ] Recorded request/response JSON under `tests/fixtures/gemini/`; tests assert endpoint, model, size request and body parsing; the ninth generation in a short is refused by the cap.
- [ ] Smoke runs with `FakeImageGenerator` on a concept beat whose fake search returns nothing and reaches `delivered` with rung 2 recorded.

## Notes from 011

- `ledger.record(job, "sourcing", "gemini", model, {"images": 1})` per generated image after `check_before_call`; the `gemini` price is required at startup when `IMAGE_GEN=gemini`.

## Blocked by

- Blocked by `issues/016-asset-step-ladder-rights.md`

## Notes from 006

- Pillow is installed (`pillow==12.3.0`); `FakeImageGenerator` can draw the prompt with `ImageDraw` and the bundled Poppins.

## User stories addressed

- User story 17
- User story 18
- User story 22
- User story 32
- User story 34
