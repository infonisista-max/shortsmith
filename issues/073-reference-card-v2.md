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

## Blocked by

- Nothing.

## User stories addressed

- Operator, 22 Sep 2026: the system must learn from the references and be designed to
  match them, not only be graded against them.
- Operator, 29 Sep 2026 (grill): learn the music choice from the references' scripts,
  their story parts and where the music changes.
