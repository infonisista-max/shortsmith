# 038 — Seed the reference library: at least three shorts per category

## Type

HITL — operator-approved input per 10.3: candidate URLs are researched by the paired review chat, Shubham approves the list, the tool does the rest. The agent's part is running the tool and checking the README output.

## Parent PRD

`issues/prd.md`

## What to build

Run `shortsmith reference add` for ≥ 3 shorts in each seeded category (history, geopolitics, finance, product, motivation, science, and any the day-14 recordings need) and keep Shubham's two approved shorts as the calibration anchors. Only analysis is committed; media stays git-ignored.

Covers PRD "Operator-supplied inputs". Decisions 10.3.

## Inputs

Seed URLs: `docs/references.md` (operator-supplied, 24 Sep 2026). Measurement tooling: `docs/reference-tooling.md`.

- Every entry carries both its tier and its category (per decision 10.3). Tiers: A = technique to reach and B = proven on this channel and presenter (both from `docs/references.md`); `anchor` = the operator's approved and rated shorts, the calibration anchor per 10.3(3). Neither field replaces the other; no category or tier is renamed.
- Every entry carries its operator rating. Ratings are final (rubric: 8 = upload as-is, 6 = after ≤ 5 min fixes):
  - `anchor`: NKB 6, Dyson 6.
  - Tier A Shorts (`ATkSnL_CdLg`, `QjwDTLPLJ6c`, `M78CO3Ybr7U`): 8 each.
  - Tier B Shorts (`nBihHUlYOQk`, `FbaBcWgMIEY`, `ePTZVwipoAM`): 8 each.
  - Tier A long-form (`id00R-3OmJ0`): 10 for editing/technique; stays pacing-excluded.
- Calibration state 25 Sep 2026: scale instantiated at 6 (anchors), 8 (reference Shorts), 10 (long-form technique); consistent with 10.3(3), no amendment.
- Tier A and Tier B are never pooled into one average.
- The long-form (`id00R-3OmJ0`) is tagged technique-only and excluded from pacing statistics, as built in `036`.
- Open question for this ticket, not decided: whether each reference also gets a committed fingerprint JSON of measured fields that the planner consumes as targets (`docs/reference-tooling.md`, "Open question, not decided").

Decision 10.3, verbatim from `docs/grill-decisions.md`:

> 10.3 — The reference library is a core product asset, bigger than Shubham's two shorts: a mini library of top-performing shorts from top-subscribed channels across categories (history, geopolitics, finance, product, motivation, science, …), and the critic compares against THEM, the market's best. (1) Library builder tool in the repo (`shortsmith.reference add <url|channel> --category <c>`): downloads a local copy (yt-dlp, git-ignored under `work/reference/<category>/` like current media; only analysis is committed), extracts frames with the same ffmpeg command, and auto-analyses the short into measured pattern data — cuts per 10 s (ffmpeg scene-change detection), caption pages per 10 s (OCR on a 4 fps strip), visual-change rate (frame-difference energy), B-roll fraction and presenter mode timeline (face detector: face size → full / PIP / off), hook structure in the first 2 s (frame strip + vision description), transition density, sound-hit density (onset detection on the non-speech band) — written into `docs/reference/<category>/README.md` in the existing format, each figure tagged MEASURED or ESTIMATED as research.md does. (2) The critic rubric anchors on those measured patterns plus the "what it does well" text, so a score means "matches what top shorts measurably do". (3) Shubham's approved and rated shorts stay in the library as the calibration anchor: top-creator entries define the ceiling, Shubham's rated shorts define what a 6 and an 8 mean, so the critic stays calibrated to the phone verdict per 10.2 and is not crushed by MrBeast budgets. (4) Seed ≥ 3 reference shorts per category by day 14 (Shubham supplies URLs, the tool does the rest); growing the library is one command per new short forever. Critic inputs per job: contact sheet at 1 fps, 8-frame PIP strip, hook strip (first 2 s at 4 fps), plan summary text (beat count, mode fractions, density, clamps, rescued beats, asset origins), stem balance report, transcript, plus the job's category pattern data and frames and the approved-shorts anchors; category is set by the planner from a fixed list. Critic output is a Pydantic model: E1–E10 scores with one reason each, overall, up to five "fix in 5 minutes" notes shown on the page. Rating capture: job page shows short, contact sheet, critic scores, a 1–10 slider + note → `job.json.rating`; `data/calibration.json` tracks the critic-vs-phone match streak and the page shows "critic agreed N of last 5".

## Acceptance criteria

- [ ] `docs/reference/<category>/README.md` exists for every seeded category with ≥ 3 entries, each with measured figures and tags.
- [ ] The approved NKB and Dyson shorts remain in the pack as anchors with their phone ratings recorded.
- [ ] No media under `docs/`; `work/reference/` is git-ignored; the pack version is recorded in `docs/reference/README.md`.

## Blocked by

- Blocked by `issues/037-reference-analyser-ocr-modes-hook.md`

## User stories addressed

- User story 45
- User story 49
