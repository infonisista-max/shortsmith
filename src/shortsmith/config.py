"""Settings loaded from the environment, defaults matching `.env.example`.

Secrets are `SecretStr` so they never appear in logs or reprs. Tests construct
`Settings(_env_file=None)` so no `.env` is ever read under pytest (board rules).
Startup validation of planner/key combinations (decision 11.3) comes with ticket 015.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Planner = Literal["fake", "claude_code", "api"]
AssetPolicy = Literal["any", "rights_safe"]
ImageGen = Literal["none", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    planner: Planner = "claude_code"
    anthropic_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    shortsmith_passcode: SecretStr | None = None
    shortsmith_max_upload_mb: int = 500
    asset_policy: AssetPolicy = "any"
    image_gen: ImageGen = "none"
    gemini_api_key: SecretStr | None = None
    shortsmith_data_dir: Path = Path("data")


def load(env_file: str | Path | None = ".env") -> Settings:
    """Build Settings from the environment plus `env_file`; pass None to ignore any .env."""
    # `_env_file` is a real pydantic-settings init kwarg that pyright's synthesized
    # signature does not know about.
    return Settings(_env_file=env_file)  # pyright: ignore[reportCallIssue]
