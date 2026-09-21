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

- [x] Root Node project (`package.json`, `tsconfig.json`, `remotion.config.ts`, `src/`) with a `Short` composition at 1080x1920, 30 fps, duration from the spec; Poppins weights 500–900 bundled under `assets/fonts/` and loaded locally, no network fonts.
- [x] The project exports a component registry (a JSON file written at build or a `registry.json` checked in and asserted by a Node test) listing `captions` and `pip`; a Python test reads it.
- [x] `contracts.RenderSpec` carries frames, fps, beats with mode and geometry, caption pages with per-word boxes, PIP geometry, gradient palette; `render.build_spec(plan, captions, pip_geometry, style_numbers) -> RenderSpec` is pure and unit-tested.
- [x] Captions render per 6.2: 74 px Poppins 800, line height 1.35, unspoken white 86 %, spoken white, active `#FFD60A` scale 1.0→1.08 over 0.10 s, keyword box `#111` on `#FFD60A`, stroke, drop and glow, page enter scale 0.94→1 over 0.12 s; every word in a fixed-advance box so activation never moves neighbours; block bottom anchored at y 1460.
- [x] PIP renders as a circle of the style's diameter with the ring look at the style's anchor; `full` beats show the presenter cut full-frame; `off` beats show the gradient.
- [x] `render.render(job)` runs the Remotion CLI with concurrency 2 and `--color-space bt709`, parses frame progress into `job.json.progress` (percentage), writes `work/picture.mp4` silent H.264, and records the render log in `work/`.
- [x] `python -m shortsmith.bench` renders the fixture composition and prints seconds per frame and total seconds; result is recorded nowhere yet (ticket 007).
- [x] Smoke renders `work/picture.mp4` from the fixture and asserts it exists, is H.264, 1080x1920, and has round(6 × 30) frames; total smoke time under 90 s on the laptop.

## Done (21 Sep 2026, operator-named HITL session)

Operator approvals in this session: `npm install` at the repo root with exact pinned versions, the five Poppins TTFs plus the OFL licence committed under `assets/fonts/`, TypeScript under `src/remotion/`, and a driver script over `@remotion/renderer` in place of the raw CLI.

### Packages (pinned, the operator pressed the install prompt)

The ticket named five; nine were installed because the composition needs the media and fonts helpers, the driver needs the renderer API, and the typecheck needs React's types:

- `remotion` 4.0.526, `@remotion/cli` 4.0.526, `@remotion/renderer` 4.0.526, `@remotion/media` 4.0.526 (the `Video` element; `OffthreadVideo` failed on B-frame pyramids in the prototype), `@remotion/fonts` 4.0.526 (local `loadFont`)
- `react` 19.3.0, `react-dom` 19.3.0
- dev: `typescript` 7.0.2, `@types/react` 19.3.0

Chrome headless shell was downloaded by Remotion on the first render into `node_modules/.remotion/` (git-ignored). Node on the machine is v24.19.0, not 22 as the ticket text said; nothing depended on the difference. npm 11 printed an "allow-scripts pending" warning for esbuild's postinstall; the render works without it.

### Root layout

- `package.json`, `tsconfig.json`, `remotion.config.ts` at the repo root; `npm test` runs the Node registry test, `npm run typecheck` runs `tsc`, `npm run studio` opens the Studio.
- TypeScript sources under `src/remotion/` beside `src/shortsmith/`, so the Python package stays pure: `index.ts`, `Root.tsx`, `Short.tsx`, `types.ts` (mirror of `contracts.RenderSpec`), `fonts.ts`, `registry.ts`, `registry.json`, `components/captions.tsx`, `components/pip.tsx`, `driver.mjs`, `tests/registry.test.mjs`.
- `assets/` is the Remotion public dir (`Config.setPublicDir`), so `staticFile("fonts/Poppins-ExtraBold.ttf")` resolves with no network. Fonts are OFL, not media, and are committed with `assets/fonts/OFL.txt`.
- The bundle is built once into `build/remotion/` (already git-ignored) and reused while a hash of `src/remotion/`, `remotion.config.ts`, `package-lock.json` and `assets/` is unchanged. `node_modules/` was added to `.gitignore` (operator condition).

### Decisions

- Driver script (`src/remotion/driver.mjs`) rather than parsing the CLI's TTY progress: it bundles through the CLI's own `remotion bundle`, then renders with `@remotion/renderer` using the 9.1 settings (concurrency 2, `colorSpace: "bt709"`, `muted`, H.264, crf 18, yuv420p) and prints one `progress N/M` line per frame count change plus a `done` line. Python streams those through the new `subproc.stream` (watchdog-registered like `subproc.run`) into `job.json.progress`.
- Remotion reads only URLs and public files, so the driver serves the presenter's directory on `127.0.0.1` with Range and CORS support for the render's lifetime. The presenter source is `input/raw.mp4` until 005 supplies `work/cut.mp4`.
- `render.Renderer` interface with `RemotionRenderer` and `FakeRenderer` (co-located, 12.1 style). Pipeline and app tests use the fake so the suite stays fast; `test_render`, `test_bench` and the three smoke walks render for real. The full suite now takes about three minutes.
- Pipeline: `sourcing` is a pass-through placeholder until 016, `rendering` runs the renderer, the job ends at `qa` (006). `JobRecord.progress` is written during the step and cleared by the next transition; the job JSON carries it, the page does not display it yet.
- Style numbers (6.2, 6.3, 3.3) live in `render.EXPLAINER` until the 008 loader; the pager numbers already live in `pipeline` the same way. Placeholders with no reference value on record, for 008 to move into front matter: gradient `#0B1D3A → #1F3B73` at 160°, PIP left 60 px, white 6 px ring. PIP top is derived: 1260 − 300 = 960, so the circle touches the caption block from above (6.3).
- Word boxes are sized from a per-glyph advance table for Poppins 800 (about 10 % accurate); 010 replaces it with the Pillow measurement and owns wrapping. Until then `render.layout_page` fills greedily, centres each line, and raises `LayoutError` on a third line.
- Keyword box timing follows the prototype the phone test accepted: yellow scaled while active, boxed once spoken.

### Measured on the laptop (Node 24.19.0, Remotion 4.0.526, concurrency 2)

- bench: 0.074 s/frame, 180 frames, 13.4 s render, 13.7 s total (warm bundle)
- smoke: 19.8 s end to end; the first render of a session adds the browser download once and the bundle (about 4 s) when sources changed

### Notes for the next iteration

- 005: switch `spec_for_job` to `work/cut.mp4`, mux the voice stem, extend smoke to `out/short.mp4`.
- 007: record the figures above in `docs/bench.md`; the VPS row waits for a box.
- 008: move `render.EXPLAINER` and the placeholders into explainer front matter; the loader's `pip.top + diameter <= anchor_y − max_lines × line_height` assertion holds on the derived value.
- 010: replace `render.text_width` with Pillow measurement; the box contract (`WordBox`) stays.
- Job page: show `progress` during `rendering` (11.1 wording) when the page is next touched.

## Blocked by

- Blocked by `issues/003-fake-planner-to-caption-pages.md`

## User stories addressed

- User story 26
- User story 27
- User story 28
- User story 58
- User story 66
