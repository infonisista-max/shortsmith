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
- [ ] Planner-cut spans are removed from the word list before paging and the same spans are absent from the audio cut list (shared function with `presenter.cut_list`).
- [ ] Keywords: priority order from the plan, cap 0.25 of words by dropping lowest priority, at most one keyword per page (the first).
- [ ] Each word gets a box at its scaled width plus fixed advance measured with Pillow ImageFont on the bundled Poppins at the spec size; page width measured once; wrapped before render if over 960 px; a page needing three lines raises.
- [ ] Two-line pages produce `beats_with_two_lines` on the caption output; RenderSpec carries it for lower-third suppression (used by 026).
- [ ] Captions are absent from the finale word onward.
- [ ] Boundary tests, `tests/test_captions.py`: name run never split, 0.35 s gap breaks and 0.34 s does not, four words never three lines, keyword cap 0.25 with one per page, finale hide, Devanagari words measured at the same size.
- [ ] Smoke renders the fixture with the new pager and T1–T4 still pass.

## Blocked by

- Blocked by `issues/006-t1-t4-contact-sheet-delivered.md`
- Blocked by `issues/009-grammar-validator.md`

## User stories addressed

- User story 26
- User story 27
- User story 28
- User story 31
- User story 63
