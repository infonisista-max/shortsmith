# 068 — The audio catalogue tells the truth: a fetched sound keeps its own name and tags, and is adopted only when they fit what it is for

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Run04 (job `20260928-140620-f774e1`, King Saud, vishva): on the operator's phone there was
no music, and a phone ring came out of nowhere. Both come from one fault. The Freesound
adapter adopts the first search hit without looking at what it is. Then it catalogues the
hit under the words it was searched with, and throws away the name and tags Freesound
returned (`freesound.py:357`, `tags=AudioTags(theme=list(theme), mood=list(mood),
intent=[intent])`).

The real names (read back from the Freesound API on 29 Sep 2026) against what
`assets/audio/fetched/catalog.yaml` says:

| id | catalogued as | really is (Freesound name, tags) |
|---|---|---|
| 557546 | bed: history documentary / regal intriguing eastern oud | "buick regal gs_magnaflow.mp3", buick, mufflers, a car's exhaust (matched the query 'regal') |
| 738836 | bed: middle eastern history oud / regal mysterious | "A cappella - Arabian nights", acappella, chant, choir, male voice |
| 253546 | sfx `tally_ding` | "SCORE COUNT.wav", beep, ding, score, a 1.46 s trill of beeps every 70 ms at ~3.2 kHz: the "phone ring" at 23.40 s |
| 249931 | sfx `changeover` | "pressing a light toggle switch", buzzer |
| 210316 | sfx `date_stamp` | "stamp coffee machine upwards", a coffee-machine lever |
| 118338 | sfx `question_tick` | "Tick-Tock", a 2 s clock loop |
| 63523 | sfx `money` | "money4.wav", a coin spinning on a table |

The catalogue is now wrong in a way the next job will act on. Once the bed score is fixed
(069), a query for "eastern oud" would pick the car exhaust on purpose.

Operator decision (run04 QA, 29 Sep 2026): never adopt a search's first hit blindly. A
sound is used only when its own Freesound name and tags match the kind it is fetched for.
The existing fetched catalogue is re-tagged from Freesound, not wiped.

- **Keep the truth.** `AudioCandidate` already carries the Freesound `name` and `tags`.
  `AudioEntry` gains `source_name` and `source_tags`, filled on adoption and written to
  the catalogue. The planner-facing `theme` / `mood` / `intent` tags are derived from
  `source_tags` (plus the kind the sound was checked against), never copied from the
  query.
- **Check before adopting.** A tracked data file, `assets/audio/kinds.yaml`, gives each
  audio kind the words that must appear in the sound's name or tags (at least one) and
  the words that must not (none).
  - bed: needs a music word (music, loop, ambient, soundtrack, instrumental, …). It must
    not carry vocal words (vocal, voice, chant, choir, acappella, singing, …) or
    field-recording words (car, engine, muffler, traffic, …). README: "no vocals".
  - Every SFX kind in 070's palette gets its own lists. Ring, phone, bell, chime, alarm,
    beep, buzzer, ringtone and siren are forbidden for every SFX kind (operator: "no
    rings, bells or chimes").

  `FreesoundAudioSearch._first_adopted` checks the kind before any download. A miss
  costs one candidate and leaves a note: `skipped: name/tags 'buick, mufflers' carry no
  music word`. The lists are data, not code, and the loader validates the file at
  startup.
- **Re-tag what is already there.** A command, `uv run python -m shortsmith.sound.seed
  retag`, reads every `fetched/` entry back from the Freesound API by id. It stores
  `source_name` and `source_tags` and re-derives the tags. It removes every entry, and
  its file, that fails the checks for its kind, and prints one line per entry kept or
  removed. It runs against the git-ignored `fetched/` catalogue only, never the tracked
  one. It needs `FREESOUND_API_KEY`; without one it says so and changes nothing.
- The fake search (`FakeAudioSearch`) applies the same check to its shelf, so tests show
  a mislabelled shelf entry being refused.

## Acceptance criteria

- [ ] Using run04's seven Freesound answers above (copied into a test as JSON; no
      media), adoption refuses 557546 and 738836 as beds, and refuses 253546 and 249931
      for every SFX kind. The notes name the offending words.
- [ ] An adopted entry's catalogue row carries `source_name` and `source_tags` exactly
      as Freesound returned them. Its `theme` / `mood` / `intent` never contain a word
      that is only in the query.
- [ ] `assets/audio/kinds.yaml` is loaded and validated at startup. A kind with no
      required words, or a word in both lists, is refused with a message naming it.
- [ ] `seed retag` against an `httpx.MockTransport` serving the run04 answers keeps the
      good entries (e.g. 669855 snare, 115525 bass stab) and removes 557546, 738836,
      253546 and 249931 with their files. It never touches `assets/audio/catalog.yaml`.
- [ ] Operator step (the afk run has `.env` parked and no network, so it does not run
      this): the done note gives the exact command for the operator to run with `.env`
      back in place (`uv run python -m shortsmith.sound.seed retag`), and what its
      output should show (557546, 738836, 253546 and 249931 removed).
- [ ] Ruff, pyright and every test file are green in foreground chunks. No test reaches
      the network.
- [ ] Done note: the amendment line for 7.2 (adoption checks name and tags against the
      kind; the catalogue keeps Freesound's own name and tags) for the operator to
      paste.

## Blocked by

- Nothing.

## Done (29 Sep 2026)

- `assets/audio/kinds.yaml` (tracked) + `sound/kinds.py`: `bed` needs a music word and
  forbids vocal and field-recording words; the SFX kinds are 070's palette (tick, whoosh,
  drum, bass, thump, ding) plus today's `changeover`, and all of them also forbid
  `sfx_forbids` (ring, ringing, phone, telephone, bell, chime, alarm, beep, buzzer,
  ringtone, siren). Tokens match as written or with a plural s/es (`mufflers`). A planner
  intent the file does not name (`date_stamp`) needs its own words and carries the SFX
  forbidden list, until 070 closes the palette. Loaded at startup in `app.create_app`
  (`audio_kinds=`); no `needs`, a word in both lists, or no `bed` is a `KindError` naming it.
- `FreesoundAudioSearch._first_adopted` checks each hit's own name/tags before the
  catalogue lookup and before any download, so a mislabelled entry already in `fetched/`
  is not reused either. The note reads e.g. `skipped: name/tags carry 'mufflers',
  forbidden for bed`.
- `AudioEntry.source_name` / `source_tags` are written on adoption. Tags come from
  `freesound.derived_tags`: a bed's theme is its own tags (lower-cased), and its mood is
  the query's mood words that Freesound also tagged. A cue carries the intent it was
  checked against. `adopt()` lost its `theme` parameter.
- `FakeAudioSearch` applies the same check to shelf entries that carry a `source_name`.
  Hand-seeded entries (no source name) keep their operator tags.
- `uv run python -m shortsmith.sound.seed retag` (`freesound.retag`) works only on
  `fetched/catalog.yaml`. If any id cannot be read back, nothing is written or removed
  (exit 1). Without a key it prints `FREESOUND_API_KEY is not set in .env: nothing
  changed` and exits 1.
- Tests: `tests/test_audio_kinds.py` uses the recorded run04 answers in
  `tests/fixtures/freesound/run04_sounds.json`. Five `test_freesound.py` tests now give
  their hits kind words, and bed tags are asserted from the source rather than the query.

**Operator step** (with `.env` back in place and network):

    uv run python -m shortsmith.sound.seed retag

You should see `freesound_557546: removed`, `freesound_738836: removed`,
`freesound_253546: removed` and `freesound_249931: removed`, each with the offending
words, then `kept as ...` for 669855, 115525, 339437, 118338, 210316 and 63523, and a
last line `6 kept, 4 removed from fetched/catalog.yaml`. The four files are deleted from
`assets/audio/fetched/`. The tracked `catalog.yaml` is not touched.

**Amendment line for 7.2** (for the operator to paste): "A fetched sound is adopted only
when its own source name and tags fit the kind it is fetched for (`assets/audio/kinds.yaml`:
a bed needs a music word and has no vocals or field recording; no SFX is a ring, phone,
bell, chime, alarm, beep, buzzer, ringtone or siren). The catalogue keeps the source's own
name and tags (`source_name`, `source_tags`), and the planner-facing tags are derived from
them, never from the query (068)."

## User stories addressed

- Operator, run04 QA (29 Sep 2026): "I heard no background music."
- Operator, run04 QA (29 Sep 2026): "Once a telephone-ring sound came out of nowhere."
- Operator, 29 Sep 2026: "never adopt a search's first hit blindly — check the sound's
  own Freesound name/tags match the kind before using it."
