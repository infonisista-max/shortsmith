# 055 — The short opens with the speaker's own first words, over the strongest images

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

Operator decision, 27 Sep 2026 — amends 3.4 (hook) and the cold-open lift in 8.1, for
every style. The operator records his scripts as finished storytelling; the edit must not
re-order or drop what he says.

- The short starts with the first spoken word of the recording. No cold-open lift: no
  line is moved from anywhere else to the front, and nothing spoken is dropped. F1
  (job `20260927-041728-656506`) lifted "Steve Jobs भी इस बाबा के fan थे" from 22.7 s to
  the front and dropped it from its place; that must no longer be possible.
- `cut` may remove only silence, breaths and dead air: every transcript word appears in
  the output exactly once, in its original order. Long pauses between sentences are
  tightened to a new `cut.max_pause_s` in each style's front matter (no style has a
  pause number today; propose explainer's value in the plan and say why).
- The opening (the first spoken sentence, up to about 5 s) is two or three quick beats in
  `pip` mode: the speaker in the circle, full-screen images behind, normal captions. No
  hook title and no hook cards.
- Those opening images are the short's strongest images of its main subject: the
  owner's reference image first; else the best-scored sourced image of the main subject
  (a named person, place or product follows 053's rules; a thing or idea, e.g. cheese,
  may come from any source including the stock libraries); else a generated image
  (5.5) — never a rung-3/4 fallback. Topics are not only people.
  The planner chooses the most striking, most relevant visual for the opening line; the
  brief's "hook wish" steers what the images show, never the order of the voice.
- The hook fields that exist only for the lift (`cold_open_span`, `original_position`,
  hook title, hook card ids) leave the plan, the prompt, the validator and the styles'
  front matter. The planner prompt version goes up by one.

## Acceptance criteria

- [x] The validator rejects any plan whose kept spans re-order speech or drop a word:
      each transcript word appears once, in order (F1's plan, replayed against the new
      rule, is rejected and names the lifted span).
- [x] The first beat starts at the first word's start (within the snap window); the
      opening beats are `pip` over full-screen images; no `hook_cards` beat exists in
      any style.
- [x] Opening-beat sourcing order is owner refs → best-scored sourced image of the main
      subject → generated; a fixture with an owner image shows it in the first beat, and
      a concept-topic fixture (no named person) gets a sourced or generated image of its
      subject, never a rung-3/4 fallback.
- [x] Pause tightening only removes non-speech: no gap between kept words exceeds
      `cut.max_pause_s`, and no word's audio is shortened, tested on the F1 transcript.
- [x] Every style spec (explainer, educational, animated, hitech) follows the new
      opening; `version` bumped where the front matter changed.
- [x] Planner prompt v7 states the rule in one short paragraph; the fake planner
      follows it; ruff, pyright, all test files green in foreground chunks, smoke
      explainer and hitech T1–T13.
- [x] Done note: the amendment lines for 3.4 and 8.1 for the operator to paste into
      `docs/grill-decisions.md`.

## Done note (27 Sep 2026)

What shipped, rule by rule:

1. **The speaker's order.** `grammar._speech` runs before every other rule: `cut.keep`
   must be listed in recording order, every transcript word must lie whole inside a kept
   span and outside every drop (a 5 ms edge tolerance), else the plan is rejected at plan
   level naming the span and the words. F1's lift, replayed as `keep = [22.74-24.1,
   0-22.74, 24.1-59.93]`, is rejected with "22.74-24.1 s is listed after ..."; as
   `drop = [22.74-24.1]` it is rejected with "removes or cuts into spoken words 'आप यकीन
   नहीं मानोगे' (22.74-24.1 s)". The F1 transcript is the fixture
   `tests/fixtures/f1/transcript.json` (text and times only).
2. **Pause tightening is code's** (`presenter.tighten`): a pause between two kept words
   longer than `cut.max_pause_s` keeps `max_pause_s` of itself, half on each side; the
   head before the first word keeps at most `beats.snap_window_s`; the tail and any
   pause the planner already cut into are left alone; no word is ever shortened. The
   validator logs one 3.4 clamp naming every trim and writes the tightened spans as the
   validated plan's `cut.keep`. On F1: one pause (0.74 s after 'खिलाओ' at 19.06 s),
   0.14 s removed, every word kept once in order.
   **Explainer `cut.max_pause_s` = 0.6 s.** Why: a spoken sentence boundary in
   conversational Hindi/Hinglish runs 0.3-0.6 s; the pager already breaks a caption page
   at 0.35 s (`gap_break_s`), so 0.6 leaves one page break and a breath between
   sentences without a hole; anything longer reads as dead air on a Short. F1's second
   longest pause is 0.56 s and stays. Educational is 0.8 s (a teacher's pause), the
   other two 0.6 s. Every style bumps `version` to "3".
3. **Beats are written on the recording's timeline and mapped by code.** The v6 prompt
   already said "recording's timeline" while the validator read output seconds (F1's
   planner did the output arithmetic because the lift forced it). Now `grammar._on_output`
   maps every boundary through the tightened cut (`presenter.output_time`); the first
   beat owns the lead before the first word; a beat wholly inside removed audio is
   rejected. The validated plan's beats are output seconds, so the renderer, captions
   and T3/T10 are unchanged. T8's re-validation passes `timeline="output"` so nothing
   is mapped twice; the pipeline uses the default `"recording"`.
4. **The opening** (`grammar._opening`; front matter `beats.opening_beats_min: 2`,
   `opening_beats_max: 3`, `opening_max_s: 5.0`, `presenter.opening_mode: pip`): the
   first two beats are `pip` over a `photo` or `card` with an asset, the second ending
   by 5 s; with owner references the first beat's asset must be one of them (the
   validator now takes `references`). No hook object, no `hook_cards` kind, no
   `cold_open` reason, no hook-wish warning: `Hook`, `HookCardsSpec`, `BeatSpec.hook`,
   `render.hook_spec`/`title_lines` and the `beats.cold_open_*`/`hook_*` and
   `presenter.hook_modes` keys are gone. The Node `hook_cards` component stays exported
   (no file under `src/remotion` changed; removing it means its registry test and the
   npm loops, a follow-up) and its row in `docs/components.md` reads `retired`.
5. **Opening sourcing** (`assets.source_opening`): owner reference (named by the plan or
   matched by caption, as before) → `best_search`: every source in the order is asked
   and the highest judge score wins, ties by source order (053's stock ban still applies
   to named entities) → generation, forced past `gen_max_per_short` (11.3) → never
   rung 3/4: with nothing found and no generator the step raises `AssetError` naming the
   beat and the job fails at `sourcing` visibly. The finale's cards are now the short's
   first three distinct images (`broll.motion.finale.cards: 3`, `render.opening_asset_ids`).
6. **Prompt v7** (`picture_v7.md`; the sound file is v6 verbatim): one paragraph, "the
   speaker's order", plus the opening and the cut rules; snapshots recorded. Fake plan:
   b01 pip photo (the owner's first reference when the request has one), b02 pip card,
   b03 full `emotional_line`, b04 pip photo with the stamp; the smoke's scaled spec
   widens `snap_window_s` to 0.2 and `cut.max_pause_s` to 0.8 so the 0.7 s bursts and
   the 0.2 s head leave the six-second clip whole.

Loops: ruff, pyright, every test file green in foreground chunks (333 + 290 + 188 +
695 + 106 + the re-runs of the fixed tests), smoke explainer and hitech T1-T13 pass;
`out/qa.json` read on both; the explainer contact sheet shows b01/b02 in pip over the
photo and the card, b03 the one punch-in, the finale with three cards and no title.

What to look for on the next real job:

- `work/plan.raw.json`: `cut.keep` from 0 to the recording's end, `cut.drop` only in
  silence, no `hook`; `job.log` "picture plan rejected" lines quoting a 3.4 speech or
  opening violation mean the planner still wants to lift or title.
- `work/plan.validated.json`: `cut.keep` is the tightened list; the 3.4 clamp names
  each pause it tightened; beats[0].start is 0 and the first two beats are pip
  photo/card.
- `out/contact.jpg`: the first frames show the speaker in the circle over the subject's
  image, no title card; the finale's cards are the opening's images.
- `job.log` at `sourcing`: no "opening beat ... has no image" failure; if one appears,
  the queries for the opening beats are the thing to fix, not the rule.

Amendment lines for `docs/grill-decisions.md` (operator to paste):

- 3.4 — AMENDED by 055 (27 Sep 2026): the two-beat hook is withdrawn for every style.
  The short starts with the first spoken word of the recording; no line is lifted from
  elsewhere, nothing spoken is dropped, no hook title, no hook cards. The opening is the
  speaker's first sentence, up to about `beats.opening_max_s` (5 s), as
  `beats.opening_beats_min`-`opening_beats_max` (2-3) quick `presenter.opening_mode`
  (`pip`) beats over full-screen images of the main subject with normal captions. The
  opening images are the short's strongest: the owner's reference first, else the
  best-scored sourced image of the main subject (a named person, place or product under
  5.1/053, a thing or idea from any source), else a generated image (5.5), never a 4.4
  rung-3/4 rescue; the brief's hook wish steers what they show, never the order of the
  voice. `cut` removes only silence, breaths and dead air: every transcript word appears
  once, in order; the validator rejects a plan whose kept spans re-order speech or drop a
  word, naming the span. Pauses between kept words longer than the style's
  `cut.max_pause_s` (explainer 0.6 s) are tightened by code, half kept on each side; the
  head before the first word keeps at most the snap window. The fields `hook.title`,
  `hook.cold_open_span`, `hook.original_position`, `hook.card_asset_ids`, the
  `hook_cards` kind and the `cold_open` reason leave the plan, the prompt, the validator
  and the styles' front matter; the finale's cards are the short's first images.
- 8.1 — AMENDED by 055 (27 Sep 2026): `PicturePlan` has no `hook`; `cut` is kept and
  dropped spans of the recording with drops only in silence (the cold-open lift is
  withdrawn). Beat times are written in recording seconds; the validator maps them onto
  the tightened cut, so a validated plan's beats are output seconds and its `cut.keep`
  is the tightened list. The planner prompt is v7.

## Blocked by

- Nothing.

## User stories addressed

- Operator, 27 Sep 2026: "script starts the way I speak; at the start just use the most
  relevant, most interesting images in the background; script and voice remain the same".
