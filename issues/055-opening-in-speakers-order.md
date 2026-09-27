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

- [ ] The validator rejects any plan whose kept spans re-order speech or drop a word:
      each transcript word appears once, in order (F1's plan, replayed against the new
      rule, is rejected and names the lifted span).
- [ ] The first beat starts at the first word's start (within the snap window); the
      opening beats are `pip` over full-screen images; no `hook_cards` beat exists in
      any style.
- [ ] Opening-beat sourcing order is owner refs → best-scored sourced image of the main
      subject → generated; a fixture with an owner image shows it in the first beat, and
      a concept-topic fixture (no named person) gets a sourced or generated image of its
      subject, never a rung-3/4 fallback.
- [ ] Pause tightening only removes non-speech: no gap between kept words exceeds
      `cut.max_pause_s`, and no word's audio is shortened, tested on the F1 transcript.
- [ ] Every style spec (explainer, educational, animated, hitech) follows the new
      opening; `version` bumped where the front matter changed.
- [ ] Planner prompt v7 states the rule in one short paragraph; the fake planner
      follows it; ruff, pyright, all test files green in foreground chunks, smoke
      explainer and hitech T1–T13.
- [ ] Done note: the amendment lines for 3.4 and 8.1 for the operator to paste into
      `docs/grill-decisions.md`.

## Blocked by

- Nothing.

## User stories addressed

- Operator, 27 Sep 2026: "script starts the way I speak; at the start just use the most
  relevant, most interesting images in the background; script and voice remain the same".
