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

## Acceptance criteria

- [ ] Unit tests: file choice, the motion score on a generated static vs moving fixture
      (ffmpeg testsrc), and the window starting at the most moving stretch.
- [ ] A render-spec test: two beats with different `motion` produce different transforms.
- [ ] Remotion tests for the moves and the grade; typecheck green.
- [ ] Smoke green.

## Blocked by

099 (the era flag); otherwise independent.

## User stories addressed

Operator, 30 Sep 2026: "zero clips ... the creativity of my 12 reference URLs does not
show."
