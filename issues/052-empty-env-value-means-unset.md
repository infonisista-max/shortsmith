# 052 — An empty `KEY=` in `.env` means unset

## Type

AFK — no new packages.

## Parent PRD

`issues/prd.md`

## What to build

`config.Settings` reads `.env` through pydantic-settings with the default
`env_ignore_empty=False`, so a line like `FREESOUND_API_KEY=` is parsed as
`SecretStr('')`, not `None` (verified 25 Sep 2026). Every optional-key check in the code
is `is None`: `check_startup` (ANTHROPIC, GROQ, GEMINI keys), `freesound.from_settings`,
and the Pexels/Pixabay skip in `assets.from_settings`. An operator who leaves a key blank
in `.env` therefore arms the adapter with an empty token instead of disabling it, and the
startup check that should have named the missing key passes. `.env.example` currently
works around this by commenting optional keys out.

Fix: `env_ignore_empty=True` in `Settings.model_config`, so an empty value is treated as
absent and the field keeps its default. Nothing else changes: a key with a value is read
exactly as today, and the required-passcode path (`SHORTSMITH_PASSCODE=` → app refuses
to start) must still refuse, now via the default `None` instead of an empty secret.

Then `.env.example` may use bare `KEY=` lines for the optional keys again; the operator
edits that file (it is denied to agent sessions), so the ticket's done note lists the
lines to change rather than changing them.

Decisions 11.3 (startup validation names the fix), 5.1 (a source whose key is unset is
skipped), 7.2 / 024 (no Freesound key → no runtime search).

## Acceptance criteria

- [ ] `Settings` built with `FREESOUND_API_KEY=""` in the environment (and, via a temp
      `_env_file`, the line `FREESOUND_API_KEY=`) has `freesound_api_key is None`; the
      same for `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `PEXELS_API_KEY`,
      `PIXABAY_API_KEY`.
- [ ] An empty non-secret value falls back to the default too: `MAX_QUEUE=` gives 3,
      `ASSET_SOURCES=` gives `DEFAULT_ASSET_SOURCES`, rather than a validation error or
      an empty order.
- [ ] `check_startup` with `TRANSCRIBER=groq` and `GROQ_API_KEY=` raises `ConfigError`
      naming `GROQ_API_KEY` (today it passes).
- [ ] `freesound.from_settings` returns `None` for `FREESOUND_API_KEY=`; the app's "no
      audio search is configured" note appears.
- [ ] The app still refuses to start with `SHORTSMITH_PASSCODE=` (existing test holds).
- [ ] Tests never read a real `.env` (`Settings(_env_file=None)` or a temp file).
- [ ] Done note lists the `.env.example` lines the operator can uncomment
      (`#FREESOUND_API_KEY=` → `FREESOUND_API_KEY=` and the other optional keys), and
      the header comment about empty values that can then go.

## Blocked by

- Nothing.

## User stories addressed

- User story 29
- User story 33
