# 019 — Image generator: Gemini direct REST, fake, prompt templates, cap, disclosure

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Ladder rung 2 becomes real. The `ImageGenerator` interface with a Gemini adapter over direct REST (no SDK, `httpx`), a fake that writes a solid 1080x1920 PNG with the prompt burned in, two prompt templates selected by the planner's `depicts`, always 9:16, the per-short cap, one retry on API error, and the generated block in the rights row so the AI disclosure line and T9's named-entity rule apply.

Covers PRD `assets` (generator), `rights` (generated rows). Decisions 4.2, 5.4, 5.5, 5.6, 12.1, 13.1.

## Acceptance criteria

- [x] `ImageGenerator.generate(prompt, size) -> GeneratedImage`; `GeminiImageGenerator` posts to `IMAGE_GEN_ENDPOINT` with `IMAGE_GEN_MODEL`, one retry on error, then "nothing generated" and the ladder moves to rung 3; `FakeImageGenerator` writes the PNG with the prompt text drawn on it.
- [x] Prompt templates built by code: `scene` → "<style look> photograph, vertical 9:16: <scene>, <mood>, <lighting>, realistic" with "no faces clearly visible" only when no person is intended; `named_entity` → "<style illustration look>, vertical 9:16, illustration of <scene>, clearly stylised, not a photograph"; always appended: no text, no watermarks, no logos; the look strings come from style front matter.
- [x] `IMAGE_GEN=none` makes rung 2 a no-op; `gen_max_per_short` from the style caps generation and the cap hit skips to rung 3; each generation is a ledger row priced per image.
- [x] Rights row `generated: {model, prompt, render, depicts}`; `depicts: named_entity` always uses the illustration template so T9 passes; the description ends with "Some scenes are AI-generated illustrations" when any row is generated.
- [x] Generated files are cached by sha256(prompt + model) in `work/assets/` so retries re-generate nothing.
- [x] Recorded request/response JSON under `tests/fixtures/gemini/`; tests assert endpoint, model, size request and body parsing; the ninth generation in a short is refused by the cap.
- [x] Smoke runs with `FakeImageGenerator` on a concept beat whose fake search returns nothing and reaches `delivered` with rung 2 recorded.

## Done (019)

- `assets/generate.py` holds the whole rung: `ImageGenerator` (`generate(prompt, size) -> GeneratedImage`, bytes plus the model that made them), `build_prompt` with the two templates, `GeminiImageGenerator`, `FakeImageGenerator` and `Generating`, the per-job bookkeeping (cap, file cache, one retry). 016's `assets.GeneratedImage` (path plus a `Generated`) was renamed `GeneratedAsset` to free the interface name; `Sourcing.generate` (a bare callable) became `Sourcing.generator: ImageGenerator | None` and `source_assets(generating=...)`.
- Mood and lighting had nowhere to come from, so `broll.scene_mood` and `broll.scene_lighting` joined the front matter of all four styles beside `photo_look` / `illustration_look`; no prompt words live in code.
- `depicts` is the planner's label when it set one, else `named_entity` on an `entity` beat and `scene` anywhere else; `named_entity` is always the illustration template, so T9 cannot fail on a generated row.
- The retry sits in `Generating`, not in the adapter, so every generator gets one retry and one "nothing generated" note; `BudgetExceeded` still propagates and fails the job (11.3).
- 016's per-query `result.json` for generation is gone: the sha256(prompt + model) folder under `work/assets/` is the cache, so a re-render generates nothing while a transient API failure is retried on a retry-from-step (043).
- Smoke runs `FakeImageGenerator`: the fake plan's three `generate` concept beats (b07, b08, b10) come back at rung 2 with prompts, the credits carry the disclosure line, and the ledger stays empty.

## Blocked / for the operator

`.env*` is unwritable from the agent session, so `.env.example` still lacks these. The lines to paste:

```
IMAGE_GEN=none                  # none | fake | gemini (decision 5.5)
IMAGE_GEN_MODEL=gemini-2.5-flash-image
IMAGE_GEN_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
GEMINI_API_KEY=
```

`IMAGE_GEN=gemini` needs `GEMINI_API_KEY` (startup check) and a `gemini.images` price in `prices.yaml` (already in `prices.example.yaml`). The default model string is the one to sanity-check against Google's current image model list before the first paid run; swapping it is an `.env` edit.

## Notes from 011

- `ledger.record(job, "sourcing", "gemini", model, {"images": 1})` per generated image after `check_before_call`; the `gemini` price is required at startup when `IMAGE_GEN=gemini`.

## Blocked by

- Blocked by `issues/016-asset-step-ladder-rights.md`

## Notes from 006

- Pillow is installed (`pillow==12.3.0`); `FakeImageGenerator` can draw the prompt with `ImageDraw` and the bundled Poppins.

## Notes from 016

- The generator plugs in as `assets.Sourcing.generate`, a callable `(beat, dest_dir) -> assets.GeneratedImage | None` (`path` plus a `contracts.Generated` with model, prompt, render, depicts); None in place of the callable is `IMAGE_GEN=none`. `from_settings` does not build one yet.
- Called first on `concept` beats with `source_intent: generate`, otherwise as ladder rung 2 after both queries found nothing on every source; results cache under `work/assets/<cache_key(query, "generated")>/`. The `gen_max_per_short` cap is not counted yet.
- T9 already fails a generated row without a prompt and a named entity rendered photoreal (`rights.completeness`); `credits.md` gets the disclosure line when any row is generated.

## User stories addressed

- User story 17
- User story 18
- User story 22
- User story 32
- User story 34
