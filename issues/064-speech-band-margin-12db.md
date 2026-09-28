# 064 — Speech-band margin 12 dB in every style: the music stays at the level the operator asked for

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Every style sets `sound.speech_band_margin_db: 20`: the voice must clear the music bed by
20 dB in the speech band (250–4000 Hz), or 056's repair ladder runs and, if no rung
reaches the line, the short ships with voice and hits only. 056's done note, run03's own
stems by hand: at the new −14 dB bed the plain mix cleared the band by 11.9 dB; after the
dip, the lowering and the next-bed search the best was 14.0 dB, so the bed was dropped.
The operator's ear on run03 (9.4 dB at the old −11 dB bed) was "music okay but loud", and
he asked for 30 % quieter — the 11.9 dB level. The 20 dB line is stricter than his ear and
would leave most melodic beds out, against 054 ("music always present").

Operator decision, paired review 28 Sep 2026 (option A; amends 7.3; the operator records
the line from the done note): `speech_band_margin_db: 12` in all seven styles —
explainer, educational, animated, hitech, footage, vishva, fastfacts. The margin is still
measured the same way (un-ducked music stem); the repair ladder and its order are
unchanged and still run whenever a bed misses the line. Only the number moves.

## Acceptance criteria

- [ ] All seven style specs carry `speech_band_margin_db: 12` and a bumped `version`; a
      test asserts every shipped style carries 12.
- [ ] A mix whose speech band clears the bed by 12.5 dB keeps the bed with no repair; one
      at 11.0 dB enters the 056 ladder in the same order as today. Tests that assumed 20
      are updated to the style's number, never loosened in what they check.
- [ ] Smoke explainer, hitech, footage, vishva and fastfacts pass T1–T13.
- [ ] Ruff, pyright, every test file green in foreground chunks (and `npm run typecheck`,
      `npm test` if anything under `src/remotion/` changed).
- [ ] Done note: the amendment line for 7.3 for the operator to paste, and what to listen
      for on run04 (voice clear over the music on the phone; `job.log` `sound:` lines show
      whether any repair ran).

## Blocked by

- Nothing.

## User stories addressed

- Operator, 27 Sep 2026 (run03): "music okay but loud"; 30 % quieter.
- Operator, 27 Sep 2026 (054): music always present.
