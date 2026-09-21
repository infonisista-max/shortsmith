# 049 - Smoke keep flag for operator render review

## Type

AFK

## Parent PRD

`issues/prd.md`

## What to build

Smoke currently renders inside `tempfile.TemporaryDirectory` (smoke.py:187) and
deletes everything on success, so the operator can never watch the rendered
`picture.mp4` - the human mechanics check is impossible by design. Add an opt-in
keep mode: when the environment variable `SHORTSMITH_SMOKE_KEEP=1` is set, the
smoke run leaves its work directory on disk and prints the absolute path to the
surviving `picture.mp4` in the final summary line. Default behavior without the
variable is unchanged: temp directory removed, output identical to today.

Covers the smoke fourth feedback loop (PRD Testing Decisions); operator tooling
only. No new packages.

## Acceptance criteria

- [x] `SHORTSMITH_SMOKE_KEEP=1` set: after `smoke ok`, the printed path exists,
  contains `picture.mp4` and `render.log`, and the summary line includes that
  absolute path.
- [x] Variable unset or any other value: behavior byte-identical to today - no
  surviving directory, summary line unchanged.
- [x] The kept directory is ignored by git (`git check-ignore` succeeds on it);
  nothing under it can reach a commit.
- [x] Tests in `tests/test_smoke_keep.py` cover: keep set -> directory survives
  with both files; keep unset -> directory removed; summary line contains the
  path only in keep mode. Use monkeypatch for the env var; no real 20 s render
  in unit tests - fake the render step as existing smoke tests do.

## Done (22 Sep 2026)

- Keep mode lands under `work/smoke/shortsmith-smoke-<random>/` beneath the
  current directory, not the system temp folder, so `git check-ignore` can
  succeed (`work/` is already in `.gitignore`). Only the exact value `1` keeps;
  `0`, `yes`, `true`, `""` and unset all clean up as before.
- `SmokeResult` gained a `picture` field; `main` appends `, kept <abs path>` to
  the summary only in keep mode. `smoke.workspace(keep)` is the one place that
  chooses between `TemporaryDirectory` and `mkdtemp(dir=work/smoke)`.
- Unit tests monkeypatch `smoke.run_smoke` with a stub that writes the two
  files, so the keep tests run in under a second with no render.
- Kept directories are never swept automatically; the operator deletes
  `work/smoke/` by hand. Ticket 042 (sweeper) may want to include it.

## Blocked by

- Nothing. `004` (Remotion pipeline) is done and pushed.

## User stories addressed

- None - operator tooling for the standing human render check (smoke is the
  fourth feedback loop; watch step recorded in HANDOFF-2026-09-22-B).
