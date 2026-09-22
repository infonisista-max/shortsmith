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

- [x] `styles/{explainer,educational,animated,hitech}.md` each carry front matter with `aliases`, `beats`, `presenter`, `broll`, `captions`, `sound`, `finale`, plus `status`, `requires_components`, `budget`, `pip.chin_anchor`, `pip.large_face_diameter`, and the explainer numbers from 3.1, 3.2, 3.3, 4.1, 4.3, 5.6, 6.1, 6.2, 6.3, 7.3, 9.4; five prose sections follow.
- [x] Every `sound.forbidden` list bans sweeps and risers and no longer bans chimes or ticks; `docs/grill-decisions.md` 7.1 is cited in the explainer prose.
- [x] `styles.load_all(registry) -> dict[str, StyleSpec]` fails at startup with the spec name and the missing key group; asserts `pip.top + pip.diameter <= captions.anchor_y − captions.max_lines × line_height`; asserts every `requires_components` entry exists in the renderer registry when `status: shipped`.
- [x] `styles.resolve(line) -> Resolution(name, note, notice)` scores alias hits, highest wins, zero hits or tie → `explainer`; an alias of a draft spec resolves to `explainer` with notice "<name> not available yet, using explainer"; the full line is the style note.
- [x] Upload form shows shipped-style chips and resolves the style field live (fetch to `GET /styles/resolve?line=`) showing the resolved name, note and notice before submit; `POST /jobs` stores `style`, `style_note` and `style_notice` on `job.json`.
- [x] `app` startup loads all specs; a broken spec stops the app with a config error.
- [x] Boundary tests, `tests/test_styles.py`: missing key group, draft never resolves as shipped, PIP/caption collision assert fires on a colliding spec, `requires_components` names a component absent from the registry; resolver: alias hit, tie, zero hits, draft redirect notice.
- [x] Planner PlanRequest now carries the loaded spec (numbers + prose) and `style_note`; FakePlanner still passes smoke.

## Session notes (done)

- Dependency pinned exactly per the operator's rider: `pyyaml==6.0.3` (already present transitively through `uvicorn[standard]`, now declared). It is the only new package. Pyright types `yaml` from its bundled typeshed stubs; no stub package was added.
- New module `src/shortsmith/styles.py`: typed front-matter models (`Beats`, `Presenter`, `Pip`, `Broll`, `Captions` = `CaptionStyle` + pager numbers, `Sound`, `FinaleSpec`, `Budget`, `Palette`), `StyleSpec` (numbers + `prose` + `sections`), `parse`, `load_all(registry, styles_dir)`, `check` (6.3 collision, 9.2 components), `shipped`, `resolve` → `Resolution(name, note, notice)`. Front-matter models are `extra="forbid"`, so a stray or misspelled key fails the load with the spec name and the key path. The README under `styles/` documents the layout.
- Forbidden list exactly as the operator ruled, in all four specs: `[sweep, riser, rumble_crescendo, whoosh]`; chimes and ticks removed (7.1); explainer's Sound prose cites 7.1 and says a tick is an ordinary cue choice under the 7.3 caps.
- YAML gotcha: PyYAML reads a bare `off` as `False`, so every presenter/finale mode `off` is quoted in the specs (`"off"`); the README says so.
- `pip.top` is the normal-diameter top (explainer 960 + 300 = 1260 = the caption block top of 1460 − 2 × 74 × 1.35, touching per 6.3). The 340 px large-face circle keeps the same bottom edge and grows upward, as `render.fixed_pip` already anchors it; the loader asserts with `pip.diameter` as the ticket states.
- `job.json`: `style_line` is replaced by `style` (resolved name), `style_note` (the full line, 1.1) and `style_notice` (1.4). A `before` validator on `JobRecord` maps a legacy `style_line` to `style_note` so job directories written before this commit still load (`GET /` counts them for the day limit).
- `ingest.accept` now takes `style: Resolution` (the route resolves so the page and the stored record come from one call). `render.EXPLAINER` is gone: `render.numbers_for(spec)` / `render.style_numbers(name)` read the front matter; `render.loaded_styles()` caches one load per process for the render path. `pipeline.run_job` / `Worker` take `specs` (the app and smoke pass the set they loaded); an unknown `job.json.style` fails the job at `planning` naming it; the pager numbers come from `captions.words_per_page` / `prefer` (`pipeline.pager_numbers`).
- App: `create_app(styles_dir=...)` loads every spec before anything else, so a broken spec raises `StyleError` at startup (tested). `GET /styles/resolve?line=` returns `{name, note, notice}` behind the passcode. The chips are `<span role="button" data-chip>` elements (the form keeps its single `<button>`), the live resolution is a small inline script with a 250 ms debounce that also runs on load. The job page shows the resolved style, the notice and the note.
- Draft specs (`educational`, `animated`, `hitech`) carry complete front matter with placeholder numbers (own beat ranges, transitions per 9.4, palettes, `requires_components` naming components still to build) so the loader and resolver are exercised on real drafts; their numbers are to be settled when each flips to shipped after one rated short (1.4). `hitech` is the 1.4 smoke draft (048).
- Feedback loops: ruff clean, pyright strict clean, 339 tests pass, smoke `delivered` with T1–T4 in about 26 s (the run also asserts the resolver and the stored style), `npm test` 3/3.
- Left for later tickets (pointers added on each): 009 reads `beats` / `presenter` / `broll` numbers; 010 reads `captions.gap_break_s`, `emphasis_max_ratio` and the layout numbers; 011 reads `budget`; 013 reads `pip.large_face_ratio` / `chin_anchor`; 022 reads `sound`; 030 completes `explainer.requires_components`. Decision 2.3's target length from a style note that names a length is not parsed yet (`Constraints.target_duration_s` is still min(60, clip length)); 009 or 014 should add it.

## Blocked by

- Blocked by `issues/006-t1-t4-contact-sheet-delivered.md`

## User stories addressed

- User story 2
- User story 3
- User story 10
- User story 65
