# 008 — Style specs rebuilt, loader, resolver, live resolution on the upload form

## Type

HITL — needs new package: `pyyaml` (`uv add pyyaml`). It is present transitively through `uvicorn[standard]` but not declared in `pyproject.toml`; the board rule says declare it via `uv add`. The operator approves; then this ticket becomes AFK. Later YAML consumers (011 prices, 022 catalogue) are blocked by this ticket.

## Parent PRD

`issues/prd.md`

## What to build

Rebuild the four style drafts under `styles/` as YAML front matter plus the five prose sections, with the seven key groups and `status`, and write the loader that validates them at startup, the resolver that maps a free-text style line to one spec, and the upload form's live resolution with the draft notice. Only `explainer` is `shipped`; the other three are `draft`. The renderer and QA read only numbers; the planner reads numbers and prose.

The style drafts' forbidden lists are rewritten per 7.1: chimes and ticks are removed as hard bans (ticks become a planner cue choice under the 7.3 caps); sweeps and risers stay banned. `explainer.requires_components` lists only components that exist in the renderer registry at this point (`captions`, `pip`); ticket 030 completes it.

Covers PRD `styles`, the style chips and live resolution on `app`, and the "Overrides to project rules" line about the drafts. Decisions 1.1, 1.2, 1.3, 1.4, 3.1, 3.2, 3.3, 4.1, 4.3, 5.6, 6.1, 6.2, 6.3, 7.1, 7.3, 9.2, 9.4.

## Acceptance criteria

- [ ] `styles/{explainer,educational,animated,hitech}.md` each carry front matter with `aliases`, `beats`, `presenter`, `broll`, `captions`, `sound`, `finale`, plus `status`, `requires_components`, `budget`, `pip.chin_anchor`, `pip.large_face_diameter`, and the explainer numbers from 3.1, 3.2, 3.3, 4.1, 4.3, 5.6, 6.1, 6.2, 6.3, 7.3, 9.4; five prose sections follow.
- [ ] Every `sound.forbidden` list bans sweeps and risers and no longer bans chimes or ticks; `docs/grill-decisions.md` 7.1 is cited in the explainer prose.
- [ ] `styles.load_all(registry) -> dict[str, StyleSpec]` fails at startup with the spec name and the missing key group; asserts `pip.top + pip.diameter <= captions.anchor_y − captions.max_lines × line_height`; asserts every `requires_components` entry exists in the renderer registry when `status: shipped`.
- [ ] `styles.resolve(line) -> Resolution(name, note, notice)` scores alias hits, highest wins, zero hits or tie → `explainer`; an alias of a draft spec resolves to `explainer` with notice "<name> not available yet, using explainer"; the full line is the style note.
- [ ] Upload form shows shipped-style chips and resolves the style field live (fetch to `GET /styles/resolve?line=`) showing the resolved name, note and notice before submit; `POST /jobs` stores `style`, `style_note` and `style_notice` on `job.json`.
- [ ] `app` startup loads all specs; a broken spec stops the app with a config error.
- [ ] Boundary tests, `tests/test_styles.py`: missing key group, draft never resolves as shipped, PIP/caption collision assert fires on a colliding spec, `requires_components` names a component absent from the registry; resolver: alias hit, tie, zero hits, draft redirect notice.
- [ ] Planner PlanRequest now carries the loaded spec (numbers + prose) and `style_note`; FakePlanner still passes smoke.

## Blocked by

- Blocked by `issues/006-t1-t4-contact-sheet-delivered.md`

## User stories addressed

- User story 2
- User story 3
- User story 10
- User story 65
