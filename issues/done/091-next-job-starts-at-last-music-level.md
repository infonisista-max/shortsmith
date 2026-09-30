# 091 — The next job's music starts at the operator's last slider setting

## Type

AFK — no network, no keys, no new packages.

## Parent PRD

`issues/prd.md`

## Why

Operator, 30 Sep 2026: the slider "remembers my setting so the next job's default moves
toward what I chose."

Taste answers (30 Sep 2026): **exactly the last setting** (not an average, not after a
repeat), and **one setting for all styles** ("my ear is the same across styles").

## What to build

- **One remembered level.** When a slider remix (090) is delivered, its offset is written to
  one small file under `data/` (e.g. `data/music_level.json`: offset, level measure name,
  job id, time). A remembered offset under a different measure than the one the new job
  levels by (089 landing later) is ignored with a log line, and the job starts at 0. The
  last delivered slider remix wins, whatever its style. The sweeper never deletes it, and
  it is git-ignored with the rest of `data/`.
- **Every new job starts there.** `sound_mix` levels the bed at the style's starting level
  (as 090 defines it) plus the remembered offset. With no file, the offset is 0.
  - This is the pipeline's own choice, not the operator's hand on this reel, so 069's
    repair ladder still applies as today. If the bed at the remembered level crowds the
    voice, it is dipped or lowered, with its lines. The ear-wins rule belongs to the slider
    alone (090).
  - `job.json.music_level` records the offset used, with `set_by: remembered` and the job
    it came from.
- **Visible.** The job page's slider mark reads "your last setting (from job <id>)". The
  job log gets one line: `music level: remembered offset <x> from job <id>`.
- **Repeatable.** A retry (043) reuses the job's recorded `music_level`, not whatever the
  file says now. The smoke and the tests never read the operator's file: the path comes
  from config, and the smoke gets a fresh one.

## Acceptance criteria

- [x] Two fixture jobs in a row: the slider set on the first changes the second's starting
      level by exactly that offset, and the second's `job.json` names the first job.
- [x] A slider move on a vishva job carries to an explainer job (one setting for all).
- [x] No file gives offset 0. A remembered level that crowds the voice is repaired, with
      the usual lines.
- [x] A retry keeps its recorded level after the file changes.
- [x] A remembered offset under another measure name is ignored, with its line.
- [x] The smoke is unaffected by a `data/music_level.json` on disk (test).
- [x] Ruff, pyright and every test file are green in foreground chunks. The smoke passes
      T1–T13.

## Done (afk, 30 Sep 2026)

- `sound/remembered.py`: `<data_dir>/music_level.json` (offset, measure, job id, time).
  Like `calibration.json`, it sits in the job's own data directory, so the path comes from
  `SHORTSMITH_DATA_DIR` and the smoke (temp data dir) never reads the operator's file.
  An unreadable file counts as no file.
- Written by `level.remix` only after a slider remix is delivered. A failed remix writes
  nothing. A bed pick (093) must not write it.
- `render.starting_level(job)` at mux: a recorded level on the job is kept (retry). Otherwise
  the file is used, with the line `music level: remembered offset +x dB from job <id>`. A
  file on another measure is ignored with its line, and the job starts at 0.
- Decision: `sound.at_offset` moves `bed_db_under_voice` **and** `bed_accept_db` by the
  offset. The band is only 3 dB wide ([-15, -12] around -14), so without the shift any
  offset past -1/+2 would be "outside the band" and repaired back toward the style's
  level. The speech-band floor and ceiling stay put, so a bed that crowds the voice is
  still dipped or lowered (test: +8 is repaired with the usual lines).
- `jobs.MusicLevel`: `set_by` gains `remembered`, plus `from_job` and `start_db`, which a
  later slider remix carries over. The page mark (datalist label plus a visible line)
  reads "your last setting (from job <id>)".

## Blocked by

- `issues/090-music-level-slider-audio-only-remix.md`

## User stories addressed

- Operator, 30 Sep 2026: "remembers my setting so the next job's default moves toward what
  I chose."
