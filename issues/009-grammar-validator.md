# 009 — Grammar validator: snap, clamp, reject, one retry, violations on the job page

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The plan validator as pure code over PicturePlan, Transcript and StyleSpec, producing a ValidatedPlan with `clamps[]` or a violation list, wired into the `planning` step so a rejected plan is re-sent once with the list appended and a second failure fails the job with the list on the page. Every count is read from style front matter. The SoundStory rules (cue caps, mood-curve bounds, cue on a non-existent beat, no cue on a bare transition) are included so the sound call is validated from the start.

Covers PRD `grammar`, `contracts.ValidatedPlan`, the retry loop in `planner`/`pipeline`. Decisions 2.3, 3.1, 3.2, 3.4, 4.1, 4.2, 4.3, 7.3, 8.2, 9.4.

## Acceptance criteria

- [ ] `grammar.validate(plan, transcript, spec) -> ValidatedPlan | Violations`; ValidatedPlan carries snapped beats, `clamps[]` with one entry per clamp, and the SoundStory clamped.
- [ ] Clamps per 8.2: boundaries snapped to the nearest word end within 0.15 s, keywords trimmed to `emphasis_max_ratio`, cues trimmed by dropping planner cues before floor hits, mood curve clipped to +4/−8, hashtags ≤ 5, title ≤ 100 chars.
- [ ] Rejections per 8.2 and 3.x/4.x/9.4, each message carrying beat id and rule number: beat outside min/max after snapping, set-piece above `set_piece_max_s`, plan mean outside 2.0–3.2 s, visual-event gap > 1.5 s, `full` without a reason tag or with a tag outside the set, consecutive `full`, full fraction > `full_max_fraction`, PIP run > `pip_max_run`, off run > `off_max_run`, hook beat `pip`, finale not `off`, hook title > 8 words, lifted span not on word boundaries, duplicated cold-open span without `keep`, tier-2 kind (message names the nearest tier-1 substitute), non-presenter beat without exactly one motion, missing `subject_kind`/`query`, no `entity` beat per 60 s when the brief has a proper noun, unique assets < min or > max, reuse > `reuse_max`, transition name outside the style list, whip spacing, cue on a non-existent beat, cue at an enter transition without a landed event, must-use reference id absent.
- [ ] Warning (not rejection): no asset reused; title ignores a numeric hook wish; both recorded on the ValidatedPlan for the contact sheet.
- [ ] `planning` step: on Violations, the same call is re-sent once with the previous output and the list appended; a second Violations → `failed` at `planning` with the list in `job.json.error.detail` and rendered on the job page; retries are ledger rows once 011 lands (a TODO marker is not acceptable; call a `ledger` hook that is a no-op until 011).
- [ ] Boundary tests, `tests/test_grammar.py`: snap within 0.15 s and not at 0.16 s, beat 0.69/0.70 s, mean 1.99/3.21 s, full fraction exactly 0.25 passes, seventh consecutive PIP rejected, duplicated cold-open span, whip spacing (second whip within three beats rejected, two whips in a row rejected), ramp < 1.5 s rejected, 21st cue dropped.
- [ ] FakePlanner's canned plan passes validation with zero violations; smoke asserts `work/plan.validated.json` exists.

## Blocked by

- Blocked by `issues/008-style-specs-loader-resolver.md`

## User stories addressed

- User story 12
- User story 13
- User story 15
- User story 16
- User story 25
- User story 63
