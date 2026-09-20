# 016 — Asset step with fake source, fallback ladder, aspect classification, rights log, credits, T9, card/photo look

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The `sourcing` step end to end with only the fake image source: the `ImageSource` interface and `FakeImageSource`, the fallback ladder applied in code with the rung recorded per beat, the source rules per subject kind, aspect classification from real dimensions into full-bleed photo or card with downgrades recorded, per-job caching by hash, the rights log with one row per unique asset, derived `credits.md` and the AI-disclosure line, and gate T9. The Remotion `photo` and `card` components render the full 4.1 look: Ken Burns 1.10→1.16 with alternating direction, framed archival card with white 14 px border, −1.5° rotation, blurred darkened cover, caption strip, push 1.45→2.1 and optional red ring. The contact sheet marks rescued and downgraded beats and shows the asset-origin letter.

Covers PRD `assets` (interface, ladder, classification, cache, manifest), `rights`, `qa.technical` T9, render `photo`/`card`, contact sheet marks. Decisions 4.1, 4.2, 4.3, 4.4, 5.1, 5.3, 5.4, 5.6, 10.1, 10.4, 12.1.

## Acceptance criteria

- [ ] `assets.ImageSource` interface with `search(query, n) -> list[Candidate]`; `FakeImageSource` writes solid PNGs at requested sizes with fake URLs and has a "nothing found" mode; the source order is a config list (`ASSET_SOURCES`) and `ASSET_POLICY=rights_safe` removes `web` from it.
- [ ] `assets.source_assets(validated_plan, references, policy) -> AssetManifest` honours `source_intent` (`reuse` always, `generate` only on concept beats, entity beats always search first), prefers owner references for beats whose query matches a reference caption, refuses sources the subject kind forbids, and applies the ladder: query, `query_fallback`, generate (no-op until 019 / `IMAGE_GEN=none`), re-dressed reuse of the nearest earlier same-kind asset with a new crop and stamp, presenter PIP over gradient with stamp; `asset.fallback_rung` 0–4 recorded per beat; never a blank beat.
- [ ] More than four rescued beats (rung ≥ 3) per 60 s fails the technical gate with "not enough relevant B-roll" (new check inside T8's family; final numbering in 032).
- [ ] Classification by real dimensions: portrait and ≥ 1080 px wide after ≤ 1.5x upscale → `photo`; otherwise `card` at native aspect, width min(980, 650 × aspect), blurred darkened cover; planner `photo` on a non-qualifying asset → `card` with `treatment_downgraded: true`.
- [ ] Per-job cache `work/assets/` keyed by sha256(query + source); re-running the step fetches nothing (fake source counts calls).
- [ ] `rights.write(job, manifest)` writes `out/rights.json` rows in the 5.4 shape; `credits.md` with one line per non-owner, non-generated asset and the disclosure line when any row is generated; both regenerated, never hand-edited.
- [ ] T9 in `qa.technical`: every beat's asset id has a row; every row has `source_url` or origin `owner_supplied|generated`; every generated row has a prompt; `depicts: named_entity` with `render: photoreal` fails; `scene` with `photoreal` passes.
- [ ] Remotion `photo` and `card` components per 4.1 and 5.3, registered; cards end above y 1240.
- [ ] `delivered` now also requires `rights.json` and `credits.md`.
- [ ] Contact sheet strip line shows beat id, mode letter, kind, origin letter and a red corner mark on rescued or downgraded beats.
- [ ] Boundary tests, `tests/test_assets.py` and `tests/test_rights.py`: each rung reached in order, re-dress on reuse differs in crop, fifth rescue fails, 1079 px portrait becomes a card, missing prompt on generated fails T9, named entity plus photoreal fails, scene plus photoreal passes.
- [ ] Smoke: FakePlanner's plan sources every beat through the fake, T1–T4 and T9 pass, `delivered`.

## Blocked by

- Blocked by `issues/006-t1-t4-contact-sheet-delivered.md`
- Blocked by `issues/009-grammar-validator.md`

## User stories addressed

- User story 6
- User story 15
- User story 17
- User story 20
- User story 21
- User story 22
- User story 33
- User story 34
- User story 35
- User story 43
