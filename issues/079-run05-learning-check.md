# 079 — Run05: does the learning work? The run04 recording again, plus one new recording, judged on the phone

## Type

HITL — operator steps with `.env` in place and network. The agent's part is preparing
commands and reading the outputs.

## Parent PRD

`issues/prd.md`

## What to build

The gate for the learning work agreed in the grill of 29 Sep 2026. New reference URLs are
added (081) only after this run shows the worked examples help.

### Operator steps, in order

1. `uv run python -m shortsmith.sound.seed retag` (068), if not already run.
2. Re-analyse the 12 references with prompt v2 (073's done note gives the command). Check
   two cards by eye.
3. Build the audio shortlist (075), put any drop-folder files in, and say yes/no on the
   listening page.
4. **Re-render the run04 recording** (King Saud, vishva, job `20260928-140620-f774e1`) as
   a new job. The script and footage are the same, so any difference comes from the
   learning.
5. `uv run python -m shortsmith.compare_plan <new job id>` (077): match share with and
   without examples.
6. **Record and run one new short** on a different topic. It also counts toward the
   day-14 gate (it runs through the normal job path, nothing special).
7. Phone verdict on both.

### Pass line (the operator's phone verdict decides; the numbers explain)

- For each run04 complaint, fixed / not fixed:
  - background music heard and fits the story;
  - a soft tick or short whoosh marks pop-ups and transitions, not every one;
  - nothing sounds unrelated to the screen (no ring);
  - pictures match what is said.
- Overall rating **≥ run04's rating + 1, and at least 7**. run04 was rated **4.5/10**
  (operator, 29 Sep 2026), so +1 gives 5.5 and the floor of 7 is the line that applies:
  **each run05 short must rate at least 7**.
- **"The examples help"** = both of:
  - the match share with examples is higher than without (step 5);
  - the operator does not mark "pictures don't match what I say".
- The comparison table (074) explains, it does not decide:
  - a red row whose effect the operator also heard becomes a ticket;
  - a red row nobody noticed is only logged here.

## Acceptance criteria

- [ ] Both jobs delivered, with `out/inventory.json` and the comparison table present.
- [ ] The phone verdict per complaint and the overall ratings recorded in this file and
      in `job.json.rating`.
- [ ] The `compare_plan` output recorded here.
- [ ] Decision recorded: go / no-go for 080–085, with the reason. A no-go names the
      tickets to write first.

## Progress (HITL session, 29 Sep 2026)

- **Step 1** done by the operator: `sound.seed retag` ran (6 kept, 4 removed, as in 068's
  done note).
- **Step 2** done by the operator: `reference inventory --all` wrote 13 of 13 v2 cards
  (the 12 plus the long-form `id00R-3OmJ0`, which had no committed card before;
  `ePTZVwipoAM` needed its one retry), then `gaps`. The reviewer checked all 13: every
  `said` is an English gist of at most 12 words with no Devanagari, and every `shows` is
  literal.
  - **Finding:** `FbaBcWgMIEY` (flavour middle_east → european → indian) and
    `ePTZVwipoAM` (mood changes at three boundaries) have an empty `music_changes`, so
    `music.pairing` says "no change". The operator confirms by ear that the music
    changes in both. They are two of the three vishva cards the King Saud re-render
    learns from. → **ticket 086** (per-boundary check at write time with one retry;
    stored cards that fail are skipped at read time). **Step 4 is blocked by 086.**
- Shortlist probe (075) ran by the operator: openverse 200 with 240 results, freesound
  200 with 11,295.
- `.gitignore`: added `assets/audio/beds/`, `sfx/` and `inbox/` (075's refused edit);
  `work/shortlist/` is already covered by `work/`.
- The QA gate for both run05 jobs is **T1–T13**, not T1–T4.
- **Step 3** done by the operator: shortlist built with `--voice` set to run04's voice
  stem, and the listening page answered **30 of 30 yes**. That added 30 entries to
  `assets/audio/catalog.yaml`: 14 beds and 16 effects, 29 from Freesound and 1 from
  Openverse, licences CC0 1.0 (13), CC BY 4.0 (13), CC BY 3.0 (4). The Trap Hamza
  measurement was **not** run before `.env` was parked. It moves to 087's operator step
  (below).
- **Ticket 087** (facts-default bed, learned from the cards and the Dyson v2 profile)
  runs in the same afk run as 086. The finding behind it: 069's
  `speech_band_margin_max_db` 20 rests on run04's non-music bed (`freesound_557546`), and
  the operator heard the Dyson v2 bed clearly on the phone. Trap Hamza is measured in
  step 3 with today's code, and the operator records the cap decision in 087.
- **What committing the v2 cards needed** (the agent's changes, 29 Sep 2026):
  - Three tests read the live cards as v1 or listed every gap name. The 12 v1 cards
    are frozen from HEAD into `tests/fixtures/reference/inventory_v1/`, and the v1
    tests in `test_reference_v2.py` read them there.
  - The v2 cards name 20 new unregistered effects. They are added to
    `assets/reference/effect_map.yaml` as `null`, exactly how an unlisted name was
    already treated, so run05's planner input is unchanged. **Operator or 083:** pick
    closest components for them if wanted, before step 4. Candidates like `text_banner`,
    `label_slide` and `text_badge_pop` may have one.
- Loops (29 Sep 2026): ruff and pyright are clean. All 70 test files are green in
  foreground chunks: render; the catalogue, cards and sound chunk (3 failures fixed
  above and re-run green); the other 51 in four chunks. The smoke delivered with
  T1–T13 passing. No `src/remotion` change.
- Order agreed: step 3 now while `.env` is in place (plus the Trap Hamza measurement)
  → 086 + 087 (one afk run, `.env` parked) → the operator re-runs the two links +
  `gaps` → the cap decision + the facts-default listening pass → steps 4–7.

## Blocked by

- 068, 069, 070, 071, 072, 073, 074, 075, 076, 077, 078
- 086, 087 (for step 4 onward)

## User stories addressed

- Operator, 29 Sep 2026 (grill): measure that learning from the references worked; the new
  run05 recording counts toward the day-14 gate.
