# 111e — Time budgets per step; the limit never kills a reel that is still rendering

## Type

AFK. Part of 111. It shares `pipeline.py` with 111d, so it runs after it.

## What to build

- **Budgets per step, not one 30-minute job timer** (`config.py:74`,
  `pipeline.py:298-330`, `subproc.Watchdog`):
  - planning, sourcing and qa each get a fixed budget from settings;
  - rendering gets `base + seconds_per_frame * total_frames * margin`. All three numbers
    are settings in `config.py`/`.env.example`, never literals in code. Measure the
    seconds-per-frame default with `uv run python -m shortsmith.bench` on the operator's machine (operator OK'd, 1 Oct 2026), and note
    the numbers in the commit message.
  - **A render that is still making progress is never killed.** The stall clock restarts
    on each progress line, and the watchdog kills only after N minutes with no new frame
    (a stall).
  - The overall job cap stays as a backstop, but it is computed from the step budgets.
- **A retry, or a 097/111d rescue rewind, gets a fresh budget** for the step it enters.
- **render.log** puts a timestamp (UTC ISO, like job.log) on every line, plus one line at
  the start and end of each phase (cut, voice, check, picture, mux) with the elapsed seconds.
- The timeout message on the page says which step ran out and that Retry starts that step fresh.

## Acceptance

- Watchdog tests: a fake process printing progress past the old cap is not killed; a
  silent one is killed at the stall limit.
- A retry from rendering gets the full rendering budget no matter how long the first
  attempt took.
- render.log lines are timestamped (a test on the writer).

## Files

`config.py`, `.env.example` (new keys with default values only), `subproc.py`,
`pipeline.py`, the render.log writer in `render.py`, and the matching subproc/pipeline tests.
