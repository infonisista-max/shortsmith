# 070 — A closed SFX palette: a soft tick on a pop-in, a short whoosh on a transition, and nothing that does not match the screen

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Run04 (job `20260928-140620-f774e1`, vishva). Operator's phone verdict: "The whooshes were
not good. YouTubers put a tick or a short whoosh on pop-ups and transitions to mark the
change." And: "Once a telephone-ring sound came out of nowhere." From `job.log` and
`work/stems/cues.json`:

- **No whoosh played.** The Freesound request filters every SFX to `duration:[0 TO 5]`
  (`freesound.py:85-88`). The 0.8 s `sound.whoosh.max_len_s` (060) is only applied
  *after* download, to the top five hits by relevance. All five were 0.91–3.16 s, and
  `sfx_queries('whoosh')` has one rung. So b05 and b10 were dropped.
- **No tick played.** `popup_tick` is a name the planner made up. It became the search
  "popup tick" (0 hits), with no broader words behind it. Text pops, stickers and bubbles
  earn no floor hit (`TRIGGER_ORDER`, `sound/__init__.py:444`), so all seven
  `popup_tick` cues were dropped.
- **What did play came from free-text names**, each the first hit for those words. The
  "phone ring" is `tally_ding` = "SCORE COUNT.wav": 1.46 s of 14 Hz beeps at 23.40 s on
  the b12 counter. It was placed at the bass-hit level, 0.16 s before b13's stamp hit.
  The rest were a coffee-machine lever (`date_stamp`), a 2 s tick-tock loop
  (`question_tick`) and a buzzing light switch (`changeover`). No length limit applies to
  a non-whoosh cue.

What the references show (`docs/reference/inventory/`, 12 shorts, 762.5 s):

- 85 sfx: whoosh 47, hit 21, ding 11, click 5, other 1.
- About 6.7 per minute, against about 9.3 visual events per minute.
- Every one is `synced_to` a visible event, mostly a pop-in or a flash.
- No ring or trill anywhere.

The approved profile (`docs/reference/README.md:97-104`) still bans "ticks, pops, bells,
chimes" and whooshes. 060 lifted the whoosh ban for vishva only.

Operator decisions (run04 QA, 29 Sep 2026):

- **All styles.** A soft tick or a short whoosh, only on a visible pop-up or transition,
  quiet under the voice, never on every event. Never a sound that doesn't match what is
  on screen: no rings, bells or chimes.
- **The cue vocabulary is a closed palette.** Every cue is fetched only after 068's
  name/tag check.

What to build:

- **The palette.** Cue kinds are `tick`, `whoosh`, `bass`, `drum`, `thump`; the last
  three are the existing floor classes. `ding` and every planner-invented intent are
  gone. The sound-story schema makes `cues[].intent` a literal of the style's palette. A
  name outside it is a 7.x validation error with the usual one retry. The prompt lists
  the palette and when each fits. Bump the prompt version.
- **Where each may sit.** Each style's `sound` front matter gains `tick: {max_per_60s,
  min_gap_s, max_len_s, on: [pop]}`, beside 060's `whoosh`.
  - `pop` is the enter of a 061 text pop, a 062 sticker or a 063 bubble.
  - `whoosh.on` widens to every non-`cut` enter transition the style allows, plus `pop`.
  - The director derives the tick on a pop-in and the whoosh on a transition itself,
    within the caps, as it derives floor hits. The planner only chooses where to place
    them.
  - Starting values: tick `max_per_60s: 6`, `min_gap_s: 2.0`, `max_len_s: 0.25`. Whoosh
    keeps 060's 6 / 3.0 / 0.8. Both come from the inventory rate and the operator's
    "never on every event". The done note names them for the phone verdict.
  - Levels sit inside the existing `cue_db_min`–`cue_db_max` band, with tick and whoosh at
    the quiet end (thump level or below).
- **Every kind has a length.** `max_len_s` per palette kind is in front matter. The
  Freesound request carries it (`duration:[0 TO max_len_s]`), so short files are what
  come back.
  - Each kind's search words come from 068's `kinds.yaml`, several rungs per kind (tick:
    `tick`, `click`, `ui click`, `soft pop`; whoosh: `whoosh short`, `swoosh`,
    `swish fast`), each asked with the length filter.
  - A counter landing, a stamp or a reveal keeps its floor class (bass or drum); it never
    gets a ding.
- **Docs.** `docs/reference/README.md`'s sound profile is amended to match: ticks and
  short whooshes allowed only on a visible pop-in or transition; rings, bells, chimes and
  dings still banned. The line says it is the operator's run04 decision. Per CLAUDE.md,
  first check the change against the reference beat tables and the inventory `synced_to`
  counts, and quote that check.

## Acceptance criteria

- [ ] Run04's sound story (copied into a test as JSON) is rejected: `popup_tick`,
      `question_tick`, `date_stamp`, `tally_ding`, `money` and `changeover` are outside
      the palette. The error names each one.
- [ ] Run04's picture plan with a fake search: every text pop, sticker and bubble enter,
      and every non-cut transition, is considered for a tick or whoosh. The placed count
      respects `max_per_60s` and `min_gap_s`. A test asserts no pop-in or transition
      beyond the cap gets one.
- [ ] With a `MockTransport`, the SFX request for each kind carries that kind's
      `duration:[0 TO max_len_s]`. A 3.16 s whoosh never reaches download.
- [ ] No placed cue is longer than its kind's `max_len_s`. Gate T6's check is unchanged:
      the whoosh exemption stays limited to files within the allowance.
- [ ] All seven style specs carry the `tick` row and the widened `whoosh.on`, with bumped
      `version`s and updated pins. `styles.load_all` refuses a tick or whoosh row with an
      unknown trigger.
- [ ] Smoke on explainer, vishva and fastfacts passes T1–T13. The fake planner emits one
      pop-in tick and one transition whoosh.
- [ ] Render run04's audio again with the fixes (`work/070/mix.wav`, git-ignored),
      listing each cue's time, kind and Freesound name, for the operator's phone check.
- [ ] Ruff, pyright and every test file are green in foreground chunks.
- [ ] Done note: the amendment lines for 7.1 and 7.3 (the closed palette; tick and whoosh
      only on pop-ins and transitions, all styles; rings, bells, chimes and dings banned)
      for the operator to paste. Also what to check on run05: each pop-up and transition
      has a soft mark, never on every one, and nothing sounds unrelated to the screen.

## Blocked by

- 068 (every palette sound is adopted only after its name/tag check).

## User stories addressed

- Operator, run04 QA (29 Sep 2026): "The whooshes were not good. YouTubers put a tick or a
  short whoosh on pop-ups and transitions to mark the change."
- Operator, run04 QA (29 Sep 2026): "Once a telephone-ring sound came out of nowhere."
