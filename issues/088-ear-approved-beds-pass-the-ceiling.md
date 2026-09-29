# 088 — A bed the operator approved by ear is never refused by the speech-band ceiling

## Type

AFK — no network, no keys, no new packages.

## Parent PRD

`issues/prd.md`

## Why

Operator, 30 Sep 2026 (079 HITL, 087's operator step 1). Trap Hamza (Mixkit 267, the Dyson
v2 bed) was put in `assets/audio/inbox/` with its sidecar, and the shortlist for
`investigative_pulse` with run04's voice stem logged:

> inbox 'mixkit-trap-hamza-267.mp3' (mixkit) skipped: the speech band 250-4000 Hz clears
> the bed by 25.4 dB (bed level -14.0 dB under the voice), over
> sound.speech_band_margin_max_db 20 dB

That is the one bed the operator has heard clearly on a phone speaker (the Dyson v2 short).
069's ceiling is a proxy for "a phone speaker does not play this bed". It was set from
run04's bed, which was a car exhaust recording and not music (087's reconcile section).
The proxy is now refusing the thing it stands in for.

Operator's decision, recorded in 087's cap section: **no dB number is chosen by the
operator. The level follows the ear and the references. A bed approved by ear must not be
refused by the check.**

## What to build

- **The ceiling screens only beds nobody has heard.** A bed the operator said yes to on
  `/audio/shortlist` (a catalogue entry carrying that approval) never fails 069's ceiling
  in the mix. Its margin is still measured and written to `balance.json`, and the job page
  shows it as a note, not a problem. The runtime Freesound fallback bed, which no one has
  heard, keeps the ceiling exactly as today.
  - If `catalog.yaml` has no mark separating operator-approved entries from seeded ones
    (068's `seed retag` survivors), add one. The done note says which entries count as
    heard. A seeded entry without an approval counts as unheard.
- **The shortlist lets the ear decide.** Going over the ceiling no longer skips a
  candidate. The candidate reaches the listening page with a visible note ("may be hard to
  hear on a phone speaker"), its margin and the level it was measured at. The **floor**
  (the bed crowding the voice) is unchanged everywhere. The operator's rule is that the
  music never covers the voice.
- **The page plays the bed the way the viewer will hear it.** A bed candidate on
  `/audio/shortlist` gets a second player: a short preview of the bed mixed under the
  `--voice` stem (or the fixture voice) at the level the mix would use today. Then a yes
  judges the balance, not just the track. If the page already does this, nothing is built
  here and the done note says so.
- **The front-matter comment tells the truth.** `speech_band_margin_max_db` keeps its value
  in this ticket (089 re-derives it). Its comment in all seven styles changes to say that it
  screens unheard beds only, and it names the run04 confound (`freesound_557546`, a car
  exhaust). Style versions are bumped and version pins updated.

## Acceptance criteria

- [ ] Director test with a fake library: an approved bed whose margin is over the ceiling
      plays, with the note in `balance.json` and on the job page. The same bed as an unheard
      Freesound fallback is refused and the director walks on, exactly as 069 does.
- [ ] Shortlist test (recorded fixtures, no network): a drop-folder bed over the ceiling
      reaches the page with the note, margin and level. A bed under the floor is skipped as
      today.
- [ ] The page's under-the-voice preview plays (app test on the served file). It is built
      with the level the mix uses, and it is never written into the catalogue.
- [ ] All seven styles have the new comment and a bumped version, with pins updated.
- [ ] Tests never reach the network. Ruff, pyright and every test file are green in
      foreground chunks. The smoke passes T1–T13 on explainer, vishva and fastfacts.

### Operator step, in the done note

Re-run
`uv run python -m shortsmith.sound.shortlist --slot investigative_pulse --voice work/089/run04_voice.wav`
(run04's own `work/` goes on the next sweep).
Trap Hamza should now reach the page. Listen under the voice and say yes or no. Then
continue with 087's operator step 2 (the facts-default pass).

## Blocked by

None - can start immediately.

## User stories addressed

- Operator, 30 Sep 2026: "the level should follow my ear and the references, not a number
  I choose; a bed I approved by ear must not be refused by the check."
