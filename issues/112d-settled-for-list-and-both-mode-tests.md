# 112d — "What the system settled for" on every job page, and tests in both modes

## Type

AFK. Part of 112. After 112c.

## What to build

- **The job page** for a delivered job shows a "What the system settled for" list, one
  row per beat: what was wanted, what was used, and why. It covers every kept rung:
  - gradient and generated image;
  - re-dress;
  - a fallback bed, "voice and hits only";
  - overlays dropped for want of a face-free spot (text pops, bubbles, stickers,
    particles, a stamp left on a face);
  - kept soft grammar rules;
  - a spent judge budget;
  - an unmeasurable clip motion.

  The data comes from one place: the decisions and `settled:` lines written in 112b.
  Each site adds a `settled` record, and the page only reads.
- In forgiving mode the same list also shows every downgrade the nets made, marked as a
  repair.
- **Tests:** a both-mode pass over `test_render_safety` (111f): every variant in both
  modes, with an asserted outcome for each (delivered, loud stop naming the beat, or the
  gate). The settled list has a row for each kind.

## Acceptance

A delivered strict job shows the list; a rating can be traced to a beat and its reason.
