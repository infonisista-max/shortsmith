"""The facts-default bed (ticket 087; operator, 29 Sep 2026, 079 HITL).

When a flavour, or even a mood, has no approved bed, a facts short takes the kind of bed
fact channels always use, never a random Freesound hit. This module is what that bed is:

- **The default mood, learned** (`default_mood`): the mood with the largest runtime share
  over the parts of the Tier A and B reference short cards. Long-form cards (longer than
  the profile's `short_max_s`), `null` parts and the cards 086 skips are left out. A tie
  goes to the mood more cards carry, then to the name; the winner, the runner-up and every
  share are logged. No mood name lives in code.
- **The profile** (`assets/audio/facts_default.yaml`, `load_profile`): minor key, a
  ceiling on harmonic change, a percussive share around 15 %, a sub-bass floor, a ceiling
  on the energy above 1 kHz, and no vocals - each value with its source in the file.
- **The distance** (`measure_samples`, `distance`, `rank`): numpy over the samples. The
  key is `sound.seed`'s chromagram against the Krumhansl-Kessler profiles; the band
  shares come from the power spectrum; the percussive share is a median-filter split of
  the spectrogram (a peak that is wide across frequency is percussive, one that is long
  in time is harmonic); the harmonic change is the mean change of the half-second chroma.
  A feature inside its bounds costs nothing, outside them its gap over the bound's scale
  (at most 1); a feature with an `about` value also costs a quarter of its distance from
  it. A wrong mode costs 1. A file whose name or tags carry a word the bed kind forbids
  (a vocal, 068) never ranks.

The director reads the `facts_default` role tag on approved beds (`sound.score_candidates`);
the shortlist's `facts_default` slot (`sound.shortlist`) asks this profile's `queries`
first and ranks every candidate by distance.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import yaml

from shortsmith import ffmpeg
from shortsmith.contracts import FACTS_DEFAULT as FACTS_DEFAULT
from shortsmith.sound import seed
from shortsmith.sound.kinds import Kind, forbidden

PROFILE_PATH = Path(__file__).resolve().parents[3] / "assets" / "audio" / "facts_default.yaml"
Floats = npt.NDArray[np.float64]
Log = Callable[[str], None]

MODES = ("minor", "major")
SHARES = ("percussive_share", "sub_bass_share", "above_1khz_share")
FEATURES = ("harmonic_change", *SHARES)
LEARNED_TIERS = frozenset({"A", "B"})

# measurement (numpy over `seed.MEASURE_RATE` samples)
MEASURE_S = 60.0  # a bed longer than a short is judged on its first minute
FFT, HOP = 2048, 512
MEDIAN_FRAMES, MEDIAN_BINS = 17, 17  # the median-filter split's two kernels
BLOCK = 128  # frames per median block, so the filter's window stack stays small
CHANGE_WINDOW_S = 0.5
ABOUT_WEIGHT = 0.25
EPS = 1e-12


class ProfileError(ValueError):
    """`facts_default.yaml` is malformed: the message names the key."""


@dataclass(frozen=True)
class Bound:
    low: float | None = None
    high: float | None = None
    about: float | None = None

    @property
    def scale(self) -> float:
        """What a gap outside the bound is measured against: the range's width, or the
        one bound when only one is given."""
        if self.low is not None and self.high is not None and self.high > self.low:
            return self.high - self.low
        return max(abs(self.high if self.high is not None else self.low or 0.0), EPS)


@dataclass(frozen=True)
class Profile:
    mode: str
    harmonic_change: Bound
    percussive_share: Bound
    sub_bass_share: Bound
    above_1khz_share: Bound
    sub_bass_max_hz: float
    high_min_hz: float
    short_max_s: float
    queries: list[str]

    def bound(self, feature: str) -> Bound:
        return cast(Bound, getattr(self, feature))


def _number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProfileError(f"{where} is not a number")
    return float(value)


def _bound(value: object, key: str, *, share: bool) -> Bound:
    if not isinstance(value, dict) or not value:
        raise ProfileError(f"{key} is not a mapping of min, max and about")
    row = cast(dict[str, object], value)
    unknown = set(row) - {"min", "max", "about"}
    if unknown:
        raise ProfileError(f"{key}: unknown key(s) {', '.join(sorted(unknown))}")
    low, high, about = (
        _number(row[k], f"{key}.{k}") if k in row else None for k in ("min", "max", "about")
    )
    for label, number in (("min", low), ("max", high), ("about", about)):
        if number is None:
            continue
        if number < 0 or (share and number > 1):
            limit = "0 to 1" if share else "0 or more"
            raise ProfileError(f"{key}.{label} {number:g} is off its range ({limit})")
    if low is not None and high is not None and low > high:
        raise ProfileError(f"{key}: min {low:g} is over max {high:g}")
    if about is not None and (
        (low is not None and about < low) or (high is not None and about > high)
    ):
        raise ProfileError(f"{key}.about {about:g} is off its stated range")
    return Bound(low, high, about)


def parse_profile(text: str, *, name: str) -> Profile:
    loaded: object = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ProfileError(f"{name}: not a mapping")
    data = cast(dict[str, Any], loaded)
    known = {"mode", "vocals", "bands_hz", "short_max_s", "queries", *FEATURES}
    unknown = set(data) - known
    if unknown:
        raise ProfileError(f"{name}: unknown key(s) {', '.join(sorted(unknown))}")
    missing = known - set(data)
    if missing:
        raise ProfileError(f"{name}: missing key(s) {', '.join(sorted(missing))}")
    try:
        mode = data["mode"]
        if mode not in MODES:
            raise ProfileError(f"mode {mode!r} is not one of {', '.join(MODES)}")
        if data["vocals"] is not False:
            raise ProfileError("vocals must be false: a facts-default bed has none")
        bands = data["bands_hz"]
        if not isinstance(bands, dict) or set(cast(dict[str, object], bands)) != {
            "sub_bass_max", "high_min"
        }:  # fmt: skip
            raise ProfileError("bands_hz is not a mapping of sub_bass_max and high_min")
        band = cast(dict[str, object], bands)
        sub = _number(band["sub_bass_max"], "bands_hz.sub_bass_max")
        high = _number(band["high_min"], "bands_hz.high_min")
        if not 0 < sub < high:
            raise ProfileError("bands_hz: sub_bass_max must be over 0 and under high_min")
        short = _number(data["short_max_s"], "short_max_s")
        if short <= 0:
            raise ProfileError("short_max_s is not a positive number of seconds")
        queries = data["queries"]
        if (
            not isinstance(queries, list)
            or not queries
            or not all(isinstance(q, str) and q.strip() for q in cast(list[object], queries))
        ):
            raise ProfileError("queries is not a list of plain search words")
        return Profile(
            mode=str(mode),
            harmonic_change=_bound(data["harmonic_change"], "harmonic_change", share=False),
            percussive_share=_bound(data["percussive_share"], "percussive_share", share=True),
            sub_bass_share=_bound(data["sub_bass_share"], "sub_bass_share", share=True),
            above_1khz_share=_bound(data["above_1khz_share"], "above_1khz_share", share=True),
            sub_bass_max_hz=sub,
            high_min_hz=high,
            short_max_s=short,
            queries=[str(q).strip() for q in cast(list[object], queries)],
        )  # fmt: skip
    except ProfileError as exc:
        raise ProfileError(f"{name}: {exc}") from None


def load_profile(path: Path = PROFILE_PATH) -> Profile:
    """The committed profile, checked; a missing file is a `ProfileError`."""
    if not path.is_file():
        raise ProfileError(f"{path.name}: not found at {path}")
    return parse_profile(path.read_text(encoding="utf-8"), name=path.name)


# --- the default mood, learned ------------------------------------------------------------


@dataclass(frozen=True)
class LearnedMood:
    mood: str
    runner_up: str | None
    shares: dict[str, float]


def default_mood(cards: Iterable[Any], *, short_max_s: float, log: Log) -> LearnedMood | None:
    """The mood with the largest runtime share over the parts of the Tier A and B short
    cards; `null` parts, long-form cards (over `short_max_s`) and the cards 086 skips
    (`reference.v2_cards`) are left out. A tie goes to the mood more cards carry, then
    to the name. None when no part is left."""
    from shortsmith.reference import v2_cards

    seconds: dict[str, float] = {}
    carried: Counter[str] = Counter()
    for card in v2_cards(cards, log=log):
        if card.tier not in LEARNED_TIERS:
            continue
        if card.duration_s > short_max_s:
            log(f"{card.video_id}: {card.duration_s:g} s is long-form (over {short_max_s:g} s); "
                "left out")  # fmt: skip
            continue
        moods = set[str]()
        for part in card.parts:
            if part.music_mood is None:
                continue
            seconds[part.music_mood] = seconds.get(part.music_mood, 0.0) + max(
                0.0, part.end_s - part.start_s
            )
            moods.add(part.music_mood)
        carried.update(moods)
    total = sum(seconds.values())
    if total <= 0:
        log("facts default mood: no short card has a part with music")
        return None
    shares = {m: s / total for m, s in seconds.items()}
    ranked = sorted(shares, key=lambda m: (-round(seconds[m], 6), -carried[m], m))
    mood = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    if runner is not None and round(seconds[mood], 6) == round(seconds[runner], 6):
        log(f"facts default mood: tie at {seconds[mood]:g} s between {mood} and {runner}; "
            f"{mood} is carried by more cards ({carried[mood]} to {carried[runner]}), "
            "then by name")  # fmt: skip
    listed = ", ".join(f"{m} {shares[m]:.0%}" for m in ranked)
    log(f"facts default mood: {mood} (runner-up {runner or 'none'}) over {total:g} s of "
        f"music: {listed}")  # fmt: skip
    return LearnedMood(mood=mood, runner_up=runner, shares=shares)


def learned_mood(
    inventory_dir: Path | None = None, *, profile: Profile, log: Log = print
) -> LearnedMood | None:
    """`default_mood` over the committed reference cards."""
    from shortsmith.reference import INVENTORY_DIR, load_card

    folder = inventory_dir or INVENTORY_DIR
    cards = [
        load_card(path.read_text(encoding="utf-8"))
        for path in (sorted(folder.glob("*.json")) if folder.is_dir() else [])
    ]
    return default_mood(cards, short_max_s=profile.short_max_s, log=log)


# --- measuring and ranking -----------------------------------------------------------------


@dataclass(frozen=True)
class Numbers:
    """A file's profile features: its key and the four numbers `distance` reads."""

    key: str | None
    harmonic_change: float
    percussive_share: float
    sub_bass_share: float
    above_1khz_share: float

    @property
    def minor(self) -> bool:
        return self.key is not None and self.key.endswith("m")

    def features(self) -> dict[str, float]:
        return {f: round(float(getattr(self, f)), 4) for f in FEATURES}


def _magnitudes(x: Floats) -> Floats:
    """Hann-windowed magnitude spectra, one row per `HOP`."""
    if x.size < FFT:
        x = np.concatenate((x, np.zeros(FFT - x.size)))
    framed = np.lib.stride_tricks.sliding_window_view(x, FFT)[::HOP]
    return np.abs(np.fft.rfft(framed * np.hanning(FFT), axis=1))


def _median(s: Floats, size: int, axis: int) -> Floats:
    """`s` median-filtered along `axis` (0 time, 1 frequency) with edge padding, a block
    of frames at a time."""
    half = size // 2
    pad = [(half, half), (0, 0)] if axis == 0 else [(0, 0), (half, half)]
    padded = np.pad(s, pad, mode="edge")
    out = np.empty_like(s)
    for start in range(0, s.shape[0], BLOCK):
        stop = min(start + BLOCK, s.shape[0])
        if axis == 0:
            chunk = padded[start : stop + 2 * half]
            view = np.lib.stride_tricks.sliding_window_view(chunk, size, axis=0)
        else:
            view = np.lib.stride_tricks.sliding_window_view(padded[start:stop], size, axis=1)
        out[start:stop] = np.median(view, axis=-1)
    return out


def _harmonic_change(s: Floats, freqs: Floats, sr: int) -> float:
    band = (freqs >= seed.CHROMA_MIN_HZ) & (freqs <= seed.CHROMA_MAX_HZ)
    pitch = np.round(69 + 12 * np.log2(freqs[band] / 440.0)).astype(np.int64) % 12
    per = max(1, round(CHANGE_WINDOW_S * sr / HOP))
    windows: list[Floats] = []
    for start in range(0, s.shape[0] - per + 1, per):
        summed = np.sum(s[start : start + per, band], axis=0)
        chroma = np.bincount(pitch, weights=summed, minlength=12).astype(np.float64)
        peak = float(np.max(chroma))
        if peak > EPS:
            windows.append(chroma / peak)
    if len(windows) < 2:
        return 0.0
    stacked = np.stack(windows)
    return float(np.mean(np.abs(np.diff(stacked, axis=0))))


def measure_samples(x: npt.ArrayLike, sr: int, profile: Profile) -> Numbers:
    samples = np.asarray(x, np.float64)[: int(MEASURE_S * sr)]
    s = _magnitudes(samples)
    freqs = np.fft.rfftfreq(FFT, 1.0 / sr)
    power = s**2
    total = float(np.sum(power[:, 1:]))
    if total <= EPS:
        return Numbers(key=None, harmonic_change=0.0, percussive_share=0.0,
                       sub_bass_share=0.0, above_1khz_share=0.0)  # fmt: skip
    per_bin = np.sum(power, axis=0)
    sub = float(np.sum(per_bin[(freqs > 0) & (freqs < profile.sub_bass_max_hz)])) / total
    high = float(np.sum(per_bin[freqs >= profile.high_min_hz])) / total
    harmonic = _median(s, MEDIAN_FRAMES, axis=0)
    percussive = _median(s, MEDIAN_BINS, axis=1)
    mask = percussive**2 / (harmonic**2 + percussive**2 + EPS)
    perc = float(np.sum((power * mask)[:, 1:])) / total
    return Numbers(
        key=seed.key_name(seed.chroma(samples, sr)),
        harmonic_change=_harmonic_change(s, freqs, sr),
        percussive_share=perc,
        sub_bass_share=sub,
        above_1khz_share=high,
    )


def measure_file(path: Path, profile: Profile) -> Numbers:
    rate = seed.MEASURE_RATE
    x = np.frombuffer(ffmpeg.pcm_f32(path, rate=rate), dtype="<f4").astype(np.float64)
    return measure_samples(x, rate, profile)


def _cost(value: float, bound: Bound) -> float:
    gap = max(
        (bound.low - value) if bound.low is not None else 0.0,
        (value - bound.high) if bound.high is not None else 0.0,
        0.0,
    )
    cost = min(1.0, gap / bound.scale)
    if bound.about is not None:
        cost += ABOUT_WEIGHT * min(1.0, abs(value - bound.about) / bound.scale)
    return cost


def distance(numbers: Numbers, profile: Profile) -> float:
    """How far a file is from the profile: 0 on it, larger further away (see the module
    docstring for the cost of each feature)."""
    mode = 0.0 if numbers.minor == (profile.mode == "minor") else 1.0
    return mode + sum(_cost(getattr(numbers, f), profile.bound(f)) for f in FEATURES)


Rankable = tuple[str, Sequence[str], Numbers]


def rank(items: Sequence[Rankable], profile: Profile, kind: Kind) -> list[tuple[int, float]]:
    """`(index, distance)` of each `(name, tags, numbers)`, nearest first; an item whose
    name or tags carry a word the bed kind forbids (a vocal, 068) is left out."""
    scored = [
        (i, distance(numbers, profile))
        for i, (name, tags, numbers) in enumerate(items)
        if forbidden(kind, name, tags) is None
    ]
    return sorted(scored, key=lambda pair: (pair[1], pair[0]))
