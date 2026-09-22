# 010 — Caption pager: full 6.1–6.3 rules with layout measurement

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Replace the minimal pager from 003 with the complete deterministic pager: never split a planner-marked name or number run, break on ASR segment punctuation and inter-word gaps > 0.35 s, fill to max preferring three, remove planner-cut spans before paging, hide captions from the finale word, enforce the emphasis cap with one keyword per page. Lay out each word in a fixed-advance box at its 1.08-scaled width measured with the bundled Poppins, measure page width and wrap before render, assert at most two lines, place the block at the style anchor inside the safe area, and report which beats carry two-line pages so lower-thirds are suppressed there. The renderer draws the boxes it is given.

Covers PRD `captions`. Decisions 6.1, 6.2, 6.3.

## Acceptance criteria

- [ ] `captions.page(...)` reads `words_per_page`, `emphasis_max_ratio`, `word_gap_px`, font, size, `anchor_y`, `max_lines` from the style spec, never constants in code.
- [ ] Marked name/number runs are never split across pages; segment punctuation and gaps > 0.35 s break pages; verbatim spoken language with trailing punctuation stripped.
- [ ] Planner-cut spans are removed from the word list before paging and the same spans are absent from the audio cut list (shared function with `presenter.cut_list`). Word times move onto the cut timeline with `presenter.output_time(spans, t)`: the cold-open lift reorders, so subtracting cut spans alone is not enough.
- [ ] Keywords: priority order from the plan, cap 0.25 of words by dropping lowest priority, at most one keyword per page (the first).
- [ ] Each word gets a box at its scaled width plus fixed advance measured with Pillow ImageFont on the bundled Poppins at the spec size; page width measured once; wrapped before render if over 960 px; a page needing three lines raises.
- [ ] Two-line pages produce `beats_with_two_lines` on the caption output; RenderSpec carries it for lower-third suppression (used by 026).
- [ ] Captions are absent from the finale word onward.
- [ ] Boundary tests, `tests/test_captions.py`: name run never split, 0.35 s gap breaks and 0.34 s does not, four words never three lines, keyword cap 0.25 with one per page, finale hide, Devanagari words measured at the same size.
- [ ] Smoke renders the fixture with the new pager and T1–T4 still pass.

## Blocked by

- Blocked by `issues/006-t1-t4-contact-sheet-delivered.md`
- Blocked by `issues/009-grammar-validator.md`

## Notes from 006

- Pillow is installed (`pillow==12.3.0`); `PIL.ImageFont.truetype` on `assets/fonts/` is available for the word-box measurement.

## Notes from 008

- `PagerNumbers` already comes from front matter: `pipeline.pager_numbers(spec)` reads `captions.words_per_page` / `prefer`. `captions.gap_break_s` (0.35) and `captions.emphasis_max_ratio` (0.25) are on `styles.Captions` too, unread so far. The 6.2 layout numbers reach the renderer through `render.numbers_for(spec)`.

## Notes from 009

- The keyword cap (0.25 by dropping lowest priority) is already applied by the grammar as a 6.1 clamp: `plan.json` holds the trimmed `keywords`, so the pager receives at most the cap; keep the one-keyword-per-page rule here. The pipeline pages from `checked.picture.keywords` (the clamped list) and `request.transcript.words`; the finale beat id is `picture.finale.beat_id`. `presenter.source_time(spans, t)` now exists beside `output_time` for the cut-timeline mapping.
- The grammar snaps beat boundaries to word ends within `beats.snap_window_s`, so the word list and the beat boundaries agree by the time the pager runs.

## User stories addressed

- User story 26
- User story 27
- User story 28
- User story 31
- User story 63
