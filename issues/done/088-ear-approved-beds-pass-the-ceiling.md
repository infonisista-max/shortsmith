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

- [x] Director test with a fake library: an approved bed whose margin is over the ceiling
      plays, with the note in `balance.json` and on the job page. The same bed as an unheard
      Freesound fallback is refused and the director walks on, exactly as 069 does.
- [x] Shortlist test (recorded fixtures, no network): a drop-folder bed over the ceiling
      reaches the page with the note, margin and level. A bed under the floor is skipped as
      today.
- [x] The page's under-the-voice preview plays (app test on the served file). It is built
      with the level the mix uses, and it is never written into the catalogue.
- [x] All seven styles have the new comment and a bumped version, with pins updated.
- [x] Tests never reach the network. Ruff, pyright and every test file are green in
      foreground chunks. The smoke passes T1–T13 on explainer, vishva and fastfacts.

### Operator step, in the done note

Re-run
`uv run python -m shortsmith.sound.shortlist --slot investigative_pulse --voice work/089/run04_voice.wav`
(run04's own `work/` goes on the next sweep).
Trap Hamza should now reach the page. Listen under the voice and say yes or no. Then
continue with 087's operator step 2 (the facts-default pass).

## Done (afk, 30 Sep 2026)

**Which entries count as heard.** Every entry of the tracked `assets/audio/catalog.yaml`:
today 30 (14 beds, 16 effects), all added by the operator's yes on `/audio/shortlist` on
29 Sep 2026 (commit 38c478d). No new mark was added, because the tracked catalogue already
is the mark. `shortlist.approve` is the only thing that writes it. The runtime search
writes only to `fetched/catalog.yaml`, and 068's `seed retag` works on that fetched file.
So no seeded entry without approval sits in the tracked file. Unheard: every
`fetched/` entry (the runtime Freesound fallback and any `retag` survivor). The director
takes the set as `approved_beds(library)` before any search adds a bed. A score is heard
only when every bed in it is in that set.

**Director.** On a heard score, a margin over `speech_band_margin_max_db` is not a
problem. It becomes a line in `BalanceReport.notes` (new, empty by default, so older
`balance.json` files load): "... over sound.speech_band_margin_max_db 20 dB: may be hard to
hear on a phone speaker; approved by ear, so it plays". The same holds per window across a
bed change. The repair ladder never walks away from a heard bed for the ceiling, and never
takes the dip off because of it. An unheard bed keeps 069 exactly as before. The floor is
unchanged for every bed. The job page gets each note once as `sound: <note>`, and the
critic's balance text lists it as `note:`.

**Shortlist.** Over the ceiling, a candidate (API or drop folder) is kept with `note`,
`margin_db` and `level_db` (the level it was measured at, `bed_db_under_voice`). Under the
floor it is still skipped. With a 12 dB floor and the bed levelled on its full-band mean,
an all-in-band bed clears the band by 14.1 dB against the reference voice. So the floor
test raises the floor on a copied style.

**Under-the-voice preview (built; the page did not have it).** Every bed candidate gets
`<file>.under_voice.wav` beside it in `work/shortlist/<slot>/`. It is the levelled bed
(same gain as the check), ducked by the 7.3 sidechain under the reference voice, summed
with the voice, and as long as the voice. The card plays it as a second player, "under the
voice, at the level the mix uses". A yes copies only the bed file, so the preview never
reaches `beds/` or `catalog.yaml`. `_nearest` removes a dropped facts-default candidate's
preview with its file.

**Styles.** The value stays at 20 dB. The comment in all seven now reads: "069, 088:
screens unheard beds only (runtime fallbacks); an ear-approved bed over it plays with a
note. Set from run04's bed, freesound_557546, a car exhaust, not music; 089 re-derives it".
Versions: explainer 20, educational 18, animated 18, hitech 19, footage/vishva/fastfacts 10.
The pins in test_bed_audible, test_speech_band_margin, test_styles and test_recipe_styles
are updated.

**Tests that changed meaning.** 069's director walk now runs on two `fetched/` beds. 087's
"facts default still goes through 069" became "the facts default is an approved bed, so
069's ceiling is a note". The facts-default shortlist now ranks the drone bed too.

### Operator step

Re-run
`uv run python -m shortsmith.sound.shortlist --slot investigative_pulse --voice work/089/run04_voice.wav`.
Trap Hamza should now reach `/audio/shortlist` with the note, its margin (25.4 dB at -14
was the last reading) and a second player under run04's voice. Listen under the voice and
say yes or no. Then continue with 087's operator step 2 (the facts-default pass).

## Blocked by

None - can start immediately.

## User stories addressed

- Operator, 30 Sep 2026: "the level should follow my ear and the references, not a number
  I choose; a bed I approved by ear must not be refused by the check."
