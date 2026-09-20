# 013 — Presenter face measurement, PIP window and strip

## Type

HITL — needs new package: a face detector, `opencv-python-headless` (Haar cascade bundled) or `mediapipe`, whichever `uv add` allows on this machine. The operator picks and approves; then this ticket becomes AFK. The same detector is reused by 037.

## Parent PRD

`issues/prd.md`

## What to build

Measure the face once per job from eight stills at the research strip times, take the median box, fail early when fewer than six stills have a face, derive the square full-width PIP window with the chin at the configured anchor, grow the circle for a large face, and write the eight-frame strip for the contact sheet. The render uses the measured window instead of the fixed geometry from 004. Never tracks.

Covers PRD `presenter` (measurement). Decisions 3.3, 10.4, 14.1(b).

## Acceptance criteria

- [ ] `presenter.measure(job, spec) -> PipGeometry` extracts eight stills with ffmpeg at the research strip times into `work/frames/strip_<n>.jpg`, runs the detector on each, takes the median box.
- [ ] Fewer than six stills with a face → the job fails at `transcribing` (measurement runs right after ingest) with "we could not find your face, please record facing the camera".
- [ ] Window: full source width, square; chin at `pip.chin_anchor` (0.82) of window height so hair clips before chin; face-box height > 45 % of source width → diameter `pip.large_face_diameter` (340) else the spec diameter (300); both read from front matter.
- [ ] `job.json` stores the face box, window and diameter; `RenderSpec` carries the window; the Remotion `pip` component crops the presenter through it.
- [ ] The eight-frame strip is written for the contact sheet and drawn as its own row (contact sheet update).
- [ ] The fixture's drawn face ellipse is detected on all eight stills; a fixture variant with the ellipse removed fails early with the sentence above.
- [ ] Unit tests on window maths: chin anchor placement, large-face threshold at 44.9 % and 45.1 %, window never exceeds source bounds.

## Blocked by

- Blocked by `issues/006-t1-t4-contact-sheet-delivered.md`

## User stories addressed

- User story 5
- User story 14
- User story 43
