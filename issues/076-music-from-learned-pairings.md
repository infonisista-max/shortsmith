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

- [ ] A sound story with a non-list mood, an inactive mood, two changes, or a change off
      a part boundary fails the grammar naming it; one retry as usual.
- [ ] With a fixture library of two approved beds: a two-segment plan renders both. At
      the change beat the music stem shows the planned `how`:
      - crossfade: both beds present for the crossfade length;
      - hard cut: the new bed starts within one frame;
      - drop to silence: music under −60 dB for the silence length.

      The swell/drop envelope still shapes each segment.
- [ ] No approved bed for the mood → one Freesound bed, no change, and a notice on the
      job page (fake search).
- [ ] Every style carries `bed_changes_max` and the change-length numbers, with bumped
      versions and updated pins.
- [ ] Smoke on explainer, vishva and fastfacts passes T1–T13. The fake planner emits one
      change (crossfade at the reveal) under vishva.
- [ ] Ruff, pyright and every test file are green in foreground chunks.
- [ ] Done note:
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
