# 030 — Transition vocabulary in the renderer, style subsets, explainer registry complete

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

The six global enter transitions implemented once in the renderer with exit always `cut` or `fade`, each style enabling a subset in front matter, and the explainer's `requires_components` completed with every tier-1 component so the `shipped` registry check passes with the full list. The grammar already rejects names outside the style list and enforces whip spacing; this ticket makes the renderer honour `enter` per beat and proves the whole tier-1 set exists.

Covers PRD render (transitions), "Global contracts" transition vocabulary, `styles` registry check completion. Decisions 9.4, 9.2, 4.1, 1.4.

## Acceptance criteria

- [ ] Transitions: `cut`, `fade` 0.35 s, `whip` 0.22 s with 14 px directional blur, `zoom` 0.3 s from 1.6, `spring` fly-in (damping 14, stiffness 160, mass 0.7), `wipe` 0.25 s; the next beat's enter carries the motion; exit is `cut` or `fade` only.
- [ ] Style front matter `broll.enter_transitions`: explainer cut/fade/whip/zoom/spring, hitech cut/fade/wipe/zoom, educational cut/fade, animated all six; the renderer refuses a transition outside the beat's style list (defence in depth behind the grammar).
- [ ] No transition triggers a cue (the sound director ignores transitions; test on a plan with a whip on every beat and no events → zero cues beyond the floor).
- [ ] The registry lists captions, pip, photo, card, stamp, lower_third, hook_cards, finale, list, chart, split, wall, infographic, label_flyin, counter and the six transitions; the explainer's `requires_components` lists all of them and loads as `shipped`.
- Rejoin note (board audit 2026-09-25): the four map components `map`, `pin_drop`, `route_arrow` and `object_path` are out of this ticket's list because 020 was demoted to ordinary HITL maps work and blocks nothing. They remain 9.2 tier-1 scope under 020/028 and rejoin the registry and the explainer's `requires_components` when those land; if unfinished at the day-14 gate, 047 reports each of the four by name as `incomplete`.
- [ ] A test removes one component from a copy of the registry and asserts the explainer fails to load.
- [ ] Smoke: FakePlanner's plan uses each of the five explainer transitions at least once; gates pass; smoke time recorded in the commit message.

## Notes from 008

- `styles.load_all` already cross-checks `requires_components` against `render.registry()` for `status: shipped` specs (a missing one fails startup naming it). `explainer.requires_components` is `[captions, pip]` today; extend it as components land. Each spec's `broll.enter_transitions` and `whip_max_per_3_beats` are typed on `styles.Broll`.

## Notes from 009

- The grammar rejects `enter` names outside `broll.enter_transitions` (9.4) and enforces `whip_max_per_3_beats` plus never-two-in-a-row, and the sound check rejects a `start` cue on a non-`cut` enter without a landed event. The fake plan's `wipe` on b05 became `fade`, so it now uses each of the five explainer transitions at least once (cut, fade, whip, spring, zoom); the smoke acceptance line above is already true. Spec edits (`styles/*.md`) were left to this ticket.

## Blocked by

- Nothing; 027 and 029 are done, 028 follows the demoted 020 maps track (see the rejoin note above).

## User stories addressed

- User story 25
- User story 65
