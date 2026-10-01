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
