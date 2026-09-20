# 003 — Fake planner → plan.json → caption pages

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The plan and caption models exist and flow through the job. The planner interface with its fake returns a canned PicturePlan and SoundStory shaped for the fixture; the pipeline's `planning` step writes `work/plan.json`; a minimal pager turns the final word list into CaptionPage objects written to `work/captions.json`. The full pager rules and boundary tests come in ticket 010; here the pager only fills two to four words per page and times pages per research §4 so the render in 004 has something to draw.

Covers PRD `contracts` (PlanRequest, PicturePlan, SoundStory, CaptionPage), the fake half of `planner`, the minimal `captions`. Decisions 2.3, 3.1, 3.2, 3.4, 4.1, 6.1, 8.1, 12.1.

## Acceptance criteria

- [ ] `contracts.PlanRequest`, `PicturePlan` (cut, beats, hook, finale, keywords, title, description, hashtags per 8.1), `SoundStory` (theme, mood_curve, bed_query, cues) and `CaptionPage` are Pydantic with `extra="forbid"`; `PicturePlan.model_json_schema()` is exercised by a test so it stays generatable.
- [ ] Plan JSON contains no Remotion or ffmpeg terms (test greps the schema and the fake plan for `remotion`, `ffmpeg`, `filter`).
- [ ] `planner.Planner` interface with `plan_picture(PlanRequest) -> PicturePlan` and `plan_sound(...) -> SoundStory`; `FakePlanner` is co-located and returns a canned plan for the 6 s fixture whose beats tile 0–6 s with no gaps, include a `full` cold open with `cold_open` tag, an `off` hook-cards beat, at least one `pip` beat, and name every tier-1 kind from 4.1 as amended by 9.2 at least once across the beats (kinds the renderer cannot draw yet are still valid plan data).
- [ ] The pipeline step `planning` builds the PlanRequest from `job.json`, `brief.md`, `refs.json` and `work/asr.json`, calls the planner, writes `work/plan.json` and `work/sound.json`, transitions `transcribing → planning → sourcing`.
- [ ] `captions.page(words, keywords, style_numbers) -> list[CaptionPage]` fills 2–4 words per page preferring 3, times pages per research §4 (start − 0.04 s, end min(last end + 0.9 s, next start), last page 1.2 s), and writes `work/captions.json`.
- [ ] Smoke asserts `plan.json`, `sound.json` and `captions.json` exist and validate against the models.

## Blocked by

- Blocked by `issues/001-walking-skeleton.md`

## User stories addressed

- User story 26
- User story 60
- User story 64
