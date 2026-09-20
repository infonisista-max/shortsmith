"""Session fixtures. The synthetic clip (decision 12.1) is generated once per session
with ffmpeg into a temp dir and never committed. `media` hands out further synthetic
clips and stills for boundary tests, each generated once per session on first use."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shortsmith.fixture import make_clip, make_fixture, make_image


@pytest.fixture(scope="session")
def fixture_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("fixture") / "fixture.mp4"
    return make_fixture(path)


@dataclass
class Media:
    root: Path
    _made: dict[str, Path] = field(default_factory=lambda: {})

    def clip(
        self,
        *,
        duration_s: float = 20.0,
        width: int = 1080,
        height: int = 1920,
        amplitude: float = 0.3,
        audio: bool = True,
        ext: str = ".mov",
    ) -> Path:
        key = f"clip-{duration_s}-{width}x{height}-{amplitude}-{audio}{ext}"
        if key not in self._made:
            self._made[key] = make_clip(
                self.root / key,
                duration_s=duration_s,
                width=width,
                height=height,
                amplitude=amplitude,
                audio=audio,
            )
        return self._made[key]

    def image(self, *, width: int, height: int, ext: str = ".png") -> Path:
        key = f"image-{width}x{height}{ext}"
        if key not in self._made:
            self._made[key] = make_image(self.root / key, width=width, height=height)
        return self._made[key]


@pytest.fixture(scope="session")
def media(tmp_path_factory: pytest.TempPathFactory) -> Media:
    return Media(tmp_path_factory.mktemp("media"))
