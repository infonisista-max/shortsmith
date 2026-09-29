# 077 — Worked examples: the planner sees how two top shorts edited lines like yours

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

The operator's goal: "pictures and maps that match exactly what I say." The planner today
sees the style's numbers and prose, and nothing of how a top short turned a spoken line
into a picture, an effect and a sound. Operator decisions (grill, 29 Sep 2026):

- **What an example is:** a v2 card's beat table (073): said / shows / match / part /
  layout / effect / sound per shot.
- **Which two:** code picks 2 cards per job, filtered in this order:
  1. by **style** (the card's `styles`);
  2. by **topic**;
  3. tiebreak: **the operator's own Tier B shorts first**, then Tier A.

  Tone matching is left out of v1.
- **The job's topic** is picked by code before the planner runs. It counts keyword hits
  from `assets/reference/topics.yaml` in the brief and the transcript, the same way the
  style alias resolver counts aliases.
  - A tie or zero hits → style-only.
  - The brief can override with `topic: <name>`.
  - The job page shows the topic and the two cards used.
- **How the planner uses them:** a new picture-prompt section, "How top shorts edit a
  line like yours". It holds both beat tables and says: copy the moves (what kind of
  picture for what kind of line, where effects and sounds land, how the parts are
  paced), **never the content** (no names, facts or pictures from the example).
  - An `unregistered` effect in an example is shown as the closest registered component
    or as "(no equivalent: skip)", using a small mapping file `assets/reference/effect_map.yaml`.
  - The grammar still judges every number, so an example cannot push the plan outside
    the style.
- **The plan records** `examples: [<video_id>, <video_id>]` and `topic` in
  `plan.validated.json` and `meta.json`.
- **Did it help?** The comparison table (074) gets its **match share** row filled for our
  short.
  - A CLI, `uv run python -m shortsmith.compare_plan <job_id>`, re-plans the same job
    once **without** examples (plan only, no render, one real planner call, ledger row).
  - It prints the match share of both plans, judged by the same rule. The rule reads the
    plan's `depicts` and asset intents: `named_entity`, a number beat or a literal
    subject counts.
  - This is the run05 measure (079).

## Acceptance criteria

- [ ] Topic: a Hindi history transcript fixture → `history`; a tie → style-only; `topic:
      science` in the brief wins over keywords.
- [ ] Selection: with fixture cards, style filters first, topic second, and Tier B wins a
      tie. With fewer than two matching cards it takes what it has; with none the
      section says "(no worked examples for this style)".
- [ ] The prompt section is rendered from two fixture cards, with unregistered effects
      mapped. Prompt version bumped and snapshots recorded. The needle test finds
      "never the content".
- [ ] `plan.validated.json` and `meta.json` record `examples` and `topic`.
- [ ] `compare_plan` against the fake planner prints both match shares; no network in
      tests.
- [ ] Smoke passes T1–T13 on explainer, vishva and fastfacts.
- [ ] Ruff, pyright and every test file are green in foreground chunks.
- [ ] Done note: the amendment line for 3.x (the planner receives two worked examples
      chosen by style, topic, then Tier B first), for the operator to paste.

## Done (29 Sep 2026, afk session)

All boxes above are met in code and tests (`tests/test_worked_examples.py`, 16 tests).

- **Topic** (`reference.examples.pick_topic`): `topic: <name>` anywhere in the brief wins
  when it names a topic in `topics.yaml` (an unknown name, e.g. "Topic: King Saud", is
  ignored). Otherwise each topic's `en` + `hi` keywords are counted in the brief and the
  transcript words (split on white space and punctuation, including `।`, never on a
  Devanagari vowel sign); one winner or style-only. `other` never wins by keywords.
- **Selection** (`select`): the style's v2 cards (never `tier: own`); then only the
  cards on the topic **when that leaves at least one** (a topic with no card falls back
  to style-only rather than nothing - my call, overrule it if you want an empty
  section instead); then Tier B, Tier A, then video id. Two at most.
- **Section 7** of the picture prompt, "How top shorts edit a line like yours": each
  card's beat table (time, part, said, shows, match, layout, effect, sound) under
  "Copy the moves ... never the content". The sound call does not get it. With no
  card: "(no worked examples for this style)" - which is what every job gets today,
  since the committed cards are still v1 until `inventory --all` runs (073).
- **Effect map** `assets/reference/effect_map.yaml`: all 66 `unregistered` names in
  today's cards, each to its closest registered component or `null`; the loader
  refuses a target that is not in the registry. An unregistered beat effect is looked up
  by the card's own effect/transition name inside the beat's time span; unknown →
  "(no equivalent: skip)". The mappings are my picks - worth one read.
- **Prompt v17**: `picture_v17.md` adds a "Worked examples" paragraph; `sound_v17.md` is
  v16's unchanged. Snapshots recorded with two fixed examples.
- **Records**: `job.json` (`topic`, `examples`), `plan.validated.json` and `meta.json`;
  `job.log` line `worked examples: topic <t> (brief|keywords); <ids>`; the job page
  line "Worked examples: topic ... · <ids>".
- **Match share of a plan** (`examples.plan_match`): a beat counts when it depicts a
  `named_entity` or its `subject_kind` is `entity` or `number`, over all beats. The
  comparison table's match-share row now fills its `plan` column from `work/plan.json`.
- **`compare_plan`**: `uv run python -m shortsmith.compare_plan data/jobs/<job_id>
  [--dir DIR]` re-plans the picture once with no examples (the `PLANNER` adapter bound to
  the job, so one ledger row and the prompt under `work/planner/run<n>/`), writes
  `work/plan.no_examples.json`, and prints both shares. No grammar retry on that one
  call; the job's own plan is untouched. On a job planned before 077 the "with" side is
  a plan that had no examples either.

### Amendment line for 3.x (for the operator to paste)

> 3.x (077): before the picture call, code picks the job's topic (a `topic:` line in the
> brief, else keyword hits from `assets/reference/topics.yaml` in the brief and the
> transcript; a tie or no hit is style-only) and gives the planner two worked examples:
> the beat tables of the v2 reference cards of the job's style, on the topic when any
> exists, the operator's Tier B first, then Tier A. The planner copies their moves,
> never their content; the grammar still judges every number.

## Blocked by

- `issues/073-reference-card-v2.md`
- `issues/074-self-inventory-on-every-job.md` (the comparison table the match share row
  lives in)

## User stories addressed

- Operator, 25 Sep 2026: learn their effect and animation vocabulary, not just pacing
  numbers.
- Operator, 29 Sep 2026 (grill): examples picked "by topic too (history with history,
  science with science)".
