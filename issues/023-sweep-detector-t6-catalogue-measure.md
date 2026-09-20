# 023 — Sweep detector R1–R4, gate T6, catalogue measure script

## Type

HITL — needs new packages: `numpy` for the detector and `librosa` (or `numpy` plus ffmpeg only) for measuring duration, bpm, key and energy of catalogue files. The operator approves; then this ticket becomes AFK. `numpy` is reused by 031 for the lip-sync cross-correlation.

## Parent PRD

`issues/prd.md`

## What to build

The taste rule that stays hard code. The detector runs R1–R4 on every SFX file at seed time and on the SFX stem at render time; any hit fails T6 and names the cue. The measure script fills `duration_s`, `bpm`, `key` and `energy` for every catalogue entry so tags are the only hand-written fields.

Covers PRD `sound` (detector), `qa.technical` T6. Decisions 7.2, 7.3, 10.1.

## Acceptance criteria

- [ ] `sound.sweep.detect(path) -> list[Hit]` implements R1 spectral flatness > 0.03 sustained > 0.45 s, R2 crescendo ≥ 200 ms rising ≥ 8 dB in ≤ 3 dB steps, R3 cue > 5 s, R4 attack > 150 ms from −20 dB to peak; each hit carries the rule and the time.
- [ ] `python -m shortsmith.sound.seed check` runs the detector on every catalogue SFX and fails with the file and rule on any hit; `python -m shortsmith.sound.seed measure` writes duration, bpm, key and energy into the catalogue.
- [ ] T6 in `qa.technical` runs the detector on `work/stems/sfx.wav` and maps a hit time to the cue at that time, naming it in the failure.
- [ ] Boundary tests: R1–R4 each with a synthesized offender and a clean file (conftest generates a white-noise sweep, a linear crescendo, a 5.1 s tone, a slow-attack tone, and clean short clicks).
- [ ] Smoke's synthesized SFX pass the detector; T6 passes.

## Blocked by

- Blocked by `issues/022-sound-director-core-mix-graph.md`

## User stories addressed

- User story 30
- User story 44
- User story 63
