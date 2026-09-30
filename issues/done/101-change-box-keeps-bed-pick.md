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

- [x] Picture change → same bed id, same level, same rights row.
- [x] A music change from the change box still overrides, as today.
- [x] Smoke green.

## Done note

- `sound_mix` passes the pick to the director: `picked=_picked_bed(job, library)`
  (`render.py:2833`, helper `:2864`). `build_mix(picked=...)` (`sound/__init__.py:1605`)
  plays that bed alone under the whole reel with the story's envelope, as `repick`
  does: no candidate scored, never repaired or dropped (the ear wins), one
  `sound: bed pick: <id> ...` log line. The slider level already survived
  (`starting_level`); a pick no longer in the library is one `sound:` line and the
  director picks as usual.
- `_audio_rights` (`render.py:2907`) keeps the picked bed's existing rights row (same id
  and sha256), so the rights log and credits are unchanged, `fetched_at` included.
- Covers every re-render (change box, rework, rewind): they all mux through `sound_mix`.
- Tests: `tests/test_pick_survives.py` - a picture change on a job at +4 dB with a pick
  keeps the bed id, the level and the rights row; a change-box `music_level` op still
  overrides the level (pick kept); a pick gone from the library falls back with a line.
  The picture is the fake renderer's, the voice stem and mux are real.

## Blocked by

None.

## User stories addressed

Operator, 30 Sep 2026: "A change-box picture edit must keep my slider level and bed pick."
