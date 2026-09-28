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

- [x] All seven style specs carry `speech_band_margin_db: 12` and a bumped `version`; a
      test asserts every shipped style carries 12.
- [x] A mix whose speech band clears the bed by 12.5 dB keeps the bed with no repair; one
      at 11.0 dB enters the 056 ladder in the same order as today. Tests that assumed 20
      are updated to the style's number, never loosened in what they check.
- [x] Smoke explainer, hitech, footage, vishva and fastfacts pass T1–T13.
- [x] Ruff, pyright, every test file green in foreground chunks (and `npm run typecheck`,
      `npm test` if anything under `src/remotion/` changed).
- [x] Done note: the amendment line for 7.3 for the operator to paste, and what to listen
      for on run04 (voice clear over the music on the phone; `job.log` `sound:` lines show
      whether any repair ran).

## Done note (28 Sep 2026, AFK session)

**Amendment line for 7.3 (for the operator to paste into `docs/grill-decisions.md`):**

> 7.3 amended by 064 (paired review 28 Sep 2026, option A): the speech-band margin is
> 12 dB, not 20 dB, in every style (`sound.speech_band_margin_db: 12`). It is measured
> the same way (voice vs the un-ducked music stem, 250–4000 Hz), and the 056 repair
> ladder (dip, lower bed, next bed, voice and hits) still runs, in the same order,
> whenever a bed misses the line.

**What changed**
- `speech_band_margin_db: 20 -> 12` in all seven specs; versions bumped: explainer
  11 -> 12, educational/animated/hitech 10 -> 11, footage/vishva/fastfacts 1 -> 2.
- `sound.margin_problem(margin_db, nums)`: the pass/miss rule taken out of `_balance`
  so it can be tested alone. The behaviour is unchanged, and the line is read from the
  spec.
- `tests/test_speech_band_margin.py`: all seven styles carry 12 plus the new versions;
  12.5 dB passes and 11.0 dB misses in every style; with the mix stubbed, 12.5 dB keeps
  the bed and never re-mixes, and 11.0 dB logs the miss, then dips (2 dB first), and
  lowers the bed only after every dip fails.
- `tests/test_sound.py`: the 056 synthetic beds were tuned to miss 20 dB. At 12 dB
  they passed without a repair, so they were rebuilt to miss the new line with the same
  checks. Any steady tone levelled on its median clears about 14 dB on the fixture
  voice, so both beds now swell in the band one second in three (1 s median windows).
  MELODIC: 8.5 dB plain, and one 5 dB dip brings it to 12.7 dB. PURE: 1.1 dB plain,
  and the dips and the lower bed can't save it.
- Version pins in `test_styles.py` and `test_recipe_styles.py` updated.

**Run04: what to listen for**
- On the phone: the voice sits clearly on top of the music the whole way through. The
  music should sit at about the level you asked for after run03 ("30 % quieter").
- In `job.log`, the `sound:` lines. `bed <id> misses the 7.3 band` followed by
  `dipped by N dB` / `lowered to` / `trying the next bed` means a repair ran. No such
  line means the bed passed as planned. `work/stems/balance.json` has the measured
  `speech_band_margin_db` beside `speech_band_margin_min_db: 12`.

## Blocked by

- Nothing.

## User stories addressed

- Operator, 27 Sep 2026 (run03): "music okay but loud"; 30 % quieter.
- Operator, 27 Sep 2026 (054): music always present.
