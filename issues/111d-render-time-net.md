# 111d — The render-time net: a beat that still breaks the render is simplified, not fatal

## Type

AFK. Part of 111. Needs 111c.

## What to build

- **Know the failing frame.** `driver.mjs` logs each finished frame range, and on error
  prints one parseable line, `failed frame=<n|unknown>`, taking the frame from Remotion's
  error when present, else from the last progress count. It also prints the error
  message, not only the stack.
- **Map frame → beat** with `BeatSpec.start_frame/end_frame` from the spec. With
  concurrency 2 the exact frame is fuzzy, so take every beat overlapping
  `[last_done, last_done + concurrency * 2]`.
- **When the frame is unknown, find the beat**: render one still per beat (`renderStill`
  at each beat's middle, through a new `driver.mjs still` mode) and take the beats whose
  still fails. If none fails, fall back to the current 097 strip-all-overlays once.
- **Simplify** each named beat to its safest version: a plain photo (its own asset if it
  probes as an image, else a frame grab) with no overlays, else the gradient, keeping
  captions and voice. Re-render. At most 3 rounds; each round may only simplify more
  beats, never re-complicate one.
- **Deliver with a warn.** One `JobRecord.warnings` line naming the beats in plain words
  ("beat 52 was shown as a simple picture because its effect would not render"), a
  `jobs.decide` record, and job.log `rescue:` lines. A single beat never fails the job.
  The job fails only when a beat that is already plain still fails (with the honest
  message), or in the `FATAL_TEXT` cases (node missing etc.).
- This replaces the "render failure naming no beat" branch in `Rescue.attempt`
  (pipeline.py:978-1130) for rendering; the sourcing rescue is unchanged.
- **Re-render cost.** It re-runs only the picture render, not cut/voice/mux, if
  `render_short` (render.py:3914-3930) allows it cheaply. If it does not, note that in
  the handoff and do not refactor.

## Acceptance

- A stubbed driver that fails with `failed frame=<inside b3>` once: b3 is simplified,
  the job delivers, and the warning names b3.
- A stubbed driver that fails with `frame=unknown` while the still mode fails only for
  b2: b2 is simplified.
- Three different failing beats in a row: the job still delivers; a fourth round does not happen.
- `npm run typecheck`, `npm test`.

## Files

`driver.mjs`, `render.py` (`run_driver` parse and simplify helper), `pipeline.py`
(Rescue render branch), `tests/test_render_net.py`, and the `test_editor.py` cases that
change.
