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

## Blocked by

- `issues/073-reference-card-v2.md`
- `issues/074-self-inventory-on-every-job.md` (the comparison table the match share row
  lives in)

## User stories addressed

- Operator, 25 Sep 2026: learn their effect and animation vocabulary, not just pacing
  numbers.
- Operator, 29 Sep 2026 (grill): examples picked "by topic too (history with history,
  science with science)".
