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

- [x] A fixture photo beat with two text pops renders; a frame after each landing shows
      the text's fill colour in its box at the given position; a pop placed on the PIP
      circle or the caption band is moved inside the allowed area or fails the build
      naming the beat (say which in the done note).
- [x] Landing time within ±0.15 s of the word's transcript time (transcript fixture).
- [x] A pop whose box covers a detected face is moved or dropped and `job.log` says so.
- [x] Caps enforced by the grammar validator; with 0 in a style any text pop fails
      validation naming the beat.
- [x] Planner prompt version bumped by one; under a test style with text pops on, the
      fake planner emits one pop and the smoke renders it; smoke explainer and hitech
      pass T1–T13 unchanged.
- [x] `npm run typecheck`, `npm test`, ruff, pyright, every test file green in foreground
      chunks.
- [x] Done note: the amendment lines for 4.1 and 9.2 for the operator to paste.

## Blocked by

- `issues/056-run03-findings.md` (its never-on-a-face rule for overlays is reused here; the
  face detector is `presenter.py`'s).

## User stories addressed

- Operator, 27 Sep 2026 (run03): "every video same style"; "pop-up images are small".
- Operator, 25 Sep 2026: the system must learn effect vocabulary from the references.

## Done note (28 Sep 2026)

What changed:

- **The plan** (`contracts.TextPop`, `Beat.text_pops`): a picture beat may carry a list
  of pops, each `{text, word, x, y, anchor, fill}` - the words, the transcript word index
  the pop lands on, the point in percent of the frame, `left | center | right`, and
  `yellow | white | accent`. `at_s` is on the model too but written by the grammar (the
  word's start on the output timeline, mapped through the cut like beat boundaries); the
  planner is told never to write it. `text_pop` is not a `Kind` or an `OverlayKind`: it
  is enabled by a style's numbers, like `flash`, so the fake plan under every existing
  style is byte-identical and the "every tier-1 kind named" tests hold.
- **Front matter** (every style, `version` 6 → 7): `broll.text_pops_max_per_60s: 0` (the
  loader requires it) and a `broll.motion.text_pop` row `{kind: pop, duration_s,
  hold_max_s: 2.5, max_per_beat: 2, tilt_deg, size_px, fill}` (explainer 0.2 s, 6°,
  96 px, `#FFD60A`; the drafts vary the overshoot, tilt and size), which
  `render.broll_numbers` requires like the other rows. None of the four styles turns pops
  on; 059's recipe styles set their caps. `fixture.pops_on(spec)` is the copy with the
  cap at 10 (one pop on the six-second fixture) that the tests (`conftest.text_pop_style`)
  and the smoke's `--text-pops` judge and render under.
- **Grammar** (`grammar._text_pops`, `text_pop_cap`): a pop sits on a `photo`, `card` or
  presenter-full beat only; 1–4 words; at most `motion.text_pop.max_per_beat` per beat
  and ceil(`text_pops_max_per_60s` × runtime / 60) over the short (0 stays 0, so under
  every existing style any pop is a 4.1 violation naming the beat); the word index must
  exist and its output time must fall inside the beat; every violation names the beat
  and rule 4.1. A beat with pops counts as changing on screen for the 3.1 density rule.
  `validate_sound`: a beat with no landed event but pops is not bare, so an `event` cue
  may hit the pop; a `whoosh` at `event` on such a beat passes 7.3 when `pop` is in
  `sound.whoosh.on` (the 060 hook, now wired); at `start` it is refused.
- **Render** (`render.text_pop_spec`, `place_text_pop`, `presenter_face_box`): the words
  measured at Poppins 900 `size_px` (shrunk in 4 px steps to fit the safe width), the
  box at the planner's point, tilted ±`tilt_deg` alternating per pop, clamped into the
  safe area (top 250 px to bottom 320 px, the rails), then, when it lands on an obstacle -
  the PIP circle on a `pip` beat, the caption band (the block's top edge down), a face -
  moved to the nearest free spot among the spots beside each obstacle and the image's
  face-free bands (upper third, lower third, below), 24 px clear. **The choice the AC
  asked for: a pop on the circle or the captions is moved, not failed**; one `text pop:`
  line in job.log names the beat, the words, what it cleared and where it went. No free
  spot: with a face in the way the pop is dropped and logged ("dropped, no spot clear of
  the face ..."); with no face the build fails naming the beat (that would mean the whole
  safe area is circle and captions, which no style's geometry allows). The face is the
  3.3 detector's on the beat's image (the 056 machinery, `face_on`), or on a `full` beat
  the measured presenter face from `job.json.presenter` through the punch-in's widest
  scale (`presenter_face_box`; `build_spec(presenter_face=...)`, passed by
  `spec_for_job`). Timing: `at_s` seconds into the beat (0 when the grammar never wrote
  it, i.e. an unvalidated plan), `pop_s` = the row's `duration_s`, `until_s` = the beat's
  end or `at_s + hold_max_s`, whichever is first. `TextPopSpec` carries the fill colour
  (`yellow` → the row's `fill`, `white` → white, `accent` → `palette.accent`), a 6 px dark
  outline and a 6 px drop.
- **Remotion** (`components/text_pop.tsx`, registered as `text_pop`): hidden before
  `at_s` and from `until_s`, a back-eased overshoot (`Easing.back(2.0)`) from
  `scale_from` 0.4 to 1 over `pop_s`, `-webkit-text-stroke` with `paint-order: stroke
  fill` for the outline plus the drop shadow, rotated by `rotate_deg`. Drawn in
  `Short.tsx` after the PIP circle and before the captions (it is placed clear of both).
- **Sound**: `sound.landing_s` - a beat with no landed event and pops lands where its
  first pop does, so an `event` cue (the fake's `popup_tick`) fires on the pop; no floor
  hit is earned by a pop (7.1 unchanged). **T6**: `whoosh_faults(..., pops=...)` accepts
  a whoosh on a beat carrying pops when `pop` is a trigger; `run` passes the plan's pop
  beats. **T12**: text pop boxes are judged against the reserved zones and counted in the
  detail ("..., 1 lower-third, 0 text pops: none inside ...").
- **Fake planner**: under a style whose `text_pops_max_per_60s` is over 0, b03 (the
  presenter full beat, 1.0–1.5 s) carries one pop, "THIS", on word 2 ("this" at 1.2 s),
  at (50 %, 42 %), and the sound story cues `popup_tick` at its event; under every
  existing style nothing changes.
- **Planner prompt v10** (`picture_v10.md`, `sound_v10.md`; snapshots recorded by a
  throwaway script that builds the prompt exactly as the snapshot test does): the text
  pop paragraph (what, where, `word`, `fill`, the caps, never `at_s`, not a landed
  event) and the sound file's pop-in wording (an `event` cue may hit a pop; a whoosh may
  ride it with `pop` in `sound.whoosh.on`).
- **Smoke**: `python -m shortsmith.smoke --text-pops` runs the walk under the selected
  style's `pops_on` copy; `check_text_pops` asserts b03's pop in the plan (`at_s` 1.2),
  in the render spec (the row's look, landing 0.2 s into the beat, inside the zones, T12
  counting it, no `text pop: ... dropped` line); the plain walks assert no pop and T12's
  "0 text pops". The summary line gains "text pops N".
- Docs: `docs/components.md` gains the `text_pop` row; `styles/README.md` names the cap
  and the row; the explainer's B-roll prose states the rule (off here).
- Tests: contracts (the model, bounds, schema), styles (row and cap in every spec,
  loader refusals, the test-style helper), grammar (pass and `at_s`, mapped through a
  tightened pause, cap 0, per-beat and per-60 s caps scaled 56 s / 6 s, word outside the
  beat, word count, kinds, presenter full, the pop cue and the whoosh on a pop), fake
  planner (one pop + cue under the pops style, none under explainer, passes the grammar,
  `at_s` 1.2), prompt v10 needles and snapshots, render (placement and look, hold, moved
  off the circle and the band with log lines, moved off a photo's face / dropped when the
  face fills it, moved off the presenter's face on a full beat, landing within 0.15 s of
  the word through the grammar, and a real Remotion render of b01 with two pops: no fill
  pixels before the landing, yellow then white pixels in each box after), sound (the
  event cue fires at the pop), T6 (pop trigger, `on: [flash]` refusal), T12 (count, top
  zone, right rail), smoke (`--text-pops` flag through `main`, the pops walk end to end
  with T1–T13), Node registry tests (registered, drawn over the pip and under the
  captions, every number read from the spec, the overshoot).

Loops (all foreground, all seen): ruff clean, pyright clean, every one of the 51 test
files green in five chunks after the last source edit (26 unit files 809 passed 0:29;
gate / sound / presenter 15 files 429 passed 2:44; pipeline / app / jobs 8 files 286
passed 4:14; render 143 passed 3:06; smoke 8 passed 6:00), smoke explainer, smoke hitech
and smoke `--text-pops` T1–T13 pass (times in the commit message), `npm run typecheck`
clean, `npm test` green.

What to look at on the next real job: nothing changes until a style turns pops on
(059's recipe styles). On that run: pop count against the cap, whether each pop lands on
the word it names (the ±0.15 s is exact by construction; the phone check is whether the
planner picked the right `word`), where the pops sit (near the thing they name, off the
face and the circle), the `text pop:` lines in job.log (how many were moved, any dropped),
and whether the planner keeps to 1–4 words.

Notes for 062 / 063 / 059: `place_text_pop` (the obstacle list, the nearest-free-spot
search, the image bands) and `presenter_face_box` are reusable for stickers and bubbles;
`TextPop.at_s` written by the grammar is the pattern for any overlay that lands on a
word. `whoosh_faults(pops=...)` and `validate_sound`'s `on_pop` are where the sticker's
and bubble's pop-ins join the `pop` trigger. 059 sets `broll.text_pops_max_per_60s` and
may tune the `text_pop` row per recipe.

Amendment lines for `docs/grill-decisions.md` (operator pastes):

- 4.1 — AMENDED by 061 (28 Sep 2026): a picture beat (`photo`, `card`, presenter full;
  `clip` when 058 lands) may carry `text_pops`: 1–4 words from the script (the name,
  number or term being said) at `{x, y, anchor}` in percent of the frame near the thing
  they name, each landing on its spoken `word` (the transcript index; code writes the
  output time), `fill` yellow, white or the palette accent. At most
  `broll.motion.text_pop.max_per_beat` (2) per beat and `broll.text_pops_max_per_60s`
  per 60 s (rounded up), both enforced by the grammar; the four existing styles set the
  cap to 0 (off), the 059 recipe styles set theirs. Code keeps a pop inside the safe
  area and moves it off the PIP circle, the caption band and any detected face (the
  image's, or the presenter's on a full beat) to the nearest free spot, logging the
  move; with a face in the way and no free spot the pop is dropped and logged. A pop is
  not the beat's one landed event (3.1); a pop is a change on screen for the density
  rule. A pop may carry a hit or pop cue at its landing under the 7.3 caps, or a whoosh
  under 7.3 as amended by 060 with `pop` in `sound.whoosh.on`.
- 9.2 — AMENDED by 061 (28 Sep 2026): the registry gains `text_pop` (Poppins 900 in the
  style's `motion.text_pop.fill`, white or the accent, a thick dark outline and drop
  shadow, a back-eased overshoot from 0.4 over `motion.text_pop.duration_s`
  (0.15–0.25 s), tilted up to `motion.text_pop.tilt_deg` (≤ 8°) alternating, on screen to
  the end of its beat or `motion.text_pop.hold_max_s` (2.5 s)), drawn over the PIP circle
  and under the captions. Every spec carries the `motion.text_pop` row and the cap; a
  style requires the component only when it turns pops on.
