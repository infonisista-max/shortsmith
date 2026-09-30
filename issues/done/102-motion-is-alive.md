# 102 — Pictures and clips move like an editor moved them

## Type

AFK (touches `src/remotion`: `npm run typecheck` + `npm test` mandatory)

## Parent PRD

`issues/prd.md`

## Why

Run05's one clip (b18, Pexels 16865644) landed but read as a still. Four things add up:
- `clips.py:112` `choose_file` takes the smallest passing file (540x960, a 2x upscale).
- Playback starts at 0 s with no push (`vishva.md:53`).
- The judge scores only the preview image (`assets/__init__.py:758`); nothing measures
  motion.
- `render.py` never reads the planner's `beat.motion`, so every photo gets the one Ken
  Burns 1.10↔1.16 (`render.py:535-549`).

## What to build

- **Clip file choice:** prefer the smallest file at least 1080 px wide; else the largest.
- **Clip motion check:**
  - measure motion over the planned window (ffmpeg frame difference on a few sampled
    frames; local, no API);
  - a clip below the style's `clip.motion_min` (front matter) is passed over for the next
    hit;
  - start the window at the clip's most moving stretch, not always 0 s;
  - if none of the hits moves, use a still and log it; never fail the job.
- **`beat.motion` is honoured:**
  - `push_in`, `pull_out`, `ken_burns_in/out`, `pan_left/right`, `pan_up/down` and `hold`
    map to real, distinct moves;
  - the scales and speeds per move live in each style's front matter
    (`broll.motion_moves`);
  - the numbers are checked against the reference frames and the cards' `motion` data
    (073), not taste.
- **Era grade:** a clip or still flagged by 099's era judge gets a light film/sepia grade
  (a renderer filter; strength in front matter).
- **Fold-in (from 103): crops aim at the subject, not the largest face.** 103's
  crop_fill centred on the largest face; on run05's King Saud group photo (ref4) it framed
  a foreground officer while the card's ring circled King Saud. crop_fill, and every 102
  move that aims at a face (push_in / pull_out), aim at the face the ring circles (the
  framing's focus); the largest face only when no subject is known. A named person is
  never swapped for a stranger by a crop.

## Acceptance criteria

- [x] Unit tests: file choice, the motion score on a generated static vs moving fixture
      (ffmpeg testsrc), and the window starting at the most moving stretch.
- [x] A render-spec test: two beats with different `motion` produce different transforms.
- [x] Remotion tests for the moves and the grade; typecheck green.
- [x] Smoke green.
- [x] (fold-in) crop_fill and the subject push on a named person's beat aim at the face
      inside the card ring's circle, or at the ring's point when no found face is there;
      the largest face only when no subject is known (test + run05 ref4 bench frame).

## Blocked by

099 (the era flag); otherwise independent.

## User stories addressed

Operator, 30 Sep 2026: "zero clips ... the creativity of my 12 reference URLs does not
show."

## Done note (30 Sep 2026)

- Clip file: `choose_file` takes the smallest passing file >= 1080 px wide, else the
  largest (src/shortsmith/assets/clips.py:100; `FULL_WIDTH_PX`).
- Motion measure, local ffmpeg: `motion_profile` samples `motion_fps` grey 64x114 frames a
  second and returns the mean abs change per step (clips.py:137); `best_window` is the
  most moving `need_s` stretch that ends inside the file (clips.py:157). Sourcing measures
  each usable file (`_clip_window`, src/shortsmith/assets/__init__.py:751, profile cached on
  the fetch record), skips one under `clip.motion_min` with a `... read as a still (102)`
  line (:918) and takes the next hit; none moving -> the still ladder with the reason
  (:1426), never a failure. The start goes on `BeatAsset.clip_start_s`
  (contracts.py:1078; walk.show :1241) and the renderer plays from it (render.py:1136).
  Fake: `FakeClipSource(still={n}, still_s=...)`, `make_test_clip(still_s=)`.
- Front matter (all seven styles; versions explainer 25, educational 20, animated 20,
  hitech 24, fastfacts / footage / vishva 15): `broll.motion.clip` gains `motion_fps: 4,
  motion_min: 0.004` (a still colour clip measures 0, the synthetic testsrc2 at 1080x1920
  0.0044-0.006, run05 b18 0.009-0.035; its best 1.5 s window starts at 19.25 s, 0.033);
  `broll.motion.era_grade: {sepia: 0.3, saturate: 0.4, contrast: 1.05}`; `broll.motion_moves`
  (styles/explainer.md:162) from the beat tables of the two approved shorts: push_in
  1.0->1.2 aim subject, pull_out 1.3->1.08 aim subject, ken_burns_in 1.04->1.18 pan_y
  -0.04, ken_burns_out 1.17->1.04 pan_x 0.04, pan_left/right 1.12 pan_x +-0.06,
  pan_up/down 1.12 pan_y +-0.06, hold 1.02->1.05 (not in the tables: every reference
  still moves). The inventory cards' `motion` data is effect entrances only (no camera
  numbers), so the beat tables are the evidence. `styles.MoveRow` / `Broll.motion_moves`
  (styles.py:147, :229) refuse a row for a non-camera motion.
- Moves: `Motion` gains pull_out, pan_up, pan_down, hold; `CAMERA_MOVES`
  (contracts.py:231); the editor's photo-motion repair knows all of them
  (editor/repairs.py:45); picture_v20.md lists them (:73; snapshot re-recorded).
  `render.moved` (render.py:992) sets the push and both drifts, clamped inside the margin
  the smaller scale leaves; applied to photo and crop_fill (`FULL_SCREEN_STILLS` :1019,
  :1173); a motion with no row keeps `motion.photo`'s alternating Ken Burns; card /
  backdrop / polaroid keep their own push. `VisualSpec.pan_y_px`, `origin_x/y` (a
  crop_fill's push is centred on the face as drawn, render.py:949), `grade`.
- Era grade: a record whose `judge.era` is `timeless` is drawn with the style's grade, still
  or clip (render.py:1178); `GradeSpec` (contracts.py:1312).
- Fold-in, subject face: the ring lands on the framing's focus (card.tsx: `focus_x *
  image_width`), so that is the subject point when the beat names a person (`never_stock`)
  or carries a ring (`subject_point`, render.py:983). `subject_face` (render.py:956)
  takes the found face whose centre is inside the ring (radius RING_FRACTION/2 of the
  shorter side), else a face-sized box at the point itself; the largest face only with no
  subject. `FaceDetector.detect_all` (presenter.py:150, Haar :172) feeds every face
  (`faces_all`, render.py:2744). The bench aims its crop_fill at its card's ring point
  (`RING_SUBJECT`, bench.py:87, :153). On run05 ref4 Haar finds only the officer; the crop
  now frames King Saud.
- Remotion: `gradeFilter`, `drift` and Framed's origin / translateY
  (src/remotion/components/photo.tsx:21, :30); crop_fill.tsx drifts; clip.tsx grades;
  types.ts mirrors the fields; node tests registry.test.mjs (102 x2).
- Smoke: the clip check reads the measured start (smoke.py:646).
- Tests: tests/test_motion_alive.py (27); 103's crop_fill test is a scene beat now (a named
  one aims at the ring); render tests read the move rows / measured start. Every test file
  green in chunks, smoke T1-T13 pass, ruff, pyright, npm typecheck + test green.
- Frames (scratchpad, not committed): 102_crop_fill_saud_group.png (run05 ref4 crop_fill
  on King Saud), 102_crop_fill_before_after.jpg (103 officer | 102 King Saud | the ring),
  102_group/102_<treatment>.png.
- For next: the move numbers are the explainer references' and are copied to every style;
  the operator's phone verdict may tune them per style. Clips keep no push (4 of 119
  reference clips were pushed).
