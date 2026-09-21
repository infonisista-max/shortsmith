"""config.Settings: every key in .env.example plus SHORTSMITH_DATA_DIR, defaults matching,
constructed without a .env file. Secrets are never printed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from shortsmith import config
from shortsmith.config import Settings

REPO = Path(__file__).resolve().parents[1]


def _example_keys() -> set[str]:
    keys: set[str] = set()
    for line in (REPO / ".env.example").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if m:
            keys.add(m.group(1))
    return keys


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key in _example_keys() | {"SHORTSMITH_DATA_DIR"}:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return config.load(env_file=None)


def test_every_example_key_is_a_setting() -> None:
    fields = {name.upper() for name in Settings.model_fields}
    assert _example_keys() <= fields
    assert "SHORTSMITH_DATA_DIR" in fields


def test_defaults_without_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert s.planner == "claude_code"
    assert s.asset_policy == "any"
    assert s.image_gen == "none"
    assert s.shortsmith_max_upload_mb == 500
    assert s.shortsmith_data_dir == Path("data")
    assert s.anthropic_api_key is None
    assert s.groq_api_key is None
    assert s.gemini_api_key is None
    assert s.shortsmith_passcode is None
    # 11.2 limits
    assert s.max_queue == 3
    assert s.max_jobs_per_day == 10
    assert s.max_job_minutes == 30


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(
        monkeypatch,
        PLANNER="fake",
        ASSET_POLICY="rights_safe",
        SHORTSMITH_MAX_UPLOAD_MB="42",
        SHORTSMITH_DATA_DIR="C:/tmp/shortsmith-data",
        GROQ_API_KEY="gsk_secret_value",
        MAX_QUEUE="5",
        MAX_JOBS_PER_DAY="2",
        MAX_JOB_MINUTES="1",
    )
    assert s.planner == "fake"
    assert s.asset_policy == "rights_safe"
    assert s.shortsmith_max_upload_mb == 42
    assert (s.max_queue, s.max_jobs_per_day, s.max_job_minutes) == (5, 2, 1)
    assert s.shortsmith_data_dir == Path("C:/tmp/shortsmith-data")
    assert s.groq_api_key is not None
    assert s.groq_api_key.get_secret_value() == "gsk_secret_value"


def test_secrets_are_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, GROQ_API_KEY="gsk_secret_value", SHORTSMITH_PASSCODE="hunter2")
    text = repr(s) + str(s) + s.model_dump_json()
    assert "gsk_secret_value" not in text
    assert "hunter2" not in text


@pytest.mark.parametrize(
    ("key", "value"),
    [("PLANNER", "gpt"), ("ASSET_POLICY", "everything"), ("IMAGE_GEN", "dalle")],
)
def test_unknown_choice_is_a_config_error(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, **{key: value})
