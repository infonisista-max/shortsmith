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


def _startup(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Settings for a `check_startup` case: the judge defaults to `api`, which needs a
    key of its own (5.2, 017), so a case not about the judge turns it off."""
    env.setdefault("RELEVANCE_JUDGE", "none")
    return _settings(monkeypatch, **env)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    unlisted = {
        "FREESOUND_API_KEY",
        "PEXELS_API_KEY",
        "PIXABAY_API_KEY",
        "PLANNER_MODEL",
        "RELEVANCE_JUDGE",
        "RELEVANCE_JUDGE_MODEL",
        "SHORTSMITH_DATA_DIR",
        "SHORTSMITH_SINGLE_OPERATOR",
        "TRANSCRIBER",
        "TRANSCRIBER_LANGUAGE",
        "TRANSCRIBER_MODEL",
    }
    for key in _example_keys() | unlisted:
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
    # 5.1 source order, written out in full: owner references first, generation last
    assert s.asset_sources == "owner,web,commons,openverse,pexels,pixabay,generate"
    assert s.pexels_api_key is None
    assert s.pixabay_api_key is None
    assert s.freesound_api_key is None  # 024: no key, no runtime audio search


def test_asset_sources_override(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, ASSET_SOURCES="commons,pexels")
    assert s.asset_sources == "commons,pexels"


def test_an_unknown_asset_source_is_a_startup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """5.1: removing a misbehaving source is a config edit, so a typo in that edit has
    to stop the server rather than silently drop a rung of the ladder."""
    with pytest.raises(config.ConfigError, match="unsplash"):
        config.check_startup(
            _startup(monkeypatch, PLANNER="fake", TRANSCRIBER="fake",
                     ASSET_SOURCES="web,unsplash,commons")  # fmt: skip
        )
    config.check_startup(
        _startup(monkeypatch, PLANNER="fake", TRANSCRIBER="fake",
                 ASSET_SOURCES=config.DEFAULT_ASSET_SOURCES)  # fmt: skip
    )
    config.check_startup(
        _startup(monkeypatch, PLANNER="fake", TRANSCRIBER="fake", ASSET_SOURCES="fake")
    )


def test_the_free_library_keys_are_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """018: Pexels and Pixabay want a free key; it is never printed."""
    s = _settings(monkeypatch, PEXELS_API_KEY="pexels_secret", PIXABAY_API_KEY="pixabay_secret")
    assert s.pexels_api_key is not None and s.pixabay_api_key is not None
    assert s.pexels_api_key.get_secret_value() == "pexels_secret"
    assert "pexels_secret" not in repr(s) + s.model_dump_json()
    assert "pixabay_secret" not in repr(s) + s.model_dump_json()


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


def test_the_subscription_planner_needs_a_declared_single_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """8.3 / 11.3: `PLANNER=claude_code` (the default) runs on the operator's own
    subscription, so startup refuses it unless SHORTSMITH_SINGLE_OPERATOR=true."""
    default = _startup(monkeypatch)
    assert default.shortsmith_single_operator is False
    with pytest.raises(config.ConfigError, match="SHORTSMITH_SINGLE_OPERATOR=true"):
        config.check_startup(_startup(monkeypatch, TRANSCRIBER="fake"))
    config.check_startup(
        _startup(monkeypatch, SHORTSMITH_SINGLE_OPERATOR="true", TRANSCRIBER="fake")
    )
    config.check_startup(_startup(monkeypatch, PLANNER="fake", TRANSCRIBER="fake"))


def test_the_transcriber_defaults_to_groq_on_whisper_large_v3_in_hindi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """12.1 / research §6: the real transcriber outside tests, fed as both approved
    jobs were (whisper-large-v3, language forced to hi); an empty language means
    Whisper detects it."""
    s = _settings(monkeypatch)
    assert (s.transcriber, s.transcriber_model, s.transcriber_language) == (
        "groq", "whisper-large-v3", "hi",
    )  # fmt: skip
    assert _settings(monkeypatch, TRANSCRIBER_LANGUAGE="").transcriber_language == ""


def test_the_groq_transcriber_needs_a_key_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """12.1 / 11.3: `TRANSCRIBER=groq` (the default) without GROQ_API_KEY stops the
    server with the fix named; `fake` needs nothing."""
    with pytest.raises(config.ConfigError, match="GROQ_API_KEY"):
        config.check_startup(_startup(monkeypatch, PLANNER="fake"))
    config.check_startup(_startup(monkeypatch, PLANNER="fake", GROQ_API_KEY="gsk_x"))
    config.check_startup(_startup(monkeypatch, PLANNER="fake", TRANSCRIBER="fake"))


def test_the_api_planner_needs_an_anthropic_key_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """8.3 / 11.3, the three planner outcomes: `api` needs ANTHROPIC_API_KEY, `claude_code`
    needs SHORTSMITH_SINGLE_OPERATOR=true, `fake` needs neither."""
    with pytest.raises(config.ConfigError, match="ANTHROPIC_API_KEY"):
        config.check_startup(_startup(monkeypatch, PLANNER="api", TRANSCRIBER="fake"))
    config.check_startup(
        _startup(monkeypatch, PLANNER="api", TRANSCRIBER="fake", ANTHROPIC_API_KEY="sk-x")
    )
    with pytest.raises(config.ConfigError, match="SHORTSMITH_SINGLE_OPERATOR=true"):
        config.check_startup(
            _startup(monkeypatch, PLANNER="claude_code", TRANSCRIBER="fake",
                      ANTHROPIC_API_KEY="sk-x")
        )  # fmt: skip
    config.check_startup(_startup(monkeypatch, PLANNER="fake", TRANSCRIBER="fake"))


def test_image_generation_is_off_by_default_and_gemini_needs_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5.5: rung 2 is a no-op until `IMAGE_GEN` names a generator; model and endpoint
    are config strings, so another provider is an `.env` edit, not code."""
    s = _settings(monkeypatch)
    assert (s.image_gen, s.image_gen_model) == ("none", "gemini-2.5-flash-image")
    assert s.image_gen_endpoint.endswith("/models/{model}:generateContent")
    with pytest.raises(config.ConfigError, match="GEMINI_API_KEY"):
        config.check_startup(
            _startup(monkeypatch, PLANNER="fake", TRANSCRIBER="fake", IMAGE_GEN="gemini")
        )
    config.check_startup(
        _startup(monkeypatch, PLANNER="fake", TRANSCRIBER="fake", IMAGE_GEN="gemini",
                 GEMINI_API_KEY="g_x")  # fmt: skip
    )
    config.check_startup(
        _startup(monkeypatch, PLANNER="fake", TRANSCRIBER="fake", IMAGE_GEN="fake")
    )
    swapped = _settings(monkeypatch, IMAGE_GEN_MODEL="imagen-x", IMAGE_GEN_ENDPOINT="https://e/x")
    assert (swapped.image_gen_model, swapped.image_gen_endpoint) == ("imagen-x", "https://e/x")


def test_the_relevance_judge_is_on_by_default_on_haiku_and_needs_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5.2: the judge filters every searched beat by default, on the current Haiku with
    the model swappable by config; `api` without ANTHROPIC_API_KEY stops the server,
    and `none` sources every beat on its source's own order."""
    s = _settings(monkeypatch)
    assert (s.relevance_judge, s.relevance_judge_model) == ("api", "claude-haiku-4-5-20251001")
    swapped = _settings(monkeypatch, RELEVANCE_JUDGE_MODEL="claude-sonnet-5")
    assert swapped.relevance_judge_model == "claude-sonnet-5"
    with pytest.raises(config.ConfigError, match="RELEVANCE_JUDGE=none"):
        config.check_startup(_settings(monkeypatch, PLANNER="fake", TRANSCRIBER="fake"))
    config.check_startup(
        _settings(monkeypatch, PLANNER="fake", TRANSCRIBER="fake", ANTHROPIC_API_KEY="sk-x")
    )
    config.check_startup(
        _settings(monkeypatch, PLANNER="fake", TRANSCRIBER="fake", RELEVANCE_JUDGE="fake")
    )


def test_the_planner_model_defaults_to_the_current_sonnet(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch).planner_model == "claude-sonnet-5"
    assert _settings(monkeypatch, PLANNER_MODEL="claude-opus-5").planner_model == "claude-opus-5"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("PLANNER", "gpt"),
        ("ASSET_POLICY", "everything"),
        ("IMAGE_GEN", "dalle"),
        ("RELEVANCE_JUDGE", "gpt4v"),
        ("TRANSCRIBER", "whisper_local"),
    ],
)
def test_unknown_choice_is_a_config_error(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, **{key: value})
