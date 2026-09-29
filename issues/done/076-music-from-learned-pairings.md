# 076 — Music from the learned pairings: a mood per story part, at most one change, done the way the references do it

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Operator decisions (grill, 29 Sep 2026):

- The planner picks the **mood** (and an optional **flavour**) for each story part of
  **this** script. It picks from the closed list (`assets/audio/moods.yaml`, 073), never
  in free words. It learns from the v2 cards' pairings of script, tone, story parts and
  music (073).
- **At most one bed change per short** (`sound.bed_changes_max: 1` in every style). It
  sits only on a story-part boundary, and **both beds come from the approved library**
  (075). A Freesound fallback bed never takes part in a change.
- **How the change sounds** comes from what the references do at that story point: the
  cards' `music_changes[].how` (`crossfade | hard_cut | drop_to_silence`). The planner
  picks the `how` the pairings show for that part boundary.
  - Crossfade length, silence length and hard-cut fade are front-matter numbers. The
    agent proposes starting values from the cards and names them in the done note.
- **Keep the swell/drop volume curve inside each bed** (the operator's 19 Sep
  sound-design rule; the 7.3 `envelope`).

### What to change

- **Sound-story schema.** `bed` becomes a list of 1–2 segments:
  `{part_from, mood, flavour?}`, plus `change: {at_beat, how}` when there are two. The
  grammar (7.x) checks:
  - moods and flavours from the closed list, and only `active` ones;
  - `bed_changes_max`;
  - the change on a beat boundary that is also a story-part boundary.

  The plan's story parts are a new `parts` field on the sound story (hook / build_up /
  reveal / ending with beat ranges).
- **Prompt.** The sound prompt gets a section "Music in top shorts", built by code from
  the v2 cards (one line per card: topic, tone, part → mood, change and how). It says to
  pick for this script's topic, place, period and tone. Bump the prompt version and
  record snapshots.
- **Director.**
  - Selects each segment's bed from the approved library by the closed tags: mood must
    match, a flavour match ranks first, then energy distance, then drop fit.
  - Renders the change at the planned beat with the planned `how`.
  - Applies the envelope within each bed.
  - With no approved bed for a mood, it falls back to Freesound via 069's music-anchored
    search. A fallback drops the change (one bed only), and the job page and `job.log`
    say "fallback bed: <mood>, no approved bed".
- **Balance.** Each segment passes the 7.3 balance, including 069's speech-band upper
  bound. The crossfade region is measured too.
- **Self-inventory row** (074): the plan's moods per part fill the "plan" side of the
  comparison.

## Acceptance criteria

- [x] A sound story with a non-list mood, an inactive mood, two changes, or a change off
      a part boundary fails the grammar naming it; one retry as usual.
- [x] With a fixture library of two approved beds: a two-segment plan renders both. At
      the change beat the music stem shows the planned `how`:
      - crossfade: both beds present for the crossfade length;
      - hard cut: the new bed starts within one frame;
      - drop to silence: music under −60 dB for the silence length.

      The swell/drop envelope still shapes each segment.
- [x] No approved bed for the mood → one Freesound bed, no change, and a notice on the
      job page (fake search).
- [x] Every style carries `bed_changes_max` and the change-length numbers, with bumped
      versions and updated pins.
- [x] Smoke on explainer, vishva and fastfacts passes T1–T13. The fake planner emits one
      change (crossfade at the reveal) under vishva.
- [x] Ruff, pyright and every test file are green in foreground chunks.
- [x] Done note:
      - the amendment lines for 7.2 (bed by closed mood/flavour from the approved
        library, Freesound as a marked fallback) and 7.3 (at most one change, its `how`,
        the envelope within each bed), for the operator to paste;
      - the starting change lengths and the cards they came from.

## Blocked by

- `issues/073-reference-card-v2.md`
- `issues/075-audio-shortlist-and-approved-library.md`
- `issues/069-a-bed-you-can-hear-on-a-phone.md`

## User stories addressed

- Operator, run04 QA: "For a Saudi-king story I expected light Middle-East music, or a
  low news-style bed."
- Operator, 29 Sep 2026 (grill): "the planner then picks the mood and the mood changes
  for my script from those pairings"; "keep the existing swell/drop volume curve inside
  a bed."

## Done note (29 Sep 2026, HITL session)

A killed run had written most of this ticket; this session checked it against every
criterion, fixed what was wrong, and closed it.

### What a real job sees today

All 12 cards in `docs/reference/inventory/` are v1 (no `parts[].music_mood`, no
`music_changes`), so `reference.music.for_job` returns nothing on every real job, the same
as 077's worked examples. Concretely:

- The sound prompt's section 9 "Music in top shorts" lists the active moods and flavours
  with their meanings, then "(no v2 reference card yet: pick from the moods alone)". The
  planner still has to name the story parts and a closed-list mood per bed, but it learns
  nothing from the references yet.
- `job.log` says so in one line after planning starts:
  `music pairings: none (no v2 reference card yet: pick from the moods alone)`
  (`music pairings: N reference cards` once cards are v2).
- The self-inventory table fills the plan column of the mood-per-part rows from
  `work/sound.json`; the reference side stays "not enough references" until the cards are v2.

The pairings start working after the operator runs `reference inventory --all` (073).

### Starting change lengths (placeholders)

In every style: `bed_changes_max: 1`, `bed_crossfade_s: 1.0`, `bed_silence_s: 0.5`,
`bed_cut_fade_s: 0.02` (under one frame at 30 fps). **No card backs these numbers**: no
committed card is v2, so none carries a measured `music_changes[].how` or length. Re-derive
them from the v2 cards after `reference inventory --all`.

### Amendment lines for the grill decisions (operator to paste)

- **7.2 (amended by 076):** The bed is chosen per story part: the planner names a mood (and
  an optional flavour) from the closed, active list in `assets/audio/moods.yaml`, never
  free words, and code plays a bed from the approved library (075) with that mood:
  flavour match first, then energy distance, then drop fit. With no approved bed for a
  mood, one Freesound bed from 069's music-anchored search is used as a marked fallback
  ("fallback bed: <mood>, no approved bed" in `job.log` and on the job page), and that
  short makes no bed change.
- **7.3 (amended by 076):** A short makes at most `sound.bed_changes_max` (1) bed changes,
  only on the first beat of a story part, and both beds must come from the approved
  library. Its `how` is the one the reference pairings show for that part boundary:
  `crossfade` (`bed_crossfade_s`, equal power), `hard_cut` (fades of `bed_cut_fade_s`) or
  `drop_to_silence` (`bed_silence_s` of nothing between the beds). The swell/drop envelope
  shapes each bed inside its span. Each bed is level-matched and must pass the balance
  (median and speech-band margins) where it plays alone; for the crossfade stretch the
  margin is measured on the sum of both beds.

### Decisions in this session

- **The recorded planner replies stay as committed.** The killed run had hand-edited
  `tests/fixtures/{claude_cli,anthropic}/sound.json` to add `parts`/`bed` (its
  `work/fix_cli_reply.py`); those edits are reverted. Note that these files were never
  real recordings: 014's commit says they were "hand-written in the documented envelope
  shape", and 055 and 070 edited them too. The new fields have defaults, so the adapter
  tests pass on the old reply. Only the end-to-end tests in `test_pipeline.py` push the
  reply through the sound grammar; there, `V18_SOUND` adds the v18 fields in code, in
  plain sight.
- A new `job.log` line `music pairings: ...` (`pipeline.music_line`), so a job says
  whether it had pairings to learn from.

### For the operator's ear (not a failure)

In the vishva smoke, the crossfade stretch (3.0-4.0 s) reads 7.7 dB under the voice,
against 14 dB for each bed alone. The window is in a voice pause (the voice is at -58 dB
from 3.5 to 4.0 s). Two causes, both from what this ticket asks for:

- each bed is level-matched where it plays alone;
- bed 2's window sits on the fake curve's planned fall to -8 dB, so bed 2's gain comes out
  about 5 dB higher than a single whole-short match would give, and the curve's swell peak
  at 3.5 s lands inside the crossfade.

With a real reveal this could sound like a music swell at the change. Whether that is
wanted is your call from the phone. The crossfade's speech-band margin first measured
10.2 dB; 056's repair dipped the band by 6 dB, reaching 12.6 dB against the 12 dB line.

### Checks run (foreground, after the last source edit)

- ruff and pyright clean.
- All 69 test files green, in 8 chunks (1,859 tests).
- Smoke on explainer, vishva and fastfacts: T1-T13 pass on each; `out/qa.json` read in
  keep mode. Vishva writes `music.1.wav` and `music.2.wav` and logs
  "bed change at 3.00 s (b07): crossfade".
- No `src/remotion` change, so the npm checks did not apply.
