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

## Done note (25 Sep 2026)

- `Settings.model_config` gains `env_ignore_empty=True` (pydantic-settings 2.15 applies
  it to both the process environment and the dotenv file). Every acceptance case is a
  test in `tests/test_config.py` (environment, temp `_env_file`, `MAX_QUEUE=`,
  `ASSET_SOURCES=`, `check_startup` on empty Groq / Anthropic / Gemini keys) and
  `tests/test_freesound.py` (`FREESOUND_API_KEY=` builds no adapter; `choose_bed` then
  says "no audio search is configured"). The passcode test with `""` still refuses.
- One consequence the ticket did not foresee: `TRANSCRIBER_LANGUAGE=` used to mean "let
  Whisper detect the language" (012). Under the new rule an empty value is unset, so it
  is `hi` again. Detection now has a word: `TRANSCRIBER_LANGUAGE=auto`
  (`transcriber.AUTO_LANGUAGE`; an empty string given to `Settings(...)` directly still
  reads as auto, so the constructor path is unchanged). Tests updated in
  `tests/test_config.py` and `tests/test_transcriber_groq.py`.
- `.env.example` is denied to agent sessions; lines for the operator to change:
  - Each optional key that is commented out can become a bare line again:
    `#FREESOUND_API_KEY=` → `FREESOUND_API_KEY=`, and the same for `PEXELS_API_KEY`,
    `PIXABAY_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (and `GROQ_API_KEY` if it
    is commented out). A bare `KEY=` now means unset.
  - The header comment explaining that an empty value is not "unset" can go.
  - The `TRANSCRIBER_LANGUAGE` comment: "empty = auto-detect" → "`auto` = let Whisper
    detect it; empty = the default `hi`".
- Loops: ruff, pyright, pytest (1161 passed), smoke (T1–T13 pass, 48.9 s) all green.

## Blocked by

- Nothing.

## User stories addressed

- User story 29
- User story 33
