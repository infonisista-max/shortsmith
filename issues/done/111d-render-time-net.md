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

## Done (111d)

- The net lives in `render.render_picture` (it has the job; `run_driver` stays job-free for
  bench). A re-render re-runs only the picture (driver + the silent 111c re-check), never
  cut, voice or mux.
- `driver.mjs`: `failed frame=<n|unknown> via=<error|progress>` on stdout, `error: <message>`
  then the stack on stderr; a `still` mode (`--frames a,b,c`, one `still frame=<n> ok|failed`
  each, one shared browser). Checked against the real driver with an mp4 in a photo slot:
  `failed frame=72 via=progress` named b3 alone, and the stills failed only b3's frame.
- Levels per beat only ever rise: as planned -> PLAIN (still photo of its own asset or the
  clip's frame grab, every overlay/set piece/transition dropped; the presenter on a `full`
  beat) -> GRADIENT (pip over the gradient). A named beat already at GRADIENT, or the 3
  re-renders spent, raises `render.NetExhausted` - the one exit. No frame and no failing
  still raises it with `unnamed=True`, and the rescue takes the 097 strip-all once.
- `pipeline.Rescue._net_exhausted` is the hook for 111g: today it logs
  `rescue: the render net is exhausted (...); the job fails` and returns None. A raw
  RenderError naming no beat is no longer stripped by the rescue.
