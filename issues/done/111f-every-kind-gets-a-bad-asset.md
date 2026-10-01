# 111f — The test that would have caught today

## Type

AFK. Part of 111. The last one (after 111g).

## What to build

- **A real-render test** (real driver, fixture clip). Build a plan in which every beat
  kind in the renderer appears. Take the kind list from `contracts.py`/`Short.tsx` and
  assert it is complete, so a new kind fails the test until it is added. Run three
  variants:
  1. every kind gets a clip where a still was expected;
  2. every kind gets an image with the wrong extension (WebP saved as .jpg, PNG saved as .mp4);
  3. every kind gets a missing file.

  The job delivers each time. The output is the right length and has an audio stream,
  `job.log` has the `check:` lines, and the page warning is present.
- **A net test:** a component forced to throw (a test-only spec flag, or a beat kind the
  test registers) is simplified by 111d, and the job delivers with a warn.
- **A last-rung test:** a render that fails on every beat delivers the plain reel (111g)
  with its page warning, and the job never shows failed.
- Keep each test file under 8 minutes. Use short beats; scale frame counts the way
  `fixture.smoke_specs` scales them.
- Add the case to `smoke.py` only if it stays fast; otherwise leave it out and say why.

## Files

`tests/test_render_safety.py` (new), maybe a fixture helper in `tests/conftest.py`.

## Done (111f)

- `tests/test_render_safety.py`: a full job (real driver, real mux, fixture clip) whose
  spec draws every `contracts.Kind` (11 planned beats, 6 overlays/events, 3 split-off
  beats: parallax, vector_illustration, presenter_pip with a lower third); completeness
  is asserted against `TIER1_KINDS + TIER2_KINDS`. Three variants break every sourced
  file on disk (clip for a still; WebP as .jpg / PNG as .mp4; missing): each delivers,
  6 s with audio, `check:` lines, the page warning, and the net never fires. b52 itself
  (a clip in a wall cell, check off) is simplified by the net; every file missing with
  the check off ends in the plain reel. 6 tests, about 4 min.
- Gap found and fixed: a dropped list-row icon kept its icon box, so `<Img src="">`
  threw in Chrome ("No src prop was passed to <Img>"); `render_check` now drops the box
  and moves the text into its place.
- Not added to smoke.py: each case is a 40-60 s real render; smoke stays fast.
