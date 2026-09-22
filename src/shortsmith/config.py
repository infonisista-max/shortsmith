"""Settings loaded from the environment, defaults matching `.env.example`.

Secrets are `SecretStr` so they never appear in logs or reprs. Tests construct
`Settings(_env_file=None)` so no `.env` is ever read under pytest (board rules).
`check_startup` is the 11.3 startup validation the app runs in its lifespan:
`PLANNER=claude_code` (the default) needs `SHORTSMITH_SINGLE_OPERATOR=true`, since
it runs on the operator's own subscription; `TRANSCRIBER=groq` (the default) needs
`GROQ_API_KEY`; `PLANNER=api` and `RELEVANCE_JUDGE=api` (the default) need
`ANTHROPIC_API_KEY`; and every name in `ASSET_SOURCES` must be an image source that
exists, so a typo in that config edit stops the server instead of silently dropping a
rung of the 5.1 ladder. A source whose free key is unset is skipped, not an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Planner = Literal["fake", "claude_code", "api"]
Transcriber = Literal["fake", "groq"]
AssetPolicy = Literal["any", "rights_safe"]
ImageGen = Literal["none", "gemini"]
RelevanceJudge = Literal["none", "fake", "api"]

# 5.1: the source order, written out in full. `owner` and `generate` are the fixed
# bookends of the ladder (owner references always first, generation always last, 4.4),
# listed so the config reads as the whole order; only the names between them are
# searched. `fake` names `FakeImageSource` for a local run with no network.
DEFAULT_ASSET_SOURCES = "owner,web,commons,openverse,pexels,pixabay,generate"
KNOWN_ASSET_SOURCES: frozenset[str] = frozenset(
    {"owner", "web", "commons", "openverse", "pexels", "pixabay", "generate", "fake"}
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 12.1: the real transcriber outside tests; tests and smoke use the fake. Research
    # §6: both approved jobs ran whisper-large-v3 with the language forced to `hi`
    # (the Hinglish-drift fix); empty lets Whisper detect it.
    transcriber: Transcriber = "groq"
    transcriber_model: str = "whisper-large-v3"
    transcriber_language: str = "hi"
    planner: Planner = "claude_code"
    planner_model: str = "claude-sonnet-5"  # 8.3: PLANNER=api's model, the current Sonnet
    # 8.3 / 11.3: the subscription planner is for a single-operator deployment only.
    shortsmith_single_operator: bool = False
    anthropic_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    shortsmith_passcode: SecretStr | None = None
    shortsmith_max_upload_mb: int = 500
    max_queue: int = 3  # 11.2: running + waiting jobs; one more is refused
    max_jobs_per_day: int = 10  # 11.2: global, counted since midnight IST
    max_job_minutes: int = 30  # 11.2: the worker kills the step and fails the job
    asset_policy: AssetPolicy = "any"
    # 5.1: the searched sources in order, comma-separated; a misbehaving source is
    # removed here without code. Owner references always come first and generation
    # last; `rights_safe` drops `web` (5.2). `fake` names the FakeImageSource.
    asset_sources: str = DEFAULT_ASSET_SOURCES
    # 018: both are free keys; neither search is metered, so neither writes a ledger
    # row. A source in `ASSET_SOURCES` whose key is unset is skipped, not an error.
    pexels_api_key: SecretStr | None = None
    pixabay_api_key: SecretStr | None = None
    # 5.2: the cheap filter above the searched sources, on by default. `none` sources
    # every beat on its source's own order; `fake` is what tests and smoke run on.
    relevance_judge: RelevanceJudge = "api"
    relevance_judge_model: str = "claude-haiku-4-5-20251001"  # 5.2: swappable by config
    image_gen: ImageGen = "none"
    gemini_api_key: SecretStr | None = None
    shortsmith_data_dir: Path = Path("data")
    # 5.6 / 11.3: prices come from an operator-edited file, never from code. The per-job
    # caps are unset until the operator derives them from the first ten metered passing
    # jobs (p90 -> soft, above it -> hard); only the daily guard ships with a number.
    prices_file: Path = Path("prices.yaml")
    budget_inr_per_job: float | None = None  # soft: flags only
    budget_inr_hard: float | None = None  # hard: fails the job before the next paid call
    budget_inr_per_day: float = 500.0  # closes the upload form until midnight IST (044)


class ConfigError(Exception):
    """A setting combination the server must not start with; the message says the fix."""


def asset_source_names(text: str) -> tuple[str, ...]:
    """`ASSET_SOURCES` as a tuple of names, blanks dropped."""
    return tuple(name.strip() for name in text.split(",") if name.strip())


def check_startup(settings: Settings) -> None:
    unknown = sorted(set(asset_source_names(settings.asset_sources)) - KNOWN_ASSET_SOURCES)
    if unknown:
        raise ConfigError(
            f"ASSET_SOURCES names no such image source: {', '.join(unknown)}. "
            f"The names are {', '.join(sorted(KNOWN_ASSET_SOURCES))} "
            f"(decision 5.1; the default is {DEFAULT_ASSET_SOURCES})"
        )
    if settings.planner == "claude_code" and not settings.shortsmith_single_operator:
        raise ConfigError(
            "PLANNER=claude_code runs on the operator's own Claude subscription and is for "
            "a single-operator deployment only: set SHORTSMITH_SINGLE_OPERATOR=true in .env, "
            "or use PLANNER=api (decision 11.3)"
        )
    if settings.planner == "api" and settings.anthropic_api_key is None:
        raise ConfigError(
            "PLANNER=api calls the Anthropic Messages API directly: set ANTHROPIC_API_KEY "
            "in .env, or PLANNER=fake to run on the canned plans (decision 8.3)"
        )
    if settings.relevance_judge == "api" and settings.anthropic_api_key is None:
        raise ConfigError(
            "RELEVANCE_JUDGE=api calls the Anthropic Messages API for the image judge: "
            "set ANTHROPIC_API_KEY in .env, or RELEVANCE_JUDGE=none to source every beat "
            "on its source's own order (decision 5.2)"
        )
    if settings.transcriber == "groq" and settings.groq_api_key is None:
        raise ConfigError(
            "TRANSCRIBER=groq calls Groq Whisper directly: set GROQ_API_KEY in .env, "
            "or TRANSCRIBER=fake to run on the fixture words (decision 12.1)"
        )


def load(env_file: str | Path | None = ".env") -> Settings:
    """Build Settings from the environment plus `env_file`; pass None to ignore any .env."""
    # `_env_file` is a real pydantic-settings init kwarg that pyright's synthesized
    # signature does not know about.
    return Settings(_env_file=env_file)  # pyright: ignore[reportCallIssue]
