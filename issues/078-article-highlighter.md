# 078 — Article highlighter: a marker sweeps across the key sentence of an uploaded article screenshot, on the spoken words

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

The most-used effect the renderer cannot draw. Three Tier A references use it
(`docs/reference/inventory/GAPS.md`):

- `ATkSnL_CdLg` 14 s (`text_highlight`);
- `M78CO3Ybr7U` 14 s (`yellow_highlighter_box`);
- `QjwDTLPLJ6c` 7, 30, 128, 171 s (`headline_kinetic_highlight`,
  `article_text_scroller_highlight`, `marker_highlighter`, `yellow_strip_highlighter`).

In each, a yellow marker sweeps across a key sentence of a real news snippet while it is
said.

Operator decisions (grill, 29 Sep 2026):

- **Source in v1: an article or document screenshot the owner uploads** as a reference
  picture (first in the asset order already).
- **Never a fake newspaper.** No invented masthead, headline or article text presented
  as if an outlet printed it. With no uploaded screenshot, the planner cannot use the
  highlighter (a text pop or a card instead).
- Web-searched real article screenshots come in 080, first after run05.

### What to build

- **Plan.** A new overlay on a beat that shows an uploaded screenshot:
  `highlight: {asset_id, sentence, words: [i, j]}`. `sentence` is the text to find on
  the screenshot. The grammar checks that the asset is an owner reference and that the
  cap `broll.highlights_max_per_60s` holds (0 in explainer, educational, animated and
  hitech; the recipe styles set theirs).
- **Finding the lines.** One vision call through the judge model: "return the line boxes
  of this sentence on this image".
  - It gets one ledger row, and the result is cached per asset + sentence.
  - No boxes found → the highlight is dropped with a `job.log` line, and the beat stays.
- **Component `highlight`** (registry, `docs/components.md`).
  - A semi-transparent yellow marker stroke, from the style palette (the explainer
    accent `#FFD60A` at about 45 % over the text), sweeps line by line, left to right.
  - It starts on the first spoken word of the sentence (±0.15 s) and ends by its last.
  - The screenshot sits as a card, slowly pushing in toward the highlighted lines.
  - It sits under the PIP circle and captions, never over a face, inside the safe area.
- **Sound:** may carry a tick under 070's palette, or nothing.
- The analyser label set learns `highlight`, so a new reference card names it instead of
  `unregistered`.

## Acceptance criteria

- [ ] A fixture screenshot (drawn in the test with known text lines) and a fake judge
      returning its line boxes render a beat.
      - A frame at the sweep's midpoint shows marker yellow over the first line's left
        half and none over its right half.
      - The last frame shows all target lines marked.
      - The PIP and caption pixels are unchanged.
- [ ] The sweep start is within 0.15 s of the first word's transcript time.
- [ ] A highlight on a non-owner asset, or over the cap, fails the grammar naming the
      beat. A judge that finds no boxes drops the highlight with a log line.
- [ ] Every style carries `highlights_max_per_60s`, with bumped versions and updated
      pins. `requires_components` checks pass.
- [ ] Planner prompt version bumped (when to use it; only on an uploaded
      article/document screenshot). The fake planner emits one highlight when a fixture
      screenshot reference is present.
- [ ] Smoke passes T1–T13 on explainer, vishva and fastfacts. `npm run typecheck` and
      `npm test` pass. Ruff, pyright and every test file are green in foreground chunks.
- [ ] Done note: the amendment lines for 4.1 and 9.2 (the `highlight` kind, owner
      screenshots only, no fake articles), for the operator to paste.

## Blocked by

- Nothing.

## User stories addressed

- Operator, 25 Sep 2026: learn the references' effect and animation vocabulary.
- Operator, 29 Sep 2026 (grill): "build the most-used new effect inside this work, the
  article highlighter."
