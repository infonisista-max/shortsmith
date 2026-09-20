# 025 — Seed the audio library: 12 beds and 20 SFX, hand-listened, with licence text

## Type

HITL — operator-supplied input per 7.2: Shubham sources the files by hand from YouTube Audio Library and Mixkit, hand-listens each, and writes the tags and licence text. The agent's part is limited to running the measure and check scripts and validating the catalogue.

## Parent PRD

`issues/prd.md`

## What to build

The real seed under `assets/audio/`: twelve beds (suspense, money, history, tech, calm, upbeat; two each) and twenty SFX by intent, each with licence text beside the file and a hand-written tag set, measured by the 023 script and passed through the sweep detector before commit. Smoke keeps using the synthesized catalogue; the real seed is what jobs use.

Covers PRD "Operator-supplied inputs". Decisions 7.1, 7.2, 7.3.

## Acceptance criteria

- [ ] `assets/audio/beds/` holds 12 files and `assets/audio/sfx/` holds 20, each with an entry in `catalog.yaml` carrying `source`, `source_url`, `licence` text, `author`, hand-written `tags`, and measured `duration_s`, `bpm`, `key`, `energy`, `drop_points_s`, `loop_ok`.
- [ ] Every SFX intent the floor needs (bass, drum, thump) and at least ten planner-style intents (reveal_drop, money, popup_tick, changeover, ...) have a matching file.
- [ ] `python -m shortsmith.sound.seed check` passes on every file; the catalogue validates at startup.
- [ ] A real job on the laptop selects a seeded bed and the stem balance report is within acceptance.

## Blocked by

- Blocked by `issues/023-sweep-detector-t6-catalogue-measure.md`

## User stories addressed

- User story 29
- User story 33
