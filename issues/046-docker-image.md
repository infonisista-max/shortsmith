# 046 — Docker image with everything the renderer needs bundled

## Type

HITL — needs the Docker toolchain on the machine and an operator-run build; the agent writes the Dockerfile and compose file, the operator builds and runs the image on the laptop and the VPS.

## Parent PRD

`issues/prd.md`

## What to build

One image: Python 3.12, Node 22, the Remotion bundle, Chrome headless shell, ffmpeg, fonts, geodata, gazetteer, audio library and prices file, running the app and the worker; laptop first, any 4 vCPU / 8 GB VPS second. The renderer runs with no network: a container started with networking disabled renders the fixture end to end with every fake.

Covers PRD "Deployment". Decisions 9.1, 13.1.

## Acceptance criteria

- [ ] `Dockerfile` and `compose.yaml` at the repo root; `.env` is mounted, never copied; `SHORTSMITH_DATA_DIR` is a volume.
- [ ] Image build bundles the Remotion project (`npm ci` and bundle at build time), Chrome headless shell, `assets/fonts`, `assets/geo`, `assets/audio`; image size recorded in `docs/deploy.md`.
- [ ] `docker run --network none ... python -m shortsmith.smoke` passes inside the container.
- [ ] `docs/deploy.md` lists the run commands for laptop and VPS and the day-3 s/frame figure from 007 measured inside the container.

## Blocked by

- Blocked by `issues/030-transition-vocabulary-registry-complete.md`
- Blocked by `issues/045-job-list-page.md`

## User stories addressed

- User story 58
