# 050 — T6: segment the SFX stem by the cue sheet, and name the real cue

## Type

AFK — no new packages (`numpy` is already in from 023).

## Parent PRD

`issues/prd.md`

## What to build

On the mixed SFX stem, the 023 detector splits sounds by silence (under −60 dBFS for 50 ms or more). Cues whose tails run together therefore read as one sound, and R3 and R4 misfire on the merged span. The operator's question on 2026-09-25 found this, and a synthetic stem confirmed it:

- five 2 s ringing cues 1.5 s apart read as one 7.5 s sound → false R3;
- two overlapping cues (1.2 s together) → false R4, a 0.40 s "attack";
- a quiet cue 15 dB down, then a loud hit 1 s later → false R4, a 1.00 s "attack" measured across two cues.

The fixture's short clicks die away before the next cue, so the smoke never sees this. Real SFX with reverb tails arrive in 025.

At render time, R3 and R4 must run per cue: each cue's slice of the stem runs from its `start_s` to the earlier of its `end_s` and the next cue's `start_s`, taken from `work/stems/cues.json`. R1 and R2 keep reading the whole stem frame by frame. Seed-time checks of single files (`python -m shortsmith.sound.seed check`) keep splitting by silence.

The failure must name the cue that actually offends, never the merged span. A 1.00 s "attack" reported across two cues is a misleading diagnostic, the same class of bug as the grammar validator naming the wrong word. Each R3/R4 hit comes from one cue's slice and carries that cue's id, beat and intent. Its measured number (length, attack) is that cue's own. Its time lies inside that cue.

Covers PRD `sound` (detector), `qa.technical` T6. Decisions 7.3, 10.1.

## Acceptance criteria

- [ ] T6 runs R3 and R4 on per-cue slices of `work/stems/sfx.wav` cut by `work/stems/cues.json`; R1 and R2 still run on the whole stem; `seed check` behaviour is unchanged.
- [ ] Boundary tests on synthetic stems: the three cases above (chained ringing tails, two overlapping cues, a quiet cue then a loud hit) pass T6 when each cue alone is clean.
- [ ] A stem where exactly one cue offends fails T6 naming that cue's `entry_id`, `beat_id` and intent, with that cue's own measured value (e.g. its own attack, not one spanning a neighbour) and a time inside that cue's slice.
- [ ] A real offender cue (a 5.1 s tone; a 200 ms swell) inside a stem of clean cues still fails R3 / R4 respectively.
- [ ] The no-stem pass keeps its written reason; smoke still passes T6 with "R1-R4 clean on the SFX stem".

## Blocked by

- Blocked by `issues/023-sweep-detector-t6-catalogue-measure.md`

## Blocks

- Blocks `issues/025-seed-audio-library.md` — real reverb tails arrive there.

## User stories addressed

- User story 30
- User story 44
