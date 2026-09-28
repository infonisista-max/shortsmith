# 062 — Stickers: 3D emoji pops from Microsoft Fluent Emoji (MIT)

## Type

AFK — no new packages (the existing httpx client fetches the PNGs).

## Parent PRD

`issues/prd.md`

## What to build

Reference inventory (036, 12 shorts, ESTIMATED): 7 of the 12 pop a sticker or emoji over
the picture or above the presenter's head — `zXK42RMPKUY` 34 s a lightbulb over his head
with a ding, `bL3rUtUPYsc` 1 s and 44 s a skull, `FbaBcWgMIEY` 24 s a thinking emoji,
`M78CO3Ybr7U` 23 s a question mark, `cKxkAjYHXbk` 7 s a blood splatter. We have none.

Source (read by the paired review, 28 Sep 2026): `github.com/microsoft/fluentui-emoji`,
MIT License, "Copyright (c) Microsoft Corporation". The 3D PNGs sit at
`https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/<Name>/3D/<name_snake>_3d.png`
(checked: `Light bulb/3D/light_bulb_3d.png`, `Skull/3D/skull_3d.png`,
`Exploding head/3D/exploding_head_3d.png` all answer 200; emoji with skin tones sit one
folder deeper under `Default/`).

Operator decision, paired review 28 Sep 2026 (amends 4.1 kinds, 5.1 sources and 9.2;
the operator records the lines from the done note):

1. **A committed catalogue** `assets/stickers/catalog.yaml`: 40–60 curated emoji, each
   with its name, its path under `assets/`, and intent tags (idea, danger, death, shock,
   money, fire, question, yes, no, time, win, love, food, science, space, sport, …).
2. **Fetched at job time, never at render time:** the PNG is downloaded on first use
   into a git-ignored cache (`assets/stickers/fetched/`) and reused after that. One
   rights row per sticker ("Fluent Emoji by Microsoft, MIT License") and one credits
   line. A failed fetch drops that sticker, logs why, and the job goes on.
3. **Component `sticker`:** pops in with an overshoot in about 0.2 s, then floats
   gently; soft shadow; 180–320 px. Placed above the PIP circle (the "over his head"
   spot of the FactTechz lightbulb) or near its subject at `{x, y, anchor}` in percent;
   never over a face or the captions; at most one per beat.
4. **The planner picks by intent tag from the catalogue,** never a free file name; cap
   `broll.stickers_max_per_60s` per style (0 in the four existing styles; the recipe
   styles of 059 set theirs).
5. **Sound:** a ding or pop cue under the existing caps, or a whoosh under 060.

## Acceptance criteria

- [ ] The catalogue is validated at startup: unique names, non-empty tags, every path
      matching the 3D pattern; a broken row stops the app naming it.
- [ ] Tests use a fake fetcher; one live fetch of one PNG in a throwaway spike, logged
      with its status and size; the second use is a cache hit; a network failure leaves
      the beat without its sticker, logged, and the job passes.
- [ ] A fixture beat renders a sticker above the PIP circle; it never overlaps the
      circle, the caption band or a detected face.
- [ ] Rights row and credits line for every sticker used; the fetched cache is
      git-ignored (`git check-ignore` in a test).
- [ ] Caps enforced by the grammar validator; planner prompt version bumped by one; the
      fake planner emits one sticker under a test style and the smoke renders it; smoke
      explainer and hitech pass T1–T13 unchanged.
- [ ] `npm run typecheck`, `npm test`, ruff, pyright, every test file green in foreground
      chunks.
- [ ] Done note: the amendment lines for 4.1, 5.1 and 9.2 for the operator to paste.

## Done note (28 Sep 2026)

Recovery session: an earlier session was killed with the whole slice in the working
tree. This session checked it against every criterion, fixed the missing `stickers`
import in `app.py`, a pyright error in `stickers.parse_catalogue` and two import orders,
then ran every loop.

- Catalogue: `assets/stickers/catalog.yaml`, 51 rows, validated in `create_app`
  (`stickers.load_catalogue`); the MIT licence text sits beside it.
- Live spike (one fetch, real `HttpStickerFetcher`): `Light bulb/3D/light_bulb_3d.png`
  answered HTTP 200 with 22450 bytes; the second `ensure` was a cache hit (1 network call).
- **Deviation:** the fetched cache is `<data dir>/cache/stickers/`, not
  `assets/stickers/fetched/`. The killed session could not edit `.gitignore`, and
  `data/` is already ignored. `tests/test_stickers.py` proves it with `git check-ignore`.
- Loops: ruff and pyright clean; all 53 test files green in foreground chunks; smoke
  explainer, smoke hitech and smoke `--stickers` pass T1-T13 (the kept `--stickers` qa.json
  was read by hand; T12 counts 1 sticker); npm typecheck clean; npm test 26 passed.

Amendment lines for the operator to paste into `docs/grill-decisions.md`:

- **4.1 (kinds), amended by 062:** a `sticker` (a 3D emoji from the committed Microsoft
  Fluent Emoji catalogue) may pop on a picture beat on its spoken word. It sits above
  the PIP circle, or at `{x, y}` near its subject, and never over a face, the circle or
  the captions. It is capped at one per beat and at `broll.stickers_max_per_60s` (0 in
  the four existing styles).
- **5.1 (sources), amended by 062:** stickers have one source, Microsoft Fluent Emoji
  (MIT, raw.githubusercontent.com). The asset step fetches each one at job time into a
  cache and reuses it after that. Each sticker gets one rights row (kind `sticker`, origin
  `fluent_emoji`) and one credits line ("Fluent Emoji by Microsoft, MIT License"). A
  failed fetch drops that sticker with a log line.
- **9.2 (the planner's words), amended by 062:** the planner picks a sticker by an
  intent tag from the catalogue, and may name one of that tag's rows, never a file.
  The grammar writes the tag's first row when no row is named.

## Blocked by

- `issues/056-run03-findings.md` (its never-on-a-face rule for overlays is reused here; the
  face detector is `presenter.py`'s).

## User stories addressed

- Operator, 27 Sep 2026: the six facts references are the base for "background effects".
- Operator, 25 Sep 2026: the system must learn effect vocabulary from the references.
