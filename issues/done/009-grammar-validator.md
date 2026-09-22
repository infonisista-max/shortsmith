# 009 — Grammar validator: snap, clamp, reject, one retry, violations on the job page

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The plan validator as pure code over PicturePlan, Transcript and StyleSpec, producing a ValidatedPlan with `clamps[]` or a violation list, wired into the `planning` step so a rejected plan is re-sent once with the list appended and a second failure fails the job with the list on the page. Every count is read from style front matter. The SoundStory rules (cue caps, mood-curve bounds, cue on a non-existent beat, no cue on a bare transition) are included so the sound call is validated from the start.

Covers PRD `grammar`, `contracts.ValidatedPlan`, the retry loop in `planner`/`pipeline`. Decisions 2.3, 3.1, 3.2, 3.4, 4.1, 4.2, 4.3, 7.3, 8.2, 9.4.

## Acceptance criteria

- [x] `grammar.validate(plan, transcript, spec) -> ValidatedPlan | Violations`; ValidatedPlan carries snapped beats, `clamps[]` with one entry per clamp, and the SoundStory clamped.
- [x] Clamps per 8.2: boundaries snapped to the nearest word end within 0.15 s, keywords trimmed to `emphasis_max_ratio`, cues trimmed by dropping planner cues before floor hits, mood curve clipped to +4/−8, hashtags ≤ 5, title ≤ 100 chars.
- [x] Rejections per 8.2 and 3.x/4.x/9.4, each message carrying beat id and rule number: beat outside min/max after snapping, set-piece above `set_piece_max_s`, plan mean outside 2.0–3.2 s, visual-event gap > 1.5 s, `full` without a reason tag or with a tag outside the set, consecutive `full`, full fraction > `full_max_fraction`, PIP run > `pip_max_run`, off run > `off_max_run`, hook beat `pip`, finale not `off`, hook title > 8 words, lifted span not on word boundaries, duplicated cold-open span without `keep`, tier-2 kind (message names the nearest tier-1 substitute), non-presenter beat without exactly one motion, missing `subject_kind`/`query`, no `entity` beat per 60 s when the brief has a proper noun, unique assets < min or > max, reuse > `reuse_max`, transition name outside the style list, whip spacing, cue on a non-existent beat, cue at an enter transition without a landed event, must-use reference id absent.
- [x] Warning (not rejection): no asset reused; title ignores a numeric hook wish; both recorded on the ValidatedPlan for the contact sheet.
- [x] `planning` step: on Violations, the same call is re-sent once with the previous output and the list appended; a second Violations → `failed` at `planning` with the list in `job.json.error.detail` and rendered on the job page; retries are ledger rows once 011 lands (a TODO marker is not acceptable; call a `ledger` hook that is a no-op until 011).
- [x] Boundary tests, `tests/test_grammar.py`: snap within 0.15 s and not at 0.16 s, beat 0.69/0.70 s, mean 1.99/3.21 s, full fraction exactly 0.25 passes, seventh consecutive PIP rejected, duplicated cold-open span, whip spacing (second whip within three beats rejected, two whips in a row rejected), ramp < 1.5 s rejected, 21st cue dropped.
- [x] FakePlanner's canned plan passes validation with zero violations; smoke asserts `work/plan.validated.json` exists.

## Session notes (done, 22 Sep 2026)

- Operator riders: retry exactly once; every rejection and clamp message carries beat id + the decision number verbatim; `styles/*.md` untouched (030 owns spec edits); the fake plan's `wipe` became `fade` (9.4). The ledger hook line above is superseded by the 011 note: the adapter that makes the call records the row, so the pipeline has no ledger code on the retry.
- Fixture rule set (the 003 question): `fixture.smoke_specs(specs)` returns the loaded specs with `explainer` replaced by a deep copy whose beat (`SMOKE_BEATS`), asset-count (`SMOKE_BROLL`) and ramp/cue-cap (`SMOKE_SOUND`) numbers are scaled to six seconds; typography, PIP, palette, finale and everything else stay the shipped values. The validator and the pipeline never know a fixture exists; the smoke, `tests/test_pipeline.py` and `tests/test_app.py` pass the scaled specs (`create_app(specs=...)` is new for that). T3's finale check stays unscaled. Against the real explainer numbers the fake plan is rejected, and a test proves both.
- `grammar.py`: `validate_picture(plan, transcript, spec, *, brief, must_use) -> PictureCheck | Violations`, `validate_sound(story, picture, spec) -> SoundCheck | Violations`, `validate(...)` combining both, `must_use_ids(brief, references)` (a sentence saying "must use" that names a reference by id or caption; 2.3), `proper_nouns(brief)` (capitalised words not opening a sentence; a field label's first word counts). `Violation`, `Clamp`, `ValidatedPlan` and `PlanFeedback` live in `contracts`; `Violations`, `PictureCheck`, `SoundCheck` in `grammar`. `str(Violation)` is `"<beat id or plan> (<rule>): <message>"`; clamps cite the decision whose number they applied (3.1 snap, 6.1 keywords, 7.3 cues and curve, 8.2 hashtags and title).
- Two readings fixed in the module docstring: density (3.1) takes a landed event to land mid-beat, so a beat with one event may run to 2 x `density_gap_max_s` and one with none to the gap; set pieces, hook cards, beats with overlays and the cold open (its punch-in) are not measured inside. Cold-open repeats (3.4): `presenter.cut_list` already removes the lifted span under `drop`, so a repeat is only ever deliberate (`keep`); the validator rejects `keep` when `cut.drop` removes the span, and a plan that forgot the repeat in its runtime fails the 3.1 tiling rule with "the cold open plays twice under 'keep'" in the message.
- Beat boundaries are output seconds and word times are recording seconds: `presenter.source_time(spans, t)` (new, the inverse of `output_time`) maps a boundary through the cut list before the nearest word end is looked up. A boundary inside a word beyond the window is a 3.1 rejection; one in silence stays. Per-60 s counts scale by runtime (floor for minimums, ceil for maximums). Hook card ids are a montage of plan assets and are not showings for `reuse_max`.
- Planner interface: `plan_picture(request, *, feedback=None)` and `plan_sound(request, picture, catalogue_tags=(), *, feedback=None)`; `PlanFeedback` is `{previous: <json text>, violations: [lines]}`. The fake ignores it. Every test subclass gained the keyword.
- Pipeline: picture -> validate -> (retry once) -> sound with the snapped picture -> validate -> (retry once). `PlanRejected(call, violations)` fails the job at `planning` with `STEP_MESSAGES["planning"]`, the list in `job.json.error.violations` (new field on `JobError`, `jobs.fail(violations=...)`) and in `detail`; the page renders `<ul class="violations">` under the error. A retry writes a `jobs.note` line to `job.log` ("picture plan rejected, re-sending once: ..."). Files: `plan.raw.json` / `sound.raw.json` (the planner's last output, kept on failure for the operator), `plan.json` / `sound.json` (snapped and clamped: what render, T3 and the sheet read), `plan.validated.json` (both plus clamps and warnings), `captions.json` paged from the clamped keywords.
- Loops: ruff clean, pyright strict clean, 419 tests pass (50 in `test_grammar.py`), smoke `delivered` in ~30 s with `out/qa.json` read: T1-T4 pass; the only clamp on the fake plan is the keyword trim (4 -> 3); contact sheet shows the PIP and caption block at the spec positions and the three kept keywords boxed.
- Not done here, for later tickets: `target_duration_s` from the style note (2.3) is still unparsed; must-use references depend on the brief wording until refs carry a flag; the landed-event time is an assumption until 026 renders events.

## Note from 003 (21 Sep 2026)

The acceptance line "FakePlanner's canned plan passes validation with zero violations" conflicts with 003 / decision 12.1 ("exercising every tier-1 kind across the 6 s"): naming all nineteen kinds needs twelve 0.5 s beats, which breaks the explainer beat minimum (0.7 s), plan mean (2.0–3.2 s), hook-cards length (2–4 s) and finale length (0.8–1.2 s). Decide here how the validator treats the fixture: 3.2 says every count is a style number, so a fixture-scaled rule set (or a per-60 s scaling of the counts, which the unique-asset and entity rules already imply) is the likely answer; shrinking the fake's coverage is not, since smoke has to exercise every kind.

## Notes from 008

- The style numbers are typed on `styles.StyleSpec`: `beats` (min/max/set-piece/mean range/density gap/snap window/hook slot lengths/title words), `presenter` (modes, full fraction, never-consecutive, reasons, pip/off runs, hook and finale modes), `broll` (kinds, tier-2 kinds, `enter_transitions`, `whip_max_per_3_beats`, asset counts). `pipeline.style_of(job, specs)` returns the job's spec; `PlanRequest.style.numbers` is the same data as a dict.
- 2.3's `target_duration_s` from a style note that names a length is not parsed yet; `job.json.style_note` holds the line.

## Notes from 011

- The ledger exists: a planning retry is `ledger.record(job, "planning", provider, model, units)` with the adapter's usage; there is no no-op hook to call, the adapter that makes the call records it (see the 012/014 notes). `ledger.BudgetExceeded` from a pre-call check already fails the job with "Budget exceeded at step planning."

## Blocked by

- Blocked by `issues/008-style-specs-loader-resolver.md`

## User stories addressed

- User story 12
- User story 13
- User story 15
- User story 16
- User story 25
- User story 63
