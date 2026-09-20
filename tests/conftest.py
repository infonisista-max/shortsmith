"""Session fixtures. The synthetic clip (decision 12.1) is generated once per session
with ffmpeg into a temp dir and never committed."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith.fixture import make_fixture


@pytest.fixture(scope="session")
def fixture_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("fixture") / "fixture.mp4"
    return make_fixture(path)
