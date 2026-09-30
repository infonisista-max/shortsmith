# 101 — A change-box picture edit keeps the operator's slider level and bed pick

## Type

AFK

## Parent PRD

`issues/prd.md`

## Why

A picture change (`editor/change.py:585-625`) re-runs from sourcing. The slider level
survives, because `render.py:2928-2936` `starting_level` reads `job.record.music_level`.
The bed pick does not: `bed_pick` (written by `sound/pick.py:169`, declared at
`jobs.py:213`) is read by no render or sound code, so `sound_mix` picks the bed again and
`_audio_rights` rewrites the rights row.

## What to build

- When `job.record.bed_pick` is set, `sound_mix` plays that bed under the whole reel
  (as `sound.repick` does) and keeps its rights row, on every re-render: change box,
  rework, rewind.
- A test runs a picture change on a job with a slider level and a bed pick, and asserts
  both are unchanged in the mix and in the rights log.

## Acceptance criteria

- [ ] Picture change → same bed id, same level, same rights row.
- [ ] A music change from the change box still overrides, as today.
- [ ] Smoke green.

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026: "A change-box picture edit must keep my slider level and bed pick."
