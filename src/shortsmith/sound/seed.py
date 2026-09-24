"""Seed-time tools for the audio catalogue (decisions 7.2, 7.3; ticket 023).

    python -m shortsmith.sound.seed check   [--catalogue PATH]
    python -m shortsmith.sound.seed measure [--catalogue PATH]

`check` runs the sweep detector (`sound.sweep`, R1-R4) on every SFX in the catalogue and
exits 1 naming the entry, its file and each rule it breaks; 7.2 wants every SFX through
it before it is committed. `measure` fills the measured fields of every entry -
`duration_s`, `bpm`, `key`, `energy` - so the tags are the only hand-written ones; an
operator adds an entry with its id, kind, file, source, licence and tags, and runs it.
The header comment above `entries:` is kept; nothing is written if any file is missing
or the result would not load.

**How each field is measured** (numpy over samples ffmpeg decoded at `MEASURE_RATE`;
operator-approved route, no librosa):

- `duration_s`: sample count over the rate.
- `bpm` (beds only): an onset-strength curve - the half-wave-rectified rise of the
  log-magnitude spectrum frame to frame - autocorrelated over the lags of
  `BPM_MIN`-`BPM_MAX`, weighted by a log-normal prior at `PRIOR_BPM` (the octave-error
  guard librosa uses), the best lag refined by a parabola. Fewer than `MIN_ONSETS`
  onsets is no beat: `bpm` stays empty.
- `key` (beds only): a chromagram - each spectrum bin between `CHROMA_MIN_HZ` and
  `CHROMA_MAX_HZ` summed into its pitch class - correlated with the Krumhansl-Kessler
  major and minor profiles in all twelve keys; the best is written `C`, `Am`, `F#`, `Ebm`.
- `energy` (1-5): the onset rate per second, bucketed by `ENERGY_ONSETS_PER_S`. The edges
  are a first guess, to be checked against the hand-listened seed library (ticket 025).

An SFX gets `duration_s` and `energy`; a tempo or key on a one-shot hit means nothing.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import yaml

from shortsmith import ffmpeg
from shortsmith.contracts import AudioEntry
from shortsmith.sound import CATALOGUE_PATH, SoundError, load_catalogue, parse_catalogue, sweep

Floats = npt.NDArray[np.float64]

MEASURE_RATE = 22050

# onsets (bpm and energy)
ONSET_FFT, ONSET_HOP = 2048, 256
ONSET_PEAK_FRACTION = 0.3  # a peak this fraction of the loudest onset counts
# and never under this mean log-magnitude rise per bin: a click measures about 0.12, the
# frame-to-frame shimmer of a steady tone about 0.00003
ONSET_MIN_STRENGTH = 0.01
ONSET_MIN_GAP_S = 0.1
MIN_ONSETS = 4
BPM_MIN, BPM_MAX = 60.0, 200.0
PRIOR_BPM, PRIOR_OCTAVES = 120.0, 1.0
ENERGY_ONSETS_PER_S = (0.5, 1.5, 3.0, 5.0)  # energy 2, 3, 4, 5 from these rates up

# key
CHROMA_FFT, CHROMA_HOP = 8192, 4096
CHROMA_MIN_HZ, CHROMA_MAX_HZ = 55.0, 5000.0
PITCH_CLASSES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
# Krumhansl-Kessler key profiles, tonic first
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

BLOCK_FRAMES = 1024


# --- onsets, tempo, energy -----------------------------------------------------------------


def _spectra(x: Floats, fft: int, hop: int) -> list[Floats]:
    """Hann-windowed magnitude spectra, a block of frames at a time."""
    framed = sweep.frames(x, fft, hop)
    window = np.hanning(fft)
    return [
        np.abs(np.fft.rfft(framed[i : i + BLOCK_FRAMES] * window, axis=1))
        for i in range(0, framed.shape[0], BLOCK_FRAMES)
    ]


def onset_envelope(x: Floats) -> Floats:
    """Onset strength per `ONSET_HOP`: the mean positive rise of the log magnitude. The
    signal is preceded by one frame of silence, so a file that opens on a hit has it as
    its first onset."""
    padded = np.concatenate((np.zeros(ONSET_FFT), np.asarray(x, np.float64)))
    log = np.log1p(np.concatenate(_spectra(padded, ONSET_FFT, ONSET_HOP)))
    if log.shape[0] < 2:
        return np.zeros(0)
    return np.mean(np.maximum(0.0, np.diff(log, axis=0)), axis=1)


def onsets(env: Floats, sr: int) -> list[int]:
    """Peak frames of the onset curve: local maxima at least `ONSET_PEAK_FRACTION` of
    the strongest and at least `ONSET_MIN_STRENGTH`, `ONSET_MIN_GAP_S` apart."""
    if env.size < 3:
        return []
    floor = max(ONSET_MIN_STRENGTH, ONSET_PEAK_FRACTION * float(np.max(env)))
    gap = ONSET_MIN_GAP_S * sr / ONSET_HOP
    found: list[int] = []
    peaks = np.flatnonzero((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] >= floor))
    for i in (int(p) + 1 for p in peaks):
        if not found or i - found[-1] >= gap:
            found.append(i)
    return found


def onset_rate(x: npt.ArrayLike, sr: int) -> float:
    samples = np.asarray(x, np.float64)
    if samples.size == 0:
        return 0.0
    return len(onsets(onset_envelope(samples), sr)) / (samples.size / sr)


def energy_level(onsets_per_s: float) -> int:
    """1-5 from the onset rate (7.2): one step per `ENERGY_ONSETS_PER_S` edge reached."""
    return 1 + sum(1 for edge in ENERGY_ONSETS_PER_S if onsets_per_s >= edge - 1e-9)


def tempo_bpm(x: npt.ArrayLike, sr: int) -> float | None:
    """The tempo in BPM, or None when there are fewer than `MIN_ONSETS` onsets."""
    env = onset_envelope(np.asarray(x, np.float64))
    if len(onsets(env, sr)) < MIN_ONSETS:
        return None
    env = env - np.mean(env)
    spectrum = np.fft.rfft(env, 2 * env.size)
    ac = np.fft.irfft(np.abs(spectrum) ** 2)[: env.size]
    rate = sr / ONSET_HOP
    lags = np.arange(int(np.ceil(60.0 * rate / BPM_MAX)), int(60.0 * rate / BPM_MIN) + 1)
    lags = lags[lags < env.size - 1]
    if lags.size == 0:
        return None
    prior = np.exp(-0.5 * (np.log2(60.0 * rate / lags / PRIOR_BPM) / PRIOR_OCTAVES) ** 2)
    score = ac[lags] * prior
    best = int(np.argmax(score))
    lag = float(lags[best])
    if 0 < best < lags.size - 1:
        a, b, c = float(score[best - 1]), float(score[best]), float(score[best + 1])
        bend = a - 2 * b + c
        if bend < 0:
            lag += 0.5 * (a - c) / bend
    return 60.0 * rate / lag


# --- key ---------------------------------------------------------------------------------


def chroma(x: npt.ArrayLike, sr: int) -> Floats:
    """The pitch-class content of the whole file, C first, scaled to a maximum of 1
    (all zeros for silence)."""
    total = np.zeros(CHROMA_FFT // 2 + 1)
    for block in _spectra(np.asarray(x, np.float64), CHROMA_FFT, CHROMA_HOP):
        total += np.sum(block, axis=0)
    freqs = np.fft.rfftfreq(CHROMA_FFT, 1.0 / sr)
    band = (freqs >= CHROMA_MIN_HZ) & (freqs <= CHROMA_MAX_HZ)
    pitch = np.round(69 + 12 * np.log2(freqs[band] / 440.0)).astype(np.int64) % 12
    out = np.bincount(pitch, weights=total[band], minlength=12).astype(np.float64)
    peak = float(np.max(out))
    return out / peak if peak > 0 else out


def key_name(pitch: Floats) -> str | None:
    """The best-correlating Krumhansl-Kessler key: `C`, `Am`, `F#`, `Ebm`; None for
    silence."""
    if float(np.max(pitch)) <= 0.0 or float(np.std(pitch)) == 0.0:
        return None
    best: tuple[float, str] | None = None
    for tonic in range(12):
        for profile, suffix in ((MAJOR_PROFILE, ""), (MINOR_PROFILE, "m")):
            r = float(np.corrcoef(pitch, np.roll(np.asarray(profile), tonic))[0, 1])
            if best is None or r > best[0]:
                best = (r, PITCH_CLASSES[tonic] + suffix)
    assert best is not None
    return best[1]


# --- measuring a file --------------------------------------------------------------------


@dataclass(frozen=True)
class Measured:
    duration_s: float
    energy: int
    bpm: int | None = None
    key: str | None = None


def measure_samples(x: Floats, sr: int, *, kind: str) -> Measured:
    duration = round(x.size / sr, 2)
    energy = energy_level(onset_rate(x, sr))
    if kind != "bed":
        return Measured(duration_s=duration, energy=energy)
    bpm = tempo_bpm(x, sr)
    return Measured(
        duration_s=duration,
        energy=energy,
        bpm=round(bpm) if bpm is not None else None,
        key=key_name(chroma(x, sr)),
    )


def measure_file(path: Path, *, kind: str) -> Measured:
    x = np.frombuffer(ffmpeg.pcm_f32(path, rate=MEASURE_RATE), dtype="<f4").astype(np.float64)
    return measure_samples(x, MEASURE_RATE, kind=kind)


# --- the commands ------------------------------------------------------------------------

_ENTRIES = re.compile(r"^entries:", re.MULTILINE)
FIELD_ORDER = tuple(AudioEntry.model_fields)


def _with_measures(raw: dict[str, Any], measured: Measured) -> dict[str, Any]:
    """The entry with its measured fields replaced, in the 7.2 field order; a field the
    measure leaves empty is dropped rather than written as null."""
    merged = {**raw, "duration_s": measured.duration_s, "energy": measured.energy}
    merged.pop("bpm", None)
    merged.pop("key", None)
    if measured.bpm is not None:
        merged["bpm"] = measured.bpm
    if measured.key is not None:
        merged["key"] = measured.key
    ordered = {k: merged[k] for k in FIELD_ORDER if k in merged}
    return ordered | {k: v for k, v in merged.items() if k not in ordered}


def measure(path: Path) -> int:
    if not path.is_file():
        print(f"no catalogue at {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    loaded: object = yaml.safe_load(text)
    raw_entries = cast(dict[str, Any], loaded).get("entries") if isinstance(loaded, dict) else None
    if not raw_entries:
        print(f"{path.name}: no entries to measure")
        return 0
    entries = cast(list[dict[str, Any]], raw_entries)
    problems: list[str] = []
    out: list[dict[str, Any]] = []
    for raw in entries:
        entry_id, kind, file = raw.get("id"), raw.get("kind"), raw.get("file")
        if not entry_id or not kind or not file:
            problems.append(f"{entry_id or '?'}: an entry needs id, kind and file to be measured")
            continue
        source = path.parent / str(file)
        if not source.is_file():
            problems.append(f"{entry_id}: {file} is not in the library folder")
            continue
        measured = measure_file(source, kind=str(kind))
        out.append(_with_measures(raw, measured))
        print(
            f"{entry_id}: {measured.duration_s:.2f} s, energy {measured.energy}"
            + (f", {measured.bpm} bpm" if measured.bpm is not None else "")
            + (f", {measured.key}" if measured.key is not None else "")
        )
    match = _ENTRIES.search(text)
    header = text[: match.start()] if match else ""
    new_text = header + yaml.safe_dump({"entries": out}, sort_keys=False, allow_unicode=True)
    if not problems:
        try:
            parse_catalogue(new_text, name=path.name)
        except SoundError as exc:
            problems.append(str(exc))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"{path.name} not written", file=sys.stderr)
        return 1
    path.write_text(new_text, encoding="utf-8")
    print(f"{len(out)} entries measured into {path.name}")
    return 0


def check(path: Path) -> int:
    try:
        library = load_catalogue(path)
    except SoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    failures: list[str] = []
    for entry in library.sfx():
        source = library.file(entry)
        if not source.is_file():
            failures.append(f"{entry.id} ({entry.file}): the file is not in the library folder")
            continue
        for hit in sweep.detect(source):
            failures.append(
                f"{entry.id} ({entry.file}): {hit.rule} at {hit.at_s:.2f} s: {hit.detail}"
            )
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"{len(library.sfx())} sfx files clean")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shortsmith.sound.seed")
    parser.add_argument("command", choices=("check", "measure"))
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE_PATH)
    args = parser.parse_args(argv)
    catalogue = cast(Path, args.catalogue)
    return check(catalogue) if args.command == "check" else measure(catalogue)


if __name__ == "__main__":
    raise SystemExit(main())
