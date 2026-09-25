"""Session fixtures. The synthetic clip (decision 12.1) is generated once per session
with ffmpeg into a temp dir and never committed. `media` hands out further synthetic
clips and stills for boundary tests, each generated once per session on first use."""

from __future__ import annotations

import wave
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from shortsmith import sound
from shortsmith.fixture import make_catalogue, make_clip, make_fixture, make_image, make_wav

Floats = npt.NDArray[np.float64]


@pytest.fixture(scope="session")
def fixture_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("fixture") / "fixture.mp4"
    return make_fixture(path)


@pytest.fixture(scope="session")
def faceless_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The fixture with the face ellipse left out (013): the early "could not find
    your face" failure has something to fail on."""
    path = tmp_path_factory.mktemp("faceless") / "faceless.mp4"
    return make_fixture(path, face=False)


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


# 050: SFX stems built in numpy, cue by cue, so a test can place cues whose tails run
# together and know exactly which cue is which. Every stem is 48 kHz mono float.
STEM_RATE = 48000


def ring(*, length_s: float = 2.0, amplitude: float = 0.5, decay: float = 0.5) -> Floats:
    """A 600 Hz hit that rings down for `length_s`: it enters at once (no attack), only
    falls (no crescendo), and stays over -60 dBFS until it stops. The default decay
    leaves the tail within 20 dB of a full hit 2 s on, as a reverb tail does."""
    t = np.arange(round(length_s * STEM_RATE)) / STEM_RATE
    return amplitude * np.sin(2 * np.pi * 600 * t) * np.exp(-decay * t)


def tone(*, length_s: float, amplitude: float = 0.3) -> Floats:
    """A steady 440 Hz tone: the R3 offender when it is longer than 5 s."""
    t = np.arange(round(length_s * STEM_RATE)) / STEM_RATE
    return amplitude * np.sin(2 * np.pi * 440 * t)


def swell(*, from_db: float = -20.0, over_s: float = 0.2, hold_s: float = 0.2) -> Floats:
    """A 440 Hz tone rising from `from_db` under its peak to it over `over_s`, then held:
    the R4 offender when `over_s` is over 150 ms."""
    t = np.arange(round((over_s + hold_s) * STEM_RATE)) / STEM_RATE
    db = np.minimum(from_db + (-from_db / over_s) * t, 0.0)
    return 0.5 * 10 ** (db / 20) * np.sin(2 * np.pi * 440 * t)


def stem(cues: Sequence[tuple[float, Floats]], *, runtime_s: float) -> Floats:
    """The cues summed at their start times into `runtime_s` of silence, as the SFX
    stem is mixed; a cue is cut where the runtime ends."""
    out = np.zeros(round(runtime_s * STEM_RATE))
    for start_s, samples in cues:
        a = round(start_s * STEM_RATE)
        part = samples[: max(0, out.size - a)]
        out[a : a + part.size] += part
    return out


def write_wav(path: Path, samples: Floats) -> Path:
    """`samples` as a 16-bit mono wav at `STEM_RATE`."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(STEM_RATE)
        handle.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return path


@pytest.fixture(scope="session")
def library(tmp_path_factory: pytest.TempPathFactory) -> sound.Library:
    """The 022 audio catalogue: tone beds and click SFX synthesised once per session
    into a temp dir, never committed. The real seed is ticket 025."""
    return sound.load_catalogue(make_catalogue(tmp_path_factory.mktemp("audio")))
