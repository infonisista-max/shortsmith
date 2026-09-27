# 061 — Text pop: bold words pinned on the picture, landing on the spoken word

## Type

AFK — no new packages (Poppins 900 is already bundled under `assets/fonts/`).

## Parent PRD

`issues/prd.md`

## What to build

Reference inventory (036, 12 shorts, ESTIMATED): the most common overlay in the
references — 47 times across 8 of the 12 — is a short bold word or number popping onto
the picture near the thing it names: `nBihHUlYOQk` 1 s "DARA SINGH", `ePTZVwipoAM` 8 s
"CUCAI" tag on the illustration, `bL3rUtUPYsc` 14 s neon "1945", `zXK42RMPKUY` 35 s
"1 LITER MUCUS", `FbaBcWgMIEY` 17 s "1-2 Day Extra". Our `stamp` (a centred punch in the
top part of the frame) and `label_flyin` (labels on an infographic base only) are close
but are not this: Gemini marked these `unregistered` even with both names in its list.

Operator decision, paired review 28 Sep 2026 (amends 4.1 kinds and 9.2 components; the
operator records the lines from the done note):

1. **What it looks like:** 1–4 words, Poppins 900, yellow or white fill (a neon accent
   from the style palette allowed for years and numbers), thick dark outline and drop
   shadow, pops in with a scale overshoot in 0.15–0.25 s, may tilt −8° to +8°, stays to
   the end of its beat or at most 2.5 s.
2. **Where:** on any picture beat — `photo`, `card`, `clip` (058), presenter full — at
   the planner's `{x, y, anchor}` in percent of the frame, near the thing it names.
   Code keeps it inside the safe area and off the PIP circle and the captions, and
   never on a face (056's stamp-and-face rule applies).
3. **When:** the words come from the script (the name, number or term being said) and
   the pop lands on that spoken word, within ±0.15 s of its transcript time.
4. **How many:** at most `motion.text_pop.max_per_beat` (2) per beat and
   `broll.text_pops_max_per_60s` per short. The four existing styles set 0 (off); the
   recipe styles of 059 turn it on.
5. **Build choice is yours:** a new component or an extension of `label_flyin`; either
   way the registry exposes `text_pop` so a style can require it.
6. **Sound:** a pop may carry a hit or pop cue under the existing caps, or a whoosh
   under 060's allowance.

## Acceptance criteria

- [ ] A fixture photo beat with two text pops renders; a frame after each landing shows
      the text's fill colour in its box at the given position; a pop placed on the PIP
      circle or the caption band is moved inside the allowed area or fails the build
      naming the beat (say which in the done note).
- [ ] Landing time within ±0.15 s of the word's transcript time (transcript fixture).
- [ ] A pop whose box covers a detected face is moved or dropped and `job.log` says so.
- [ ] Caps enforced by the grammar validator; with 0 in a style any text pop fails
      validation naming the beat.
- [ ] Planner prompt version bumped by one; under a test style with text pops on, the
      fake planner emits one pop and the smoke renders it; smoke explainer and hitech
      pass T1–T13 unchanged.
- [ ] `npm run typecheck`, `npm test`, ruff, pyright, every test file green in foreground
      chunks.
- [ ] Done note: the amendment lines for 4.1 and 9.2 for the operator to paste.

## Blocked by

- `issues/056-run03-findings.md` (its never-on-a-face rule for overlays is reused here; the
  face detector is `presenter.py`'s).

## User stories addressed

- Operator, 27 Sep 2026 (run03): "every video same style"; "pop-up images are small".
- Operator, 25 Sep 2026: the system must learn effect vocabulary from the references.
