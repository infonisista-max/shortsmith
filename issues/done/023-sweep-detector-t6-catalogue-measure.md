# 023 — Sweep detector R1–R4, gate T6, catalogue measure script

## Type

AFK — was HITL for its packages. The operator approved the numpy + ffmpeg route (no librosa) on 2026-09-25 and installed `numpy>=2,<3` (2.5.3) themselves; ffmpeg decodes, numpy measures. `numpy` is reused by 031 for the lip-sync cross-correlation.

## Parent PRD

`issues/prd.md`

## What to build

The taste rule that stays hard code. The detector runs R1–R4 on every SFX file at seed time and on the SFX stem at render time; any hit fails T6 and names the cue. The measure script fills `duration_s`, `bpm`, `key` and `energy` for every catalogue entry so tags are the only hand-written fields.

Covers PRD `sound` (detector), `qa.technical` T6. Decisions 7.2, 7.3, 10.1.

## Acceptance criteria

- [x] `sound.sweep.detect(path) -> list[Hit]` implements R1 spectral flatness > 0.03 sustained > 0.45 s, R2 crescendo ≥ 200 ms rising ≥ 8 dB in ≤ 3 dB steps, R3 cue > 5 s, R4 attack > 150 ms from −20 dB to peak; each hit carries the rule and the time.
- [x] `python -m shortsmith.sound.seed check` runs the detector on every catalogue SFX and fails with the file and rule on any hit; `python -m shortsmith.sound.seed measure` writes duration, bpm, key and energy into the catalogue.
- [x] T6 in `qa.technical` runs the detector on `work/stems/sfx.wav` and maps a hit time to the cue at that time, naming it in the failure.
- [x] Boundary tests: R1–R4 each with a synthesized offender and a clean file (conftest generates a white-noise sweep, a linear crescendo, a 5.1 s tone, a slow-attack tone, and clean short clicks).
- [x] Smoke's synthesized SFX pass the detector; T6 passes.

## Status (2026-09-25): done

All acceptance criteria met. ruff clean, pyright 0 errors, pytest 1019 passed on the
committed tree; smoke ok, `out/qa.json` T1 T2 T3 T4 T6 T8 T9 pass, T6 "R1-R4 clean on the
SFX stem (2 cues)".

Follow-up: on the mixed SFX stem, R3/R4 split sounds by silence, so cues whose tails run
together read as one sound and can fail T6 falsely (measured: chained 2 s ringing tails
read as one 7.5 s sound; overlapping cues read as a 0.40 s / 1.00 s "attack"). It fails
loudly at QA and seed-time single files are unaffected, so the operator shipped 023 as it
stands. The per-cue segmentation, with the failure naming the real cue, is
`issues/050-t6-segment-stem-by-cue-sheet.md`, which blocks 025.

## Blocked by

- Blocked by `issues/022-sound-director-core-mix-graph.md`

## User stories addressed

- User story 30
- User story 44
- User story 63
