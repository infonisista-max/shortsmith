# 004 — Remotion composition: captions + PIP → silent H.264, plus the bench command

## Type

HITL — needs new packages: a Node render project at the repo root with `remotion`, `@remotion/cli`, `react`, `react-dom`, `typescript` (npm). Node 22 is on the machine (see `proto/remotion-captions/`). The agent does not run `npm install`; the operator approves the packages, then this ticket becomes AFK.

## Parent PRD

`issues/prd.md`

## What to build

The picture engine from 9.1: a Node project at the repo root holding the explainer composition, and a Python render bridge that writes the engine-specific RenderSpec from the plan, caption pages and PIP geometry, runs the Remotion CLI and reports frame progress to the job. Only two components exist after this ticket, `captions` and `pip`; the presenter is shown full-frame or in a fixed-geometry PIP (the measured window comes in 013) over a style-palette gradient. The composition renders to a silent H.264 file in `work/`. A `bench` command times the same composition and prints seconds per frame for ticket 007.

The `proto/remotion-captions/` prototype is evidence only; do not import from it.

Covers PRD `render` (bridge, composition, registry export), `contracts.RenderSpec`. Decisions 6.2 (typography numbers, active-word behaviour, fixed advance), 6.3 (safe area), 9.1, 9.2 (registry), 12.1 (bundled fonts), 13.1.

## Acceptance criteria

- [ ] Root Node project (`package.json`, `tsconfig.json`, `remotion.config.ts`, `src/`) with a `Short` composition at 1080x1920, 30 fps, duration from the spec; Poppins weights 500–900 bundled under `assets/fonts/` and loaded locally, no network fonts.
- [ ] The project exports a component registry (a JSON file written at build or a `registry.json` checked in and asserted by a Node test) listing `captions` and `pip`; a Python test reads it.
- [ ] `contracts.RenderSpec` carries frames, fps, beats with mode and geometry, caption pages with per-word boxes, PIP geometry, gradient palette; `render.build_spec(plan, captions, pip_geometry, style_numbers) -> RenderSpec` is pure and unit-tested.
- [ ] Captions render per 6.2: 74 px Poppins 800, line height 1.35, unspoken white 86 %, spoken white, active `#FFD60A` scale 1.0→1.08 over 0.10 s, keyword box `#111` on `#FFD60A`, stroke, drop and glow, page enter scale 0.94→1 over 0.12 s; every word in a fixed-advance box so activation never moves neighbours; block bottom anchored at y 1460.
- [ ] PIP renders as a circle of the style's diameter with the ring look at the style's anchor; `full` beats show the presenter cut full-frame; `off` beats show the gradient.
- [ ] `render.render(job)` runs the Remotion CLI with concurrency 2 and `--color-space bt709`, parses frame progress into `job.json.progress` (percentage), writes `work/picture.mp4` silent H.264, and records the render log in `work/`.
- [ ] `python -m shortsmith.bench` renders the fixture composition and prints seconds per frame and total seconds; result is recorded nowhere yet (ticket 007).
- [ ] Smoke renders `work/picture.mp4` from the fixture and asserts it exists, is H.264, 1080x1920, and has round(6 × 30) frames; total smoke time under 90 s on the laptop.

## Blocked by

- Blocked by `issues/003-fake-planner-to-caption-pages.md`

## User stories addressed

- User story 26
- User story 27
- User story 28
- User story 58
- User story 66
