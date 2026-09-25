# 013 — Presenter face measurement, PIP window and strip

## Type

HITL — needs new package: a face detector, `opencv-python-headless` (Haar cascade bundled) or `mediapipe`, whichever `uv add` allows on this machine. The operator picks and approves; then this ticket becomes AFK. The same detector is reused by 037.

## Parent PRD

`issues/prd.md`

## What to build

Measure the face once per job from eight stills at the research strip times, take the median box, fail early when fewer than six stills have a face, derive the square full-width PIP window with the chin at the configured anchor, grow the circle for a large face, and write the eight-frame strip for the contact sheet. The render uses the measured window instead of the fixed geometry from 004. Never tracks.

Covers PRD `presenter` (measurement). Decisions 3.3, 10.4, 14.1(b).

## Acceptance criteria

- [x] `presenter.measure(job, spec) -> PipGeometry` extracts eight stills with ffmpeg at the research strip times into `work/frames/strip_<n>.jpg`, runs the detector on each, takes the median box.
- [x] Fewer than six stills with a face → the job fails at `transcribing` (measurement runs right after ingest) with "we could not find your face, please record facing the camera".
- [x] Window: full source width, square; chin at `pip.chin_anchor` (0.82) of window height so hair clips before chin; face-box height > 45 % of source width → diameter `pip.large_face_diameter` (340) else the spec diameter (300); both read from front matter.
- [x] `job.json` stores the face box, window and diameter; `RenderSpec` carries the window; the Remotion `pip` component crops the presenter through it.
- [x] The eight-frame strip is written for the contact sheet and drawn as its own row (contact sheet update).
- [x] The fixture's drawn face ellipse is detected on all eight stills; a fixture variant with the ellipse removed fails early with the sentence above.
- [x] Unit tests on window maths: chin anchor placement, large-face threshold at 44.9 % and 45.1 %, window never exceeds source bounds.

## Status (HITL session, 25 Sep 2026)

Package: `opencv-python-headless` 4.14.0, installed by the operator (`uv add`);
`cv2.data.haarcascades` resolves and `haarcascade_frontalface_default.xml` loads. The
`alt2` cascade never finds the fixture face; the default one does. Detector
parameters are OpenCV's documented defaults (scaleFactor 1.1, minNeighbors 5) and
were never loosened.

Fixture v2 (approved by the operator, rider 2). Two findings drove it, both in
`fixture.py`:

- Seed finding: this ffmpeg build's `gradients` lavfi source ignores `seed=7`. Two
  generations of the seeded source decode to different frames, so the 12.1 clip was a
  new clip every session and the cascade's verdict changed with the background: the
  original flat ellipse (eyes and mouth only) was missed on 14 of 64 and then 20 of
  80 strip stills across two experiments, always where the gradient behind it was
  bright and low-contrast. Writing the three gradient colours out (`c0`/`c1`/`c2`)
  pins it: decoded frames identical across generations.
- Drawing finding: with a hair cap, brows, larger eyes, a nose shadow and a dark
  collar the cascade found the face on 0-miss runs: 0 misses in 80 stills over ten
  generations in the scratch experiment, and again 0 in 80 over ten generations of
  the committed `make_fixture` (box heights 434-452 px, about 40-42 % of the width,
  so the fixture takes the 300 px circle and the large-face branch is covered by the
  unit tests); the faceless variant is found on 0 of 8. The scratch script and stills
  are not committed.

12.1 is elaborated, not contradicted: the clip is still a moving colour gradient with
a drawn face ellipse in the top third; `fixture.py`'s docstring cites 12.1 and
"fixture v2, 25 Sep 2026".

## Blocked by

- Blocked by `issues/006-t1-t4-contact-sheet-delivered.md`

## User stories addressed

- User story 5
- User story 14
- User story 43
