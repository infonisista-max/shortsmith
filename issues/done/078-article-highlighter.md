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

- [x] A fixture screenshot (drawn in the test with known text lines) and a fake judge
      returning its line boxes render a beat.
      - A frame at the sweep's midpoint shows marker yellow over the first line's left
        half and none over its right half.
      - The last frame shows all target lines marked.
      - The PIP and caption pixels are unchanged.
- [x] The sweep start is within 0.15 s of the first word's transcript time.
- [x] A highlight on a non-owner asset, or over the cap, fails the grammar naming the
      beat. A judge that finds no boxes drops the highlight with a log line.
- [x] Every style carries `highlights_max_per_60s`, with bumped versions and updated
      pins. `requires_components` checks pass.
- [x] Planner prompt version bumped (when to use it; only on an uploaded
      article/document screenshot). The fake planner emits one highlight when a fixture
      screenshot reference is present.
- [x] Smoke passes T1–T13 on explainer, vishva and fastfacts. `npm run typecheck` and
      `npm test` pass. Ruff, pyright and every test file are green in foreground chunks.
- [x] Done note: the amendment lines for 4.1 and 9.2 (the `highlight` kind, owner
      screenshots only, no fake articles), for the operator to paste.

## Blocked by

- Nothing.

## User stories addressed

- Operator, 25 Sep 2026: learn the references' effect and animation vocabulary.
- Operator, 29 Sep 2026 (grill): "build the most-used new effect inside this work, the
  article highlighter."

## Done note (29 Sep 2026)

What changed:

- **The plan** (`contracts.Highlight`, `Beat.highlight`): at most one per beat,
  `{asset_id, sentence, words: [first, last]}`; `at_s` / `end_s` are written by the
  grammar (the first word's start and the last word's end on the output timeline), the
  planner leaves them empty. Like the text pops, bubbles and stickers it is enabled by a
  cap, not a `Kind`, so every existing plan is byte-identical.
- **Front matter** (every style, versions bumped: explainer 18, educational 16, animated
  16, hitech 17, the recipes 8; pins updated in test_styles, test_recipe_styles,
  test_bed_audible, test_speech_band_margin): `broll.highlights_max_per_60s` (the loader
  requires it) - 0 everywhere but **footage, 2** (its reference `ATkSnL_CdLg` sweeps a
  marker at 14 s; vishva's and fastfacts' references never do, so they keep 0) - and a
  `broll.motion.highlight` row `{kind: sweep, color: <palette.accent>, opacity: 0.45,
  pad_px: 8, push_to: 1.12}` that `render.broll_numbers` requires like the other rows.
  Each spec's B-roll prose gains the "Article highlights" bullet. `fixture.highlights_on`
  is the cap-10 copy the tests judge and render under.
- **Grammar** (`grammar._highlights`, `highlight_cap`; rule 4.1): a `photo` or `card`
  beat with the picture on screen (never `full`); the asset must be one of the owner's
  references ("never a made-up page") and the one the beat shows; words inside the
  transcript with the first starting inside the beat; ceil(cap x runtime / 60) over the
  short. Each violation names the beat. The sweep's start is a change on screen for the
  3.1 density rule (`change_times`). It is not a pop-in: no cue rides it (the ticket's
  "a tick, or nothing" - nothing).
- **The line finder** (`assets/lines.py`): `LineFinder` / `FakeLineFinder` /
  `VisionLineFinder` - one Messages call on the judge model (`RELEVANCE_JUDGE_MODEL`)
  with the screenshot and the sentence, answering line boxes as fractions of the image;
  one `judge` ledger row at `sourcing`, the hard cap checked before the call.
  `find_highlights` runs in `Sourcing.run` after the ladder: the boxes are cached per
  asset + sentence in `work/lines.json`; a beat that does not show the screenshot, no
  finder (`RELEVANCE_JUDGE=none`), a finder error, or no boxes drops the highlight with
  one `highlight: b.. ... dropped: ... (078)` job.log line and the beat stays; a found
  one is a `HighlightRecord` on `work/assets.json` (`manifest.highlights`) and an
  "N lines found" log line. `from_settings` builds the finder from `RELEVANCE_JUDGE`
  (none / fake / api), like the judge.
- **Render** (`render.highlight_visual`, `marker_lines`): a beat with a recorded
  highlight shows the screenshot as a **straight** card (no tilt, no crop, no strip - a
  screenshot reads straight), pushing from 1.0 to `push_to` about the centre of the
  highlighted lines (`CardSpec.origin_x/origin_y`, 0.5 on every other card), placed so
  that at full push it still ends `PIP_GAP_PX` above the circle (`card_bottom` now
  accounts for the origin). The marker strokes are the line boxes in the card image's
  pixels padded by `pad_px`, swept one after another at one speed from the first word to
  the last, finished by the beat's last frame.
- **Remotion** (`components/highlight.tsx`, registered as `highlight`; `card.tsx` draws
  it inside the image box, after the picture, so it rides the card's push and sits under
  the PIP circle and captions): each stroke widens left to right over its seconds, in the
  row's colour at its opacity with `mix-blend-mode: multiply`, so the ink stays dark.
  `types.ts` gains `MarkerLine` / `HighlightSpec` and the card's origin; the registry
  test checks the component is drawn in card.tsx and reads every number from the spec.
- **Analyser**: `highlight` is in `registry.json` and `docs/components.md`, so the
  reference analyser's component list names it (a new card says `highlight`, not
  `unregistered`).
- **Planner prompt v19** (`picture_v19.md`; `sound_v19.md` is v18's text): the
  "Article highlights" paragraph - only on the beat that shows an owner's uploaded
  article or document screenshot, the sentence as printed, the `[first, last]` words,
  never invent a newspaper page / masthead / headline / article text (a text pop or a
  card instead), the cap, never `at_s` / `end_s`. Snapshots recorded by a throwaway
  script under work/ that builds the prompt exactly as the snapshot test does.
- **Fake planner** (`fake_highlight`): where the cap is over 0 and the first reference's
  caption says "screenshot", b01 (which shows it) carries `FAKE_SENTENCE` on words 0-1.
  The smoke uploads no reference, so its plans carry none.
- **Tests**: `tests/test_highlight.py` (29): contracts, styles, the analyser label,
  grammar (landing, density, non-owner, other asset, cap, kind/mode, words), the finder
  (fake, reply parsing, the vision call's request / ledger row / hard cap / refusal /
  missing key), sourcing (record + cache, drops with log lines, the step writes the
  manifest, settings), the render spec (straight card, origin, placement, strokes and
  timing), and one real Remotion render of a drawn 1600x900 screenshot (at the first
  line's sweep midpoint the left of the line is tinted and the right is not; on the
  beat's last frame both lines are tinted at three points each; the PIP circle and
  caption pixels equal the same render with the marker removed).

Loops (all foreground, all seen, after the last source edit): ruff clean, pyright clean,
all 70 test files green in 8 chunks (34 unit files 819 passed; 24 gate / assets /
reference files 803 passed plus test_worked_examples re-run 16 passed after its v19 pin;
sound 120; pipeline + app 155; render 164; recipe_render + smoke_keep 13; smoke 10 in
7:44; smoke_recipes 3), smoke explainer / vishva / fastfacts each T1-T13 pass; a kept
explainer run's out/qa.json read by hand (T1-T13 all passed); a frame pair of the
highlight render looked at (part of the first line marked at frame 8, both lines at
frame 14, the card straight above the circle); `npm run typecheck` clean; `npm test` 29
passed.

What to look at on the next real job with an uploaded article screenshot under footage
(or a style the operator turns on): the `highlight:` lines in job.log (found / dropped
and why), whether the judge model's boxes sit on the printed sentence, whether a tall
phone screenshot's card is large enough to read (the card is the 5.3 card: at most
980 px wide and about 650 px tall, so a 9:16 phone screenshot draws narrow - a crop
around the lines may be the next step), and `push_to` 1.12 and the 0.45 opacity on the
phone. No reference card carries a measured highlight yet, so the row's numbers are
starting values.

Amendment lines for `docs/grill-decisions.md` (operator pastes):

- 4.1 — AMENDED by 078 (29 Sep 2026): a `photo` or `card` beat that shows the owner's
  uploaded article or document screenshot (an owner reference; never a searched or
  generated page, never a made-up newspaper, masthead, headline or article text) may
  carry one `highlight`: `asset_id` (that reference, which the beat itself shows),
  `sentence` (as printed on the screenshot) and `words` (the transcript words that say
  it). Code writes the landing (the first word's start) and the end (the last word's
  end) on the output timeline. At most `broll.highlights_max_per_60s` per 60 s (rounded
  up), enforced by the grammar naming the beat; 0 in explainer, educational, animated,
  hitech, vishva and fastfacts, 2 in footage. The sentence's line boxes are found on the
  image by one call on the judge model at sourcing (one `judge` ledger row, cached per
  asset and sentence); a sentence it cannot find, a missing finder or a beat showing
  another picture drops the highlight with a job.log line and the beat stays. A
  highlight is not the beat's landed event; its start is a change on screen for the
  density rule; it carries no cue.
- 9.2 — AMENDED by 078 (29 Sep 2026): the registry gains `highlight`: the screenshot as
  a straight card pushing in from 1.0 to `motion.highlight.push_to` about the
  highlighted lines, ending above the PIP circle; a marker in `motion.highlight.color`
  (the palette accent) at `motion.highlight.opacity` (0.45), multiplied over the page,
  padded `motion.highlight.pad_px` round each line, sweeping the lines left to right one
  after another from the first word to the last and done by the beat's last frame;
  drawn inside the card, under the PIP circle and the captions. Every spec carries the
  row and the cap.
