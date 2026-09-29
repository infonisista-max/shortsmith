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

**Amended 29 Sep 2026 (grill on learning from references):**

- **Effect sounds come only from the approved library** (075). The operator has said yes
  to each file by ear. No SFX search runs at job time. A palette kind with no approved
  file drops the cue with a `job.log` line.
- The per-kind search words and length filters below move to 075's shortlist tool. The
  job never uses them.
- **One ding exception.** A soft `ding` is allowed only on a 062 sticker whose intent tag
  is `idea` (the FactTechz lightbulb, `zXK42RMPKUY` 34 s). Rings, bells and chimes stay
  banned.

What to build:

- **The palette.** Cue kinds are `tick`, `whoosh`, `bass`, `drum`, `thump`, `ding`; the
  first two and `ding` are placed by the director, the next three are the existing floor
  classes. `ding` sits only on an `idea` sticker's pop-in (`ding: {max_per_60s: 2,
  max_len_s: 0.8, on: [idea_sticker]}` in front matter), soft (tick level). Every
  planner-invented intent is gone. The sound-story schema makes `cues[].intent` a literal of the style's palette. A
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
  director matches only approved library files within it (075's shortlist already asked
  Freesound with `duration:[0 TO max_len_s]`, from 068's `kinds.yaml` words: tick `tick`,
  `click`, `ui click`, `soft pop`; whoosh `whoosh short`, `swoosh`, `swish fast`).
  - A counter landing, a stamp or a reveal keeps its floor class (bass or drum); it never
    gets a ding.
- **Docs.** `docs/reference/README.md`'s sound profile is amended to match: ticks and
  short whooshes allowed only on a visible pop-in or transition; a soft ding only on an
  idea sticker; rings, bells and chimes still banned. The line says it is the operator's run04 decision. Per CLAUDE.md,
  first check the change against the reference beat tables and the inventory `synced_to`
  counts, and quote that check.

## Acceptance criteria

- [x] Run04's sound story (copied into a test as JSON) is rejected: `popup_tick`,
      `question_tick`, `date_stamp`, `tally_ding`, `money` and `changeover` are outside
      the palette. The error names each one.
- [x] Run04's picture plan with a fake search: every text pop, sticker and bubble enter,
      and every non-cut transition, is considered for a tick or whoosh. The placed count
      respects `max_per_60s` and `min_gap_s`. A test asserts no pop-in or transition
      beyond the cap gets one.
- [x] No SFX search is made at job time: with a fake search that fails the test when
      called for an SFX, every cue is matched from a fixture approved library, and a kind
      with no approved file drops its cue with a log line.
- [x] A `ding` on an `idea` sticker passes; a `ding` on any other sticker, pop or
      transition fails the grammar naming the cue.
- [x] No placed cue is longer than its kind's `max_len_s`. Gate T6's check is unchanged:
      the whoosh exemption stays limited to files within the allowance.
- [x] All seven style specs carry the `tick` row and the widened `whoosh.on`, with bumped
      `version`s and updated pins. `styles.load_all` refuses a tick or whoosh row with an
      unknown trigger.
- [x] Smoke on explainer, vishva and fastfacts passes T1–T13. The fake planner emits one
      pop-in tick and one transition whoosh.
- [x] Operator step (the afk run has `.env` parked and no network, so it does not
      render with real sounds): the done note gives the exact command for the
      operator to run with `.env` back in place, once 075's library has approved effect
      files. It re-renders run04's audio with the fixes into `work/070/mix.wav`
      (git-ignored) and prints each cue's time, kind and library file, for the
      operator's phone check.
- [x] Ruff, pyright and every test file are green in foreground chunks.
- [x] Done note: the amendment lines for 7.1 and 7.3 (the closed palette; tick and whoosh
      only on pop-ins and transitions, all styles; a soft ding only on an idea sticker;
      effect files only from the approved library; rings, bells and chimes banned)
      for the operator to paste. Also what to check on run05: each pop-up and transition
      has a soft mark, never on every one, and nothing sounds unrelated to the screen.

## Blocked by

- 068 (every palette sound is adopted only after its name/tag check).
- `issues/075-audio-shortlist-and-approved-library.md` (the approved library shape; the
  tests use a fixture library, so only the operator step needs real approved files).

## User stories addressed

- Operator, run04 QA (29 Sep 2026): "The whooshes were not good. YouTubers put a tick or a
  short whoosh on pop-ups and transitions to mark the change."
- Operator, run04 QA (29 Sep 2026): "Once a telephone-ring sound came out of nowhere."

## Done (29 Sep 2026, afk session)

What was built:

- `contracts.CUE_KINDS` = tick, whoosh, bass, drum, thump, ding. The sound-story schema
  lists them as an enum on `cues[].intent`; `grammar.validate_sound` refuses any other
  name as a 7.1 violation naming it (run04's six are all named; one retry as usual).
- Grammar 7.3: a `tick` only at the event of a beat that pops something in; a `ding`
  only at the event of a beat carrying a sticker tagged `idea`; a `whoosh` at the start
  of a beat whose non-cut enter `sound.whoosh.on` names, or at a pop-in with `pop` in it.
  Floor classes keep 9.4's rules.
- Front matter, all seven styles (versions explainer 16, educational 14, animated 14,
  hitech 15, footage / vishva / fastfacts 6; pins updated): `whoosh` out of
  `sound.forbidden`; `whoosh: {6, 3.0, 0.8, on: [<the style's non-cut enters>, pop]}`;
  `tick: {max_per_60s: 6, min_gap_s: 2.0, max_len_s: 0.25, on: [pop]}`;
  `ding: {max_per_60s: 2, max_len_s: 0.8, on: [idea_sticker]}`;
  `floor_max_len_s: {bass: 1.5, drum: 1.2, thump: 0.8}` (075's shortlist lengths).
  `styles.load_all` refuses a row naming any other trigger, and a floor class with no
  length. The Sound prose of every style says the same.
- Director (`sound.place_cues`): every cue plays the shortest approved file of its kind
  no longer than the kind's length; only the tracked catalogue is the approved library
  (`Library.approved_sfx`, never `fetched/`); no SFX search at job time (`place_cues`
  takes no search; `build_mix` asks the search for beds only). A kind with no file
  drops its cues with a `job.log` line. After the planner's cues, the changeover and the
  floor, the director marks pop-ins (tick; ding on an idea sticker) and non-cut
  transitions (whoosh) itself (`sound.mark_candidates`), each kind within
  `max_per_60s` (scaled, rounded up like T6) and `min_gap_s`; every candidate left
  unmarked has its line. Levels: tick and ding 0.2 of the band, whoosh 0.4 (thump
  level). The 7.3 changeover after a drop plays the approved bass (the palette has no
  changeover kind).
- Gate T6: a whoosh on any non-cut enter its row names passes the trigger check (was
  `flash` only); the sweep exemption is unchanged (files within `max_len_s` only).
- Prompt v16 (sound file lists the palette and where each kind sits; picture file is
  v15's unchanged); snapshots recorded. The fake story speaks only the palette: one
  pop-in tick where the plan pops (vishva, fastfacts: b03) and one transition whoosh
  (explainer b03's fade; recipes b05's fade).
- `docs/reference/README.md` sound profile amended with the inventory check quoted;
  `assets/audio/README.md` says effects are never searched at job time.

Numbers for the phone verdict: tick 6 a minute, at least 2.0 s apart, at most 0.25 s
long; whoosh 6 a minute, 3.0 s apart, at most 0.8 s; ding 2 a minute, at most 0.8 s;
tick and ding at 20 % of the cue band, whoosh at 40 % (the thump's level).

Operator step (with `.env` back in place, once 075's library has approved tick and
whoosh files):

    uv run python -m shortsmith.sound.remix data/jobs/20260928-140620-f774e1 --out work/070

It re-mixes run04's plan, sound story and voice with today's director into
`work/070/` (git-ignored; the job folder is not written), leaves `work/070/mix.wav`,
and prints one line per cue: time, kind, source, beat and library file. Run04's story
still names the pre-070 intents; the director drops those with a line and marks the
pop-ins and transitions itself, which is what run05's planner will then place.

Amendment lines for the operator to paste:

- 7.1 (as amended, 070): Cues are a closed palette - tick, whoosh, bass, drum, thump,
  ding - and any other name is a validation error. Every effect file comes only from
  the operator's approved library; nothing is searched for at job time. Rings, bells
  and chimes are banned.
- 7.3 (as amended, 070; all styles): a soft tick only on a visible pop-in and a short
  whoosh (at most 0.8 s) only on a visible transition or pop-in, within the style's
  `sound.tick` / `sound.whoosh` caps and never on every change; a soft ding only on an
  `idea` sticker's pop-in; every kind has a length in front matter.

What to check on run05: each pop-up and transition that matters has a soft mark, never
every one; nothing sounds unrelated to the screen; no ring, bell or phone sound.

Notes:
- `AudioSearch.sfx` and the Freesound adapter's SFX path stay (the adapter's tests and
  `sfx_queries` still use them); no job calls them.
- The shipped `catalog.yaml` has no approved effect yet, so until the operator approves
  files on `/audio/shortlist` a real job places no cue (`job.log` says so; the page
  warns only when the bed is missing too).

## Finish (29 Sep 2026, HITL session)

The afk session ticked the boxes above and then ran out of time with the smoke tests
still red (3 in `test_smoke.py`, 1 in `test_smoke_recipes.py`). This session fixed them:

- `tests/test_smoke_recipes.py`: footage's summary now says `recipe flash b03, tick b03`
  (b03's pop-in carries the tick; the whoosh moves to b05's fade), not the pre-070
  `whoosh b03`.
- `smoke.check_marks` wanted a tick wherever any beat popped something in, but one cue a
  beat means a pop-in on a beat another cue already holds gets none (the stickers walk's
  b01 under the opening bass, the bubbles walk's b04 under the stamp's). It now wants a
  tick only where a pop-in beat is free.

Then every loop was run in the foreground, after the last source edit: ruff, pyright,
all 67 test files in chunks under 8 minutes each, and the explainer smoke. The vishva smoke
was also run in keep mode, and its `qa.json` shows T1-T13 passing.

For the phone verdict: the director caps tick and whoosh at 6 a minute each, but the
style's overall `cues_max_per_60s` applies too (the cap tests lift it to isolate the
per-kind caps), so run05 may play fewer marks than 6 a minute.
