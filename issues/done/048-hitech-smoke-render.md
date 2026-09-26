# 048 — `hitech` smoke render end to end

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Prove the style system works beyond `explainer` before day 14: the `hitech` draft's front matter is completed with its own numbers, palette, transition subset (cut/fade/wipe/zoom) and `requires_components`, and the fixture renders end to end under it with every fake. Not judged, not shipped; `status` stays `draft` and its aliases still redirect to `explainer` on the page.

Covers PRD "Further Notes" slice 10. Decisions 1.4, 9.2, 9.4.

## Acceptance criteria

- [x] `styles/hitech.md` passes the loader with `status: draft` and a complete `requires_components` list against the registry.
- [x] `python -m shortsmith.smoke --style hitech` renders the fixture with the hitech numbers and palette, uses `wipe` on at least one beat, and passes T1–T13.
- [x] The upload form still resolves "hitech" to `explainer` with the notice; a test asserts it.
- [x] `docs/components.md` records which components the hitech render exercised.

## Done note (2026-09-26)

- `styles/hitech.md`: `requires_components` is now the twenty registry names the render exercises (the old `spec_stamp` / `glow_ring` were not registry components: the spec stamp is `stamp` in the `cyan_white` palette, the glow border the `pip` ring). Added the `list`, `split`, `wall`, `chart`, `infographic`, `counter` and `map` motion rows the renderer and `infographics.numbers_for` read, with hitech numbers (flat 2 px cards, deeper dims, dark land / cyan coast). Status stays `draft`; the prose says the numbers are a first draft for the smoke, not read off reference frames.
- `fixture.smoke_specs(specs, name=DEFAULT)`: the fixture-shaped copy can be made of any loaded style, so the draft is judged by its own numbers scaled to the clip.
- `planner/fake.py`: the fake reads `broll.enter_transitions` from the request's style numbers and swaps a canned enter the style does not enable for the nearest enabled one (`ENTER_FALLBACKS`: whip → wipe, spring → zoom, else cut). Under hitech the plan enters with exactly cut, fade, wipe, zoom (wipe on b04). With no numbers the explainer five are unchanged.
- `smoke.py`: `--style` flag (argparse) and `run_smoke(root, style=...)`. For a draft the smoke first proves `styles.resolve(<name>)` still redirects to `explainer` with the 1.4 notice, then selects the draft directly through `Resolution(name=<draft>)`. Every check that read `styles.DEFAULT` now reads the selected style; new `check_look` asserts the render spec's palette, caption typography, PIP ring and stamp colour are the selected spec's. Summary line starts `smoke ok: style <name>, job ...`.
- `docs/components.md`: the registry table with explainer and hitech smoke columns per beat, and the three 028 overlays listed `incomplete`; 047 reads it.
- Tests: `test_fixture` (named scaling), `test_planner` (enters unchanged without numbers; hitech subset covered), `test_styles` (hitech components complete and in the registry, doc rows), `test_smoke` (flag parsing; a real end-to-end hitech render asserting the draft's look and T1–T13). The existing `test_app` tests already assert the form's redirect.
- Observed: the hitech run places 1 cue where explainer places 2, because the renderer scales the on-disk `cues_max_per_60s` (16 vs 20) to six seconds. Style number, not a bug.
- Not done here: `lower_third` as a standalone overlay is not exercised by the fixture plan under either style (b04's card strip carries the label); recorded in the doc.

## Notes from 008

- `styles/hitech.md` is a complete draft spec (status `draft`, own palette, transitions cut/fade/wipe/zoom, `requires_components: [captions, pip, spec_stamp, glow_ring, counter]`). The resolver never picks a draft, so the smoke render has to select it directly: `jobs.create(..., style="hitech")` or a `Resolution(name="hitech", ...)` into `ingest.accept`, with `PlanStyle.status` set to `draft`. The loader accepts unbuilt components on a draft.

## Blocked by

- Blocked by `issues/030-transition-vocabulary-registry-complete.md`

## User stories addressed

- User story 3
- User story 65
