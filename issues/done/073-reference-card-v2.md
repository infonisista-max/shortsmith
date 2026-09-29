# 073 — Reference card v2: the script, its story parts, the music in each part, and a beat table of what was said and what was shown

## Type

AFK — no new packages. The live re-analysis of the 12 references is an operator step
(the afk run has `.env` parked and no network).

## Parent PRD

`issues/prd.md`

## What to build

Operator, grill on learning from references (29 Sep 2026): the system must really learn
from the reference shorts and be designed to match them, not only be graded against them.
Today it has learned once, by hand. The v1 inventories (036,
`docs/reference/inventory/*.json`) became three style specs (059) and four effect
families (060–063). No job reads an inventory. Sound was barely learned: one mood
sentence per short and a count of effect kinds. The inventory never records the words
spoken over a shot, so it cannot teach "the picture matches what I say".

This ticket makes the card that the rest of this work reads: prompt
`reference/prompts/inventory_v2.md`, a v2 schema, and the closed vocabularies the
planner and the sound director will share.

Operator decisions (grill, 29 Sep 2026):

- **What learning produces**, in this order: (3) a sound vocabulary, (2) worked examples
  for the planner, and later (1) style numbers drafted by code when new URLs are added.
  Plus (4): our own output goes through the same tool so the two compare by numbers
  (074).
- **The music choice is learned from the script, not only the topic.** The card records
  what the script is about, its tone, its story parts, which music mood plays in each
  part, and where and how the music changes.
- **Learn techniques, never content** (036 stands): nothing is downloaded, and the
  "said" column is a short gist, never a transcript.

### The v2 card (every field ESTIMATED, as in v1)

Everything in v1 stays. Added:

- **`script`**: `about` (one sentence), `topic` (from the closed topic list below),
  `tone` (1–3 words, free text), `language`.
- **`parts`**: the story parts in order, `hook | build_up | reveal | ending`, each with
  `start_s`, `end_s`, `music_mood` (from the closed mood list) and optional
  `music_flavour`.
- **`music_changes`**: each point where the bed changes, with `at_s`, `from_part`,
  `to_part`, and `how`: `crossfade | hard_cut | drop_to_silence`. An empty list means one
  bed throughout.
- **`beats`**: one row per shot, holding:
  - `start_s` and `end_s`;
  - `said`: a gist of the spoken words, at most 12 words, in English even for a Hindi
    short;
  - `shows`: what the picture literally depicts;
  - `match`: `literal | named_entity | number | illustrative | metaphor`;
  - `part`: the story part;
  - the layout, the effect (registry name or `unregistered`) and the sound (sfx kind or
    none).
- **For each sound effect**, beside v1's time, kind and `synced_to`:
  - `event`: the visible event it sits on, in our terms (`text_pop`, `sticker`,
    `bubble`, `flash`, `cut`, `stamp`, `reveal`, `other`);
  - `loudness`: `soft | medium | loud` against the voice;
  - `length_s`.
- **For each effect**, beside v1's fields, a `motion` object: entrance
  (`pop_overshoot | slide | fade | wipe | draw | scale | other`), entrance duration,
  size as a share of the frame width, and screen region. This is the data 083 builds
  later effects from.
- **`styles`**: the shipped style names this reference informs, filled from the trace
  table in `styles/README.md`. An operator flag `--style` sets it for a new link.

### Closed vocabularies (data files, validated at startup)

- `assets/audio/moods.yaml`: the bed moods and regional flavours, each with a one-line
  meaning.
  - Moods: `tense_dramatic`, `investigative_pulse`, `mysterious_curiosity`,
    `calm_ambient`, `eerie_scifi`, `upbeat_electronic`, `energetic_beat`.
  - Flavours: `middle_east`, `indian`, `east_asian`, `european`.
  - The first batch the library will carry (075) is marked `active`: the first four
    moods, plus `middle_east` and `indian`.
- `assets/reference/topics.yaml`: `history`, `geopolitics`, `science`, `business`,
  `tech`, `society`, `sport` and `other`, each with English and Hindi keywords (077
  counts them).

### The tool

- `python -m shortsmith.reference inventory <url> [--style s] [--topic t]` writes a v2
  card. `--prompt v1` stays possible. Cards carry `prompt_version`.
- A loader reads v1 and v2 cards side by side. A v1 card simply has no v2 fields, and
  every reader of v2 fields skips it with a log line.
- `reference gaps` keeps working on both versions.
- Code checks every closed-list label (mood, flavour, topic, part, match, event,
  `how`). An unknown label is retried once like a malformed answer, then the reference
  stops with one message naming the field. No partial JSON is written.

## Acceptance criteria

- [ ] A recorded v2 answer fixture (written by hand from `S5j-2CWYYwM`'s v1 card plus
      plausible v2 fields, no network) parses into the v2 model. The six v1 cards still
      load unchanged.
- [ ] An unknown mood, topic or `how` is retried once, then fails naming the field.
- [ ] `said` longer than 12 words is refused at parse time.
- [ ] `moods.yaml` and `topics.yaml` load at startup; a duplicate or empty entry is
      refused naming it.
- [ ] The prompt `inventory_v2.md` lists the closed vocabularies from the data files
      (not copied into the prompt by hand). A snapshot test pins it.
- [ ] `FakeAnalyser` serves the v2 fixture; tests never reach the network.
- [ ] Operator step, in the done note: the exact command to re-analyse the 12 with v2
      (`uv run python -m shortsmith.reference inventory --all`, with `.env` back),
      the expected token cost (about 12 × 30k, YouTube input free in the preview), and
      what to eyeball in two cards (parts, music changes, five beat rows).
- [ ] Ruff, pyright and every test file are green in foreground chunks.

## Done (29 Sep 2026, afk session)

All boxes above are met in code and tests; the live re-analysis is the operator step
below.

- **The card.** `InventoryAnswerV2` (v1's fields plus `script`, `parts`,
  `music_changes`, `beats`; `motion` on each effect; `event`, `loudness`, `length_s` on
  each sound effect) and `ReferenceInventoryV2` (plus `styles`) in
  `src/shortsmith/reference/__init__.py`. `load_card` reads each JSON as its own version
  (by `prompt_version`); `gaps.load_all` uses it, and the committed `GAPS.md` is
  byte-for-byte what the loader reproduces (pinned by a test). `v2_cards(cards, log=...)`
  is the one door for 074-077: a v1 card is skipped with
  `<id>: a v1 card has no v2 fields; skipped`.
- **Closed lists.** In code (schema literals, so pydantic refuses them): part, match,
  event, loudness, `how`, entrance, region. In data (`src/shortsmith/vocab.py`):
  `assets/audio/moods.yaml` (7 moods, 4 flavours; `active` on the first four moods,
  `middle_east`, `indian`) and `assets/reference/topics.yaml` (8 topics, `en` and `hi`
  keywords, Devanagari and romanised; `other` is the keyword-less fallback). Both load in
  `app.create_app` and before any reference request; a duplicate key (a custom YAML
  loader, since PyYAML silently keeps the last), an empty entry, a blank meaning or a
  topic missing a language is a `VocabError` naming it.
- **Checks.** An unknown mood, flavour or topic is an `AnswerInvalid` line naming the
  field (`parts.0.music_mood: 'jazzy_lounge' is not a mood in moods.yaml (...)`), so the
  existing one retry applies, then `ReferenceError` naming the field, nothing written.
  `said` over 12 words is a field validator (twelve passes). A beat's `effect` is
  labelled against the registry like a component.
- **Decisions of mine, for the operator to overrule:** `music_mood` may be null (no
  music in that part); `motion.size` is 0-1 of the frame width; `region` is
  `top | middle | bottom | left | right | full`; `--topic` replaces the model's topic;
  `--style` is repeatable and must name a file in `styles/`; without it the styles come
  from the trace table rows in `styles/README.md` that name the video.
- **Prompt.** `prompts/inventory_v2.md`; moods, flavours and topics are substituted from
  the data files (a test proves an edited `moods.yaml` reaches the prompt and the
  parser, and that no name is written into the template). Snapshot:
  `tests/fixtures/reference/inventory_v2.snapshot.md`, built with a fixed six-name
  registry and `tests/fixtures/reference/components.md` so a new component does not move
  it; re-record with `SHORTSMITH_UPDATE_SNAPSHOTS=1`.
- **CLI.** `inventory <url> [--style s] [--topic t] [--prompt v1|v2]`; v2 is the default.
  The v1 tests in `tests/test_reference.py` now pass `version="v1"` / `--prompt v1`.
- **Fixture.** `tests/fixtures/gemini/inventory_v2.json`: S5j's v1 card with
  hand-written parts (hook / build_up / reveal / ending, moods
  mysterious_curiosity -> eerie_scifi -> tense_dramatic -> calm_ambient), three music
  changes, 24 beat gists and motion/sfx detail. Plausible, not observed.

### Operator step (needs `.env` back and network)

    uv run python -m shortsmith.reference inventory --all
    uv run python -m shortsmith.reference gaps

This overwrites the 12 v1 cards under `docs/reference/inventory/` with v2 cards (git
keeps the v1 ones). Expected cost: about 12 x 30-35k tokens (the v1 run was about 30k
each; v2's longer prompt and answer add a few thousand), YouTube URL input free in the
preview. Every request logs its tokens.

Eyeball two cards, `S5j-2CWYYwM` (Hindi, Dhruv) and `FbaBcWgMIEY` (vishva, yours):

- `parts`: four or fewer, in order, covering the runtime; does each `music_mood` match
  what you hear?
- `music_changes`: at the moments the bed really changes, with the right `how` (or
  empty when one bed plays throughout).
- five `beats` rows: is `said` a gist in English (never a transcript, at most 12 words),
  is `shows` what is literally on screen, and is `match` fair?

If a card fails its closed-list check twice, the log names the field; re-run that one
link.

## Blocked by

- Nothing.

## User stories addressed

- Operator, 22 Sep 2026: the system must learn from the references and be designed to
  match them, not only be graded against them.
- Operator, 29 Sep 2026 (grill): learn the music choice from the references' scripts,
  their story parts and where the music changes.
