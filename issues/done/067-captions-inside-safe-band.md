# 067 — Caption lines are laid out inside the safe band, never under the right rail

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Run04 (job `20260928-140620-f774e1`, vishva) failed QA on T12:

> caption page 3 'है' at 2.26 s reaches x 994.97, inside the right rail; caption page
> 56 'था' at 54.28 s reaches x 940.16, inside the right rail

Cause: all seven styles set `captions.max_width_px: 960`, and `captions.py` centres
every line on the frame (`x = (WIDTH - line) / 2`, centre 540). A full line can
therefore run from x 60 to x 1020. The 6.3 right rail starts at x 940
(`SAFE_RIGHT_PX = 140`). The pager never looks at the safe area, so only T12, after
the whole render, catches a line that goes too far.

- Page 3 is 910 px wide ("प्राइम मिनिस्टर कौन है") and reaches 994.97.
- Page 56 is 800.3 px wide ("abduct कर लिया था") and reaches 940.16, over by 0.16 px.

Hindi pages with long Devanagari words are the first to go past 800 px. Earlier shorts
happened to stay under that.

Operator decision (QA review, 28 Sep 2026): the pager lays the caption block out in
the safe band, from the left margin (`SAFE_LEFT` 60) to the rail (x 940), which is 880
px wide with its centre at x 500:

- **One definition of the safe area.** Today the 6.2/6.3 numbers are defined three
  times, and `contact_sheet.py` borrows the third copy:
  - `render.py:722-723` has `SAFE_LEFT = 60.0` and `SAFE_RIGHT_PX = 140.0`, and
    `render.py:899-900` has `SAFE_TOP_PX = 250.0` and `SAFE_BOTTOM_PX = 320.0`.
  - `infographics.py:85-87` has `SAFE_LEFT`, `SAFE_RIGHT_PX` and `SAFE_TOP`.
  - `qa/technical.py:763` has `SAFE_TOP_PX, SAFE_BOTTOM_PX, SAFE_RIGHT_PX = 250, 320,
    140`.
  - `contact_sheet.py:60` re-exports `technical`'s values.

  Create one module, `src/shortsmith/safe_area.py`, that holds the frame size, the left
  margin, the top zone, the bottom zone and the right rail, plus the band's left edge,
  right edge, width and centre derived from them. It imports nothing from `shortsmith`,
  so `captions` can use it without an import cycle through `render`. `captions`,
  `render`, `infographics`, `qa/technical` (T12) and `contact_sheet` all import from it.
  None of them keeps a copy, not even as an alias assigned from a literal.
- Lines wrap at `min(captions.max_width_px, band width)` (880) and are centred on the
  band's centre (x 500). The whole block moves 40 px left of the frame centre.
- `styles.load_all` refuses a style whose `captions.max_width_px` is wider than the
  band, and names the style and the number. The shipped styles move to
  `max_width_px: 880`, with each `version` bumped, so the spec states the width the
  pager really uses.
- A single word wider than the band still makes today's `LayoutError`: it is a pager
  bug, never a caption that runs into a zone.
- Render run04's page 3 before and after the change, plus one short English page, and
  save the frames to `work/067/` (git-ignored). List their paths in the done note. The
  operator judges the 40 px shift on the phone. The agent does not judge the look.

## Acceptance criteria

- [x] Run04's page 3 and page 56 words (copied into a test as text, times and keyword
      flags; no media) lay out with every box's right edge ≤ 940 and left edge ≥ 60.
      Page 3 wraps to two lines or stays on one line inside the band.
- [x] A property-style test over every shipped style: any page the pager accepts has
      every word box inside x 60–940.
- [x] `styles.load_all` rejects `max_width_px: 960` with a message naming the style.
      All seven specs carry 880 and a bumped `version`, and the version pins in the
      style tests are updated.
- [x] `safe_area.py` is the only place the numbers 60, 140, 250 and 320 are defined as
      safe-area values. A test asserts that `render`, `infographics`,
      `qa.technical`, `contact_sheet` and `captions` all use its values, and a grep in
      the done note shows no other `SAFE_*` definition under `src/shortsmith/`.
- [x] T12 still judges every caption word. Its only change is where it imports the
      zones from. It passes on smoke explainer,
      hitech, footage, vishva and fastfacts (T1–T13).
- [x] The `captions.py` docstring (Layout, 6.2) says "centred in the safe band", and
      the `WIDTH` comment no longer calls the frame "the width the block is centred
      in".
- [x] Ruff, pyright and every test file are green in foreground chunks (plus
      `npm run typecheck` and `npm test` if anything under `src/remotion/` changed).
- [x] The before and after frames are saved to `work/067/`.
- [x] Done note: the amendment line for 6.2/6.3 for the operator to paste, the paths of
      the `work/067/` frames for the operator's phone verdict, and what to check on
      run05: captions sit just left of centre and never under the like/comment rail on
      the phone.

## Blocked by

- Nothing.

## User stories addressed

- Operator, run04 QA (28 Sep 2026): QA failed T12, with two caption lines reaching
  into the right rail.

## Done note (28 Sep 2026)

- `src/shortsmith/safe_area.py` is the one 6.2/6.3 definition (frame 1080 x 1920,
  `SAFE_LEFT` 60, `SAFE_RIGHT_PX` 140, `SAFE_TOP_PX` 250, `SAFE_BOTTOM_PX` 320; band x
  60-940, width 880, centre 500). It imports nothing from `shortsmith`. `captions`,
  `render`, `infographics`, `qa.technical` and `contact_sheet` import from it
  (`infographics.SAFE_TOP` is now `SAFE_TOP_PX`). Grep
  `^\s*SAFE_\w+(\s*,\s*SAFE_\w+)*\s*=` under `src/shortsmith/` finds only
  `safe_area.py:18-21` and `contact_sheet.py:94 SAFE_COLOUR` (a colour, not a zone).
  `tests/test_safe_area.py` asserts the same thing.
- The pager wraps at `min(max_width_px, BAND_WIDTH)` and centres each line on x 500.
  A word wider than the band raises `LayoutError` ("wider than the safe band").
- All seven specs: `max_width_px: 880`. Versions: explainer 13, educational, animated
  and hitech 12, footage, vishva and fastfacts 3. `styles.check` refuses a wider
  width: "<style>: captions.max_width_px 960 is wider than the safe band 880 px".
- Run04's page 3 with vishva captions: it was one line from x 85.0 to 995.0. It now
  wraps to two lines: "प्राइम मिनिस्टर कौन" from 79.8 to 920.2, and "है" from 476.2 to 523.8
  on its own line. That second line is one short word; the operator may want to look
  at it.
- `tests/test_pipeline.py`: the CLI-planner prompt test now uses an empty
  `sound.Library`. Without it, runtime adoptions under the git-ignored
  `assets/audio/fetched/` leaked tags into the prompt on this machine. This is a test
  isolation fix found while running the suite for this ticket.
- Frames for the phone verdict (git-ignored). They show the explainer composition on
  the fixture, with vishva's caption numbers and the real driver.
  `work/067/frames.py` renders them again:
  - `work/067/page3_before.jpg`, `work/067/page3_after.jpg` (run04 page 3)
  - `work/067/english_before.jpg`, `work/067/english_after.jpg` ("prime minister")
- Amendment line for 6.2/6.3 (for the operator to paste): "6.2/6.3 amended by 067
  (28 Sep 2026): caption lines wrap at min(max_width_px, 880) and are centred in the
  safe band x 60-940 (centre x 500), no longer on the frame centre; the safe-area
  numbers are defined once, in `safe_area.py`."
- Run05 check on the phone: captions sit about 40 px left of centre and never go under
  the like/comment rail. A long Hindi page wraps instead of running right.
