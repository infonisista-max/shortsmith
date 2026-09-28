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

- [x] Fixture renders: a speech bubble whose tail tip lands within 40 px of its anchor;
      a thought bubble; a dialogue pair with the second landing 0.6–1.2 s after the
      first.
- [x] Seven long words shrink to fit; text that cannot fit at the minimum size fails the
      build naming the beat; a bubble over a detected face is moved and logged.
- [x] `job.log` lists each bubble's text with its source words.
- [x] Caps enforced by the grammar validator; planner prompt version bumped by one (the
      "only from the recording" rule in one line); the fake planner emits one dialogue
      pair under a test style and the smoke renders it; smoke explainer and hitech pass
      T1–T13 unchanged.
- [x] `npm run typecheck`, `npm test`, ruff, pyright, every test file green in foreground
      chunks.
- [x] Done note: the amendment lines for 4.1 and 9.2 for the operator to paste.

## Blocked by

- `issues/056-run03-findings.md` (its never-on-a-face rule for overlays is reused here; the
  face detector is `presenter.py`'s).

## User stories addressed

- Operator, 27 Sep 2026: learn broader styles from the references, his own included.

## Done note (28 Sep 2026)

What changed:

- **The plan** (`contracts.Bubble`, `Beat.bubbles`): a picture beat may carry a list of
  bubbles, each `{shape, text, first, last, x, y}` - `speech` (a rounded box with a tail)
  or `thought` (a rounded body with a trail of dots), the words, the transcript word run
  (`first`-`last`, inclusive) the text came from, and the point in percent of the frame
  the tail points at. `at_s` is on the model but written by the grammar; the planner is
  told never to write it. `bubble` is not a `Kind` or an `OverlayKind`: it is enabled by
  `broll.bubbles_max_per_60s` > 0 like `flash` and `text_pop`, so every existing plan and
  fake plan is byte-identical under the four styles (all cap 0, `version` 7 -> 8).
- **Front matter** (every style): `broll.bubbles_max_per_60s: 0` (the loader requires it)
  and a `broll.motion.bubble` row `{kind: pop, duration_s, hold_max_s: 3.0,
  max_per_beat: 2, words_max: 7, dialogue_gap_min_s, dialogue_gap_max_s, size_px,
  min_size_px, width_px, fill, ink}` (explainer 0.2 s, 0.6-1.2 s, 56/36 px, 640 px,
  white on `#111111`; the drafts vary the overshoot, gap, size and ink), which
  `render.broll_numbers` requires like the other rows. `fixture.bubbles_on(spec)` is the
  copy with the cap at 20 (two bubbles on the six-second fixture: one dialogue pair)
  that the tests (`conftest.bubble_style`) and the smoke's `--bubbles` judge and render
  under.
- **The dialogue gap on the fixture** (the one call to record): no 0.5 s fake beat can
  hold a real 0.6 s gap, so `fixture.smoke_specs` scales `motion.bubble.dialogue_gap_*`
  to 0.2-0.4 s (`SMOKE_BUBBLE`) exactly as it scales the beat lengths, asset counts,
  ramps and pauses; the shipped row keeps 0.6-1.2 s, the grammar tests judge the 56 s
  plan by it, and the render test draws a pair 0.6 s apart on b01 stretched to 4 s. The
  renderer never reads the gap: it draws the `at_s` the grammar wrote.
- **Grammar** (`grammar._bubbles`, `bubble_cap`, `bubble_gap`; rule 4.1): a bubble sits on
  a `photo`, `card` or presenter-full beat only; 1-`words_max` words; `first`-`last` exist
  in the transcript and the first source word starts before the beat ends (nothing to
  quote yet otherwise); at most `max_per_beat` per beat and ceil(cap x runtime / 60) over
  the short (0 stays 0, so under every existing style any bubble is a 4.1 violation
  naming the beat). Landing: the first source word's output time (mapped through the
  cut like beat boundaries), or the beat's start when the words came earlier; a second
  bubble lands `dialogue_gap_min_s`-`dialogue_gap_max_s` after the one before it (its own
  word's time when inside that window, else the nearer edge), and a beat that ends
  before the window opens is rejected as too short for a pair. A beat with bubbles
  counts as changing on screen for 3.1; `validate_sound`'s `bare` and `on_pop` take
  bubbles like text pops, so an `event` cue may hit a bubble and a whoosh may ride it
  with `pop` in `sound.whoosh.on`.
- **Render** (`render.bubble_lines`, `bubble_tail`, `bubble_path`, `bubble_dots`,
  `bubble_spec`, `build_spec`'s `bubbles`): the words wrap greedily inside `width_px` at
  `size_px`, the type shrinking in 4 px steps to `min_size_px` until they fit on at most
  four lines (`BUBBLE_LINES_MAX`); text that never fits raises `RenderError` naming the
  beat. The body is asked for above the anchor (`BUBBLE_TAIL_LEN_PX` 90 px), then
  clamped into the safe area and moved by 061's `place_text_pop` search off the PIP
  circle (a `pip` beat), the caption band, **the stamp** (a new obstacle, so the fake's
  card beat keeps its stamp readable), the face (the image's via the 056 detector, or
  the presenter's on a `full` beat), **the anchor's own 80 px keep-out** (the body never
  covers what it points at) and **the beat's earlier bubble** (a pair never overlaps).
  A moved bubble is one `bubble:` line in job.log naming the beat, the shape, the words,
  what it cleared and where it went; with a face in the way and no free spot the bubble
  is dropped and logged; with no face the build fails naming the beat. The tail leaves
  the body side facing the tip, its 56 px base kept off the rounded corners, and the tip
  is the anchor exactly (the AC's 40 px is 0 by construction); the outline is one SVG
  path (body plus tail) so fill and stroke meet with no seam; a thought bubble has no
  tail and three dots (14, 10, 6 px) along the line from the body's edge to the anchor.
  `BubbleSpec` carries the lines, body box, radius, tip, path, dots, Poppins 800, the
  row's fill and ink, a 5 px outline, `scale_from` 0.5, `at_s` / `pop_s` / `until_s` (the
  beat's end or `hold_max_s`).
- **Remotion** (`components/bubble.tsx`, registered as `bubble`): hidden before `at_s`
  and from `until_s`, a back-eased overshoot (`Easing.back(1.6)`) about the body's
  centre, the path and dots in an SVG over the frame, the lines centred in the body.
  Drawn in `Short.tsx` after the text pops and before the captions. `types.ts` gains
  `BubbleSpec` / `BubbleDot` and `BeatSpec.bubbles`.
- **T12** judges bubble bodies against the 6.3 zones and counts them ("..., 0 text pops,
  2 bubbles: none inside ..."); the tail may point into a zone (at the circle). **T6**
  takes its `pop` trigger beats from `technical.pop_in_beats` (text pops or bubbles).
  **Sound**: `landing_s` lands a beat with no event on its first text pop, else its
  first bubble.
- **job.log**: `pipeline.bubble_lines` writes one line per bubble of the validated plan
  at `planning` (`bubble: b04: speech 'Hello there?' from words 0-1 'hello there' (063)`),
  so every bubble's words can be checked against the recording.
- **Fake planner** (`FAKE_BUBBLES`): under a style whose `bubbles_max_per_60s` is over 0,
  b04 (the card beat with the stamp, 1.5-2.0 s) carries a speech bubble of words 0-1
  pointing at the top of the PIP circle (19.4 %, 50 %) and a thought bubble of words 2-3
  over the card (62 %, 30 %); the stamp stays the landed event, so the sound story is
  unchanged. Under every existing style nothing changes.
- **Planner prompt v11** (`picture_v11.md`, `sound_v11.md`; snapshots recorded by a
  throwaway script under work/): the bubbles paragraph (speech / thought, words only
  from the recording in one line, `first`-`last`, the tail's `{x, y}` and where the
  circle's top sits, the dialogue pair and its gap, the caps, never `at_s`, not a landed
  event) and the sound file's wording (an `event` cue may hit a bubble; a whoosh may
  ride it).
- **Smoke**: `python -m shortsmith.smoke --bubbles` runs the walk under the style's
  `bubbles_on` copy; `check_bubbles` asserts the pair in the plan (landings 1.5 and
  1.7 s), in the render spec (the row's look, tips on the anchors, bodies inside the
  zones and off the circle, the stamp and each other, the thought trail), T12's count,
  and job.log's source-word lines with nothing dropped; the plain walks assert none. The
  summary line gains "bubbles N".
- Docs: `docs/components.md` gains the `bubble` row; `styles/README.md` names the cap and
  the row; the explainer's B-roll prose states the rule (off here).
- Tests: contracts, styles (row and cap in every spec, loader refusals, the test-style
  helper, the fixture gap scaling), grammar (landings, the pair inside / at the edges of
  the window, too short for a pair, caps, word count, source words, kinds, density, the
  pop cue and the whoosh), sound, gate (`pop_in_beats`, T12), render (anchor and tail
  tip, thought trail, tail side, the pair apart and 0.6 s apart, wrap / shrink / fail,
  moved off the band, the circle and a face, dropped, the fake pair through the grammar
  clear of the stamp, a real Remotion render with white bodies after the landing), fake
  planner, prompt v11 needles and snapshots, pipeline (the job.log lines), smoke
  (`--bubbles` through `main`, the walk end to end), Node registry tests.

Loops (all foreground, all seen, after the last source edit): ruff clean, pyright clean,
every one of the 51 test files green in five chunks (33 unit files 959 passed 1:25; gate
/ sound / presenter / transcriber 12 files 391 passed 2:08; pipeline / app / jobs 184
passed 3:57; render 152 passed 3:37; smoke 16 passed 6:58), smoke explainer 55.4 s, smoke
hitech 55.4 s, smoke `--bubbles` 57.4 s, smoke `--text-pops` 56.9 s, each T1-T13 pass;
out/qa.json of a kept `--bubbles` run read by hand (T12: "10 caption words, 2 stamps, 0
lower-thirds, 0 text pops, 2 bubbles: none inside the reserved zones") and its contact
sheet and the 1.85 s frame looked at: both bodies clear of the stamp, the circle and the
captions, the tail on the circle, the trail on its anchor; `npm run typecheck` clean;
`npm test` 24 passed.

What to look at on the next real job: nothing changes until a style turns bubbles on
(059's recipe styles). On that run: whether the planner's bubble words really are the
recording's (the `bubble:` lines in job.log beside the transcript words), whether the
tail points at the right person or the circle, whether the pair's second bubble lands
where the answer is said (or gets pulled to the window's edge), how many `bubble:` moved
/ dropped lines there are, and whether a thought bubble's trail crosses a stamp (the
fake's does on the fixture: its anchor sits on the stamp's top edge; the body is kept
off it). The thought body is a rounded pill, not a scalloped cloud: the operator's phone
verdict decides whether it needs scallops.

Notes for 062 / 059: `bubble_spec`'s obstacle list (circle, band, stamp, face, anchor
keep-out, earlier bubble) and the `place_text_pop` search are the pattern for the
sticker; `pop_in_beats` is where a sticker's beat joins the `pop` trigger. 059 sets
`broll.bubbles_max_per_60s` and may tune the `bubble` row per recipe.

Amendment lines for `docs/grill-decisions.md` (operator pastes):

- 4.1 — AMENDED by 063 (28 Sep 2026): a picture beat (`photo`, `card`, presenter full;
  `clip` when 058 lands) may carry `bubbles`: `speech` or `thought` bubbles of 1 to
  `broll.motion.bubble.words_max` (7) words that the recording itself carries - what
  the speaker says someone said or thought, or the speaker's own question, shortened
  or in the caption language, never a quote the recording does not carry - with
  `first`-`last` naming the transcript words the text came from (written to job.log
  beside the text) and the tail pointing at `{x, y}` in percent of the frame (a person
  in the picture, or the PIP circle when the presenter is the one asking). Code writes
  the landing: the first source word's output time, or the beat's start when the words
  came earlier; at most `motion.bubble.max_per_beat` (2) per beat, a dialogue pair's
  second bubble landing `motion.bubble.dialogue_gap_min_s`-`dialogue_gap_max_s`
  (0.6-1.2 s) after the first (a beat too short for that is rejected); at most
  `broll.bubbles_max_per_60s` per 60 s (rounded up), both enforced by the grammar; the
  four existing styles set the cap to 0 (off), the 059 recipe styles set theirs. Code
  keeps the body inside the safe area and moves it off the captions, the PIP circle,
  the stamp, any detected face (the image's, or the presenter's on a full beat), the
  anchor itself and the beat's other bubble, logging the move; with a face in the way
  and no free spot the bubble is dropped and logged. The text shrinks from
  `motion.bubble.size_px` to `min_size_px` to fit `width_px`; below that the build
  fails naming the beat. A bubble is not the beat's one landed event (3.1); it is a
  change on screen for the density rule. A bubble may carry a pop cue at its landing
  under the 7.3 caps, or a whoosh under 7.3 as amended by 060 with `pop` in
  `sound.whoosh.on`.
- 9.2 — AMENDED by 063 (28 Sep 2026): the registry gains `bubble` (a speech bubble: a
  white rounded body with a tail to its anchor; a thought bubble: the body with a
  trail of three dots; Poppins 800 in `motion.bubble.ink` on `motion.bubble.fill`, a
  dark outline, a back-eased overshoot from 0.5 over `motion.bubble.duration_s`
  (0.15-0.25 s), on screen to the end of its beat or `motion.bubble.hold_max_s`),
  drawn over the PIP circle and the text pops and under the captions. Every spec
  carries the `motion.bubble` row and the cap; a style requires the component only
  when it turns bubbles on.
