"""Session fixtures. The synthetic clip (decision 12.1) is generated once per session
with ffmpeg into a temp dir and never committed. `media` hands out further synthetic
clips and stills for boundary tests, each generated once per session on first use."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shortsmith import sound
from shortsmith.fixture import make_catalogue, make_clip, make_fixture, make_image, make_wav


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


TONE = "sin(2*PI*440*t)"


def _swell(*, from_db: float, over_s: float, hold_s: float = 0.2) -> tuple[str, float]:
    """A 440 Hz tone entering `from_db` under its peak, rising linearly in dB to the
    peak (0.5 full scale) over `over_s`, held `hold_s`, then silent for 0.2 s."""
    slope = -from_db / over_s
    expr = (
        f"if(lt(t,{over_s:g}),0.5*pow(10,({from_db:g}+{slope:.6g}*t)/20),"
        f"if(lt(t,{over_s + hold_s:g}),0.5,0))*{TONE}"
    )
    return expr, over_s + hold_s + 0.2


# 023: the sweep detector's offenders and their clean twins, one side of each 7.3
# boundary apiece. `expr` is an aevalsrc expression in `t`; every file is 48 kHz mono.
SWEEP_SIGNALS: dict[str, tuple[str, float]] = {
    # R1: white noise held 0.5 s (a whoosh's body) against 0.4 s (under 0.45 s)
    "noise_500ms": ("if(lt(t,0.5),0.6*random(0)-0.3,0)", 1.0),
    "noise_400ms": ("if(lt(t,0.4),0.6*random(0)-0.3,0)", 1.0),
    # R2: a crescendo of 10 dB over 250 ms; the same 10 dB over only 150 ms; and 250 ms
    # rising only 6 dB
    "crescendo_250ms_10db": _swell(from_db=-10, over_s=0.25),
    "crescendo_150ms_10db": _swell(from_db=-10, over_s=0.15),
    "crescendo_250ms_6db": _swell(from_db=-6, over_s=0.25),
    # R3: a steady tone sounding 5.1 s against 4.9 s
    "tone_5100ms": (f"if(lt(t,5.1),0.3*{TONE},0)", 5.5),
    "tone_4900ms": (f"if(lt(t,4.9),0.3*{TONE},0)", 5.5),
    # R4: a tone entering at -20 dB under its peak and reaching it in 200 ms / 100 ms
    "attack_200ms": _swell(from_db=-20, over_s=0.2),
    "attack_100ms": _swell(from_db=-20, over_s=0.1),
    # clean: four short decaying clicks, the shape of every fixture SFX
    "clicks": ("0.8*sin(2*PI*1000*t)*exp(-14*mod(t,0.5))*lt(mod(t,0.5),0.4)", 2.0),
}  # fmt: skip


@dataclass
class Sounds:
    root: Path
    _made: dict[str, Path] = field(default_factory=lambda: {})

    def __call__(self, name: str) -> Path:
        if name not in self._made:
            expr, duration_s = SWEEP_SIGNALS[name]
            self._made[name] = make_wav(self.root / f"{name}.wav", expr=expr, duration_s=duration_s)
        return self._made[name]


@pytest.fixture(scope="session")
def sounds(tmp_path_factory: pytest.TempPathFactory) -> Sounds:
    """The 023 sweep offenders and clean files, each synthesised on first use."""
    return Sounds(tmp_path_factory.mktemp("sweep"))


@pytest.fixture(scope="session")
def library(tmp_path_factory: pytest.TempPathFactory) -> sound.Library:
    """The 022 audio catalogue: tone beds and click SFX synthesised once per session
    into a temp dir, never committed. The real seed is ticket 025."""
    return sound.load_catalogue(make_catalogue(tmp_path_factory.mktemp("audio")))
