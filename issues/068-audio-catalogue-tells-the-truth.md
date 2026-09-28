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
- [ ] Run once for real on this machine. The done note pastes its output lines.
- [ ] Ruff, pyright and every test file are green in foreground chunks. No test reaches
      the network.
- [ ] Done note: the amendment line for 7.2 (adoption checks name and tags against the
      kind; the catalogue keeps Freesound's own name and tags) for the operator to
      paste.

## Blocked by

- Nothing.

## User stories addressed

- Operator, run04 QA (29 Sep 2026): "I heard no background music."
- Operator, run04 QA (29 Sep 2026): "Once a telephone-ring sound came out of nowhere."
- Operator, 29 Sep 2026: "never adopt a search's first hit blindly — check the sound's
  own Freesound name/tags match the kind before using it."
