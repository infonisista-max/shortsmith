# 003 — Fake planner → plan.json → caption pages

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The plan and caption models exist and flow through the job. The planner interface with its fake returns a canned PicturePlan and SoundStory shaped for the fixture; the pipeline's `planning` step writes `work/plan.json`; a minimal pager turns the final word list into CaptionPage objects written to `work/captions.json`. The full pager rules and boundary tests come in ticket 010; here the pager only fills two to four words per page and times pages per research §4 so the render in 004 has something to draw.

Covers PRD `contracts` (PlanRequest, PicturePlan, SoundStory, CaptionPage), the fake half of `planner`, the minimal `captions`. Decisions 2.3, 3.1, 3.2, 3.4, 4.1, 6.1, 8.1, 12.1.

## Acceptance criteria

- [x] `contracts.PlanRequest`, `PicturePlan` (cut, beats, hook, finale, keywords, title, description, hashtags per 8.1), `SoundStory` (theme, mood_curve, bed_query, cues) and `CaptionPage` are Pydantic with `extra="forbid"`; `PicturePlan.model_json_schema()` is exercised by a test so it stays generatable.
- [x] Plan JSON contains no Remotion or ffmpeg terms (test greps the schema and the fake plan for `remotion`, `ffmpeg`, `filter`).
- [x] `planner.Planner` interface with `plan_picture(PlanRequest) -> PicturePlan` and `plan_sound(...) -> SoundStory`; `FakePlanner` is co-located and returns a canned plan for the 6 s fixture whose beats tile 0–6 s with no gaps, include a `full` cold open with `cold_open` tag, an `off` hook-cards beat, at least one `pip` beat, and name every tier-1 kind from 4.1 as amended by 9.2 at least once across the beats (kinds the renderer cannot draw yet are still valid plan data).
- [x] The pipeline step `planning` builds the PlanRequest from `job.json`, `brief.md`, `refs.json` and `work/asr.json`, calls the planner, writes `work/plan.json` and `work/sound.json`, transitions `transcribing → planning → sourcing`.
- [x] `captions.page(words, keywords, style_numbers) -> list[CaptionPage]` fills 2–4 words per page preferring 3, times pages per research §4 (start − 0.04 s, end min(last end + 0.9 s, next start), last page 1.2 s), and writes `work/captions.json`.
- [x] Smoke asserts `plan.json`, `sound.json` and `captions.json` exist and validate against the models.

## Done — 21 Sep 2026

- Models in `contracts.py`: `PlanRequest` (with `PlanStyle`, `PlanReference`, `Constraints`), `PicturePlan` (`CutPlan`, `Beat`, `Hook`, `Finale`), `SoundStory` (`MoodPoint`, `BedQuery`, `Cue`), `CaptionPage`; all `extra="forbid"`. `TIER1_KINDS` / `TIER2_KINDS` are Literals so the schema lists them and 009 can reject tier 2 with a substitute named instead of a raw Pydantic error.
- A beat has one base `kind` plus `overlays[]` for the motion-graphics kinds that animate on a base per 9.3 (pin_drop, route_arrow, object_path on a map; label_flyin on an infographic; counter on a chart). `stamp` and `lower_third` are named through `event` per the 8.1 beat shape; `presenter_full` / `presenter_pip` through the mode. `planner.kinds_named(plan)` is the one place that counts coverage.
- `FakePlanner`: twelve 0.5 s beats, boundaries on word ends (x.5) or in silence (x.0), full cold open, off hook cards, pip beats, every tier-1 kind named. `plan_sound` takes the picture plan and a `catalogue_tags` sequence (empty until 022).
- `planner.from_settings`: `fake` → `FakePlanner`; `claude_code` / `api` → `UnavailablePlanner` that fails the job at `planning` naming ticket 014 / 015. No silent fallback to the fake for a paid planner setting.
- `captions.page(words, keywords, PagerNumbers, duration_s=)`: greedy threes with a leftover of one folded into the previous page (4 → [4], 7 → [3, 4], 13 → [3, 3, 3, 4]); timing per research §4 with the last page clamped to the clip; one keyword per page by priority. Timing constants are global, the words-per-page numbers move to front matter in 010.
- `pipeline`: steps are now a list; `planning` builds the request (style hard-coded to `explainer` with the prose from `styles/explainer.md` until 008; target duration = min(60, clip)), writes `plan.json`, `sound.json`, `captions.json`; job ends at `sourcing`.
- Bug found and fixed on the way: `jobs._write_json`'s atomic replace fails on Windows with `PermissionError` while the job page poll (or any reader) holds `job.json` open. The worker crashed mid-transition in the app test. The writer now retries for up to ~1 s; `tests/test_jobs.py::test_write_survives_a_concurrent_reader` reproduces it deterministically enough that it fails with retries disabled.
- Open tension for 009: full tier-1 coverage in six seconds cannot also satisfy the explainer numbers (beat min 0.7 s, plan mean 2.0–3.2 s, hook cards 2–4 s, finale 0.8–1.2 s). Noted on ticket 009.

## Blocked by

- Blocked by `issues/001-walking-skeleton.md`

## User stories addressed

- User story 26
- User story 60
- User story 64
