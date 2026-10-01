# 111g — The last rung: the plain reel always delivers

## Type

AFK. Part of 111. Needs 111d and 111e (shares `pipeline.py`). Operator, 1 Oct 2026.

## What to build

- **Any failure after planning ends in the plain reel**: the speaker video (cut.mp4) with
  captions, voice and music, and no b-roll or overlays. This covers:
  - the 3 rounds of 111d still failing;
  - a crash in mux or QA after rendering;
  - any other exception in sourcing, rendering or qa that the rescue does not fix;
  - a step budget running out (111e).
- **The plain reel is its own render path.** It reuses the spec builder with every beat
  set to the presenter, or to a gradient if no presenter footage exists, plus captions.
  If the Remotion render of that fails too, fall back to ffmpeg alone: cut.mp4 + voice +
  music, with captions burned by ffmpeg if that is simple, else no captions and the
  warning says so. QA runs in warn mode only. A QA failure never blocks the plain reel.
- **The plain reel gets its own fresh time budget** (111e).
- **Job page:**
  - The job ends `delivered`, with a warning in plain words saying what was dropped and
    why (e.g. "We could not finish the edit, so this is the plain version: your video
    with captions and music. The pictures and effects were dropped.").
  - The job page shows **failed** only for planning failures, and for the cases where
    even the plain reel cannot be made (no cut.mp4, no voice stem, ffmpeg missing). In
    those cases the message is honest.
  - `job.log` records the reason; `jobs.decide` records `plain_reel`.
- **Retry** on a plain-reel job still re-runs the full edit from rendering.

## Acceptance

- A stubbed picture render that always fails delivers the plain reel with the warning.
- A stubbed mux crash and a stubbed QA crash each deliver the plain reel.
- The Remotion plain render failing too delivers the ffmpeg-only reel.
- With no cut.mp4, the job fails with an honest message.
- Retry on a plain-reel job re-renders the full edit.

## Files

`pipeline.py` (the end-of-rescue branch), `render.py` (`render_plain` helper), `jobs.py`
or `app.py` only if the page needs a new state label, tests in `tests/test_plain_reel.py`.
