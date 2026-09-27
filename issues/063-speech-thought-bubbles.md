# 063 — Speech and thought bubbles

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Reference inventory (036, 12 shorts, ESTIMATED): 3 of the 12 use comic bubbles, two of
them the operator's own proven shorts — `ePTZVwipoAM` 16 s a speech bubble asking a
question followed by a second answering it, 30 s a thought bubble over a historical
figure; `FbaBcWgMIEY` 19 s a bubble naming "Rennet"; Dhruv `M78CO3Ybr7U` 54 s.

Operator decision, paired review 28 Sep 2026 (amends 4.1 kinds and 9.2; the operator
records the lines from the done note):

1. **Component `bubble`:** `speech` (rounded box with a tail) or `thought` (cloud with a
   trail of dots); white fill, dark outline, dark bold text (Poppins 800), 1–7 words;
   pops in with an overshoot in about 0.2 s. The tail points at `{x, y}` in percent —
   a person in the picture, or the PIP circle when the presenter is the one asking.
2. **Words only from the recording:** a bubble carries what the speaker says someone
   said or thought, or his own question, shortened or put in the caption language —
   never a quote the recording does not carry. Every bubble's text is written to
   `job.log` next to the transcript words it came from.
3. **Dialogue:** a beat may carry two bubbles, the second landing 0.6–1.2 s after the
   first.
4. **Placement:** inside the safe area, off the captions, never covering a face (the
   tail points at it instead); text shrinks to fit down to a minimum size, below which
   the build fails naming the beat.
5. **Cap:** `broll.bubbles_max_per_60s` per style (0 in the four existing styles; the
   recipe styles of 059 set theirs). A bubble's pop may carry a pop cue, or a whoosh
   under 060.

## Acceptance criteria

- [ ] Fixture renders: a speech bubble whose tail tip lands within 40 px of its anchor;
      a thought bubble; a dialogue pair with the second landing 0.6–1.2 s after the
      first.
- [ ] Seven long words shrink to fit; text that cannot fit at the minimum size fails the
      build naming the beat; a bubble over a detected face is moved and logged.
- [ ] `job.log` lists each bubble's text with its source words.
- [ ] Caps enforced by the grammar validator; planner prompt version bumped by one (the
      "only from the recording" rule in one line); the fake planner emits one dialogue
      pair under a test style and the smoke renders it; smoke explainer and hitech pass
      T1–T13 unchanged.
- [ ] `npm run typecheck`, `npm test`, ruff, pyright, every test file green in foreground
      chunks.
- [ ] Done note: the amendment lines for 4.1 and 9.2 for the operator to paste.

## Blocked by

- `issues/056-run03-findings.md` (its never-on-a-face rule for overlays is reused here; the
  face detector is `presenter.py`'s).

## User stories addressed

- Operator, 27 Sep 2026: learn broader styles from the references, his own included.
