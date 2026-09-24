"""The no-sweep detector (decision 7.3; ticket 023): the taste rule that stays hard code.

7.1 bans whooshes, sweeps and risers outright; this module is how the ban is enforced.
`detect(path)` decodes a file with ffmpeg (mono, 48 kHz, float32) and runs four rules on
the samples with numpy. Each hit carries its rule, when the offending sound starts and
the measured number, so the seed check names the file and T6 names the cue.

    R1  spectral flatness > 0.03 sustained > 0.45 s        (a noise whoosh's body)
    R2  crescendo >= 200 ms rising >= 8 dB in <= 3 dB steps (a riser)
    R3  one sound > 5 s                                     (a cue is a hit, not a bed)
    R4  attack > 150 ms from -20 dB under the peak to it    (a swell into a hit)

It runs on every catalogue SFX at seed time (`python -m shortsmith.sound.seed check`)
and on the rendered SFX stem, `work/stems/sfx.wav`, at render time (gate T6).

Silence never offends: a frame under `SILENCE_DB` belongs to no run and no sound, which
is what lets the same rules read a stem that is mostly silence between its cues. The
7.3 numbers are the named constants below; the frame sizes are this detector's
measuring resolution, like the geometry constants in `render`.

**R2, read (operator-approved 2026-09-25).** The level is measured in 50 ms windows at a
25 ms hop. A crescendo is a run of windows where each step is at most
`RISE_STEP_MAX_DB` louder than the last and never more than `RISE_JITTER_DB` quieter -
a sudden hit breaks the run on its first step. Within a run, the rise is measured from
its quietest window to its loudest one after it; the rise counts from the last window
still within the jitter of the bottom to the first window within the jitter of the top,
so the flat hold after a crescendo does not lengthen it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
from numpy.lib.stride_tricks import sliding_window_view

from shortsmith import ffmpeg

Rule = Literal["R1", "R2", "R3", "R4"]
Floats = npt.NDArray[np.float64]

SAMPLE_RATE = ffmpeg.SAMPLE_RATE
SILENCE_DB = -60.0  # dBFS: a quieter frame is silence and belongs to no run or sound
TINY = 1e-20  # keeps log10 finite on digital silence

# R1 - spectral flatness (7.3)
FLATNESS_MAX = 0.03
FLAT_SUSTAIN_S = 0.45
FLAT_FRAME_S, FLAT_HOP_S = 0.02, 0.01

# R2 - crescendo (7.3; the jitter is the operator-approved reading of "steps")
RISE_MIN_S = 0.2
RISE_MIN_DB = 8.0
RISE_STEP_MAX_DB = 3.0
RISE_JITTER_DB = 0.5
RISE_WINDOW_S, RISE_HOP_S = 0.05, 0.025
# Smoothing bias: the 50 ms window averages the bottom of a ramp up, so a crescendo reads
# about half a window's worth of rise short - a true 10 dB over 250 ms measures 9.0 dB.
# At the limit's own slope (8 dB in 200 ms) that is about 1 dB, so R2 needs roughly 9 dB
# of true rise to fire; RISE_MIN_DB stays at the 7.3 number and is tuned by ear at 025.

# R3 - cue length (7.3)
CUE_MAX_S = 5.0
EVENT_WINDOW_S = 0.01
EVENT_GAP_S = 0.05  # a shorter silence does not end a sound

# R4 - attack (7.3)
ATTACK_FLOOR_DB = 20.0
ATTACK_MAX_S = 0.15
ATTACK_PEAK_TOL_DB = 1.0  # the peak is reached once the level is this close to it
# Read literally (operator, 2026-09-25): a sound that jumps in from silence has crossed
# -20 dB at its entry, so one entering at -6 dB and swelling 250 ms to its peak offends.
# Rejecting too much is cheaper than letting a swell through; tuned by ear at 025.
ATTACK_WINDOW_S, ATTACK_HOP_S = 0.01, 0.0025

BLOCK_FRAMES = 2048  # spectra are taken this many frames at a time, to bound memory


@dataclass(frozen=True)
class Hit:
    """One broken rule: which, when the offending sound starts, and what was measured."""

    rule: Rule
    at_s: float
    detail: str


def decode(path: Path) -> Floats:
    """The file's first audio stream as mono float samples at `SAMPLE_RATE`."""
    data = np.frombuffer(ffmpeg.pcm_f32(path, rate=SAMPLE_RATE), dtype="<f4")
    return data.astype(np.float64)


def detect(path: Path) -> list[Hit]:
    """R1-R4 on the file at `path`; empty when it is clean."""
    return detect_samples(decode(path), SAMPLE_RATE)


def detect_samples(samples: npt.ArrayLike, rate: int) -> list[Hit]:
    """R1-R4 on mono samples at `rate`, the hits in time order."""
    x = np.asarray(samples, dtype=np.float64)
    if x.size == 0:
        return []
    events = sounds(x, rate)
    hits = [*_r1(x, rate), *_r2(x, rate), *_r3(events), *_r4(x, rate, events)]
    return sorted(hits, key=lambda h: (h.at_s, h.rule))


# --- framing -----------------------------------------------------------------------------


def frames(x: Floats, frame: int, hop: int) -> Floats:
    """Overlapping frames as a strided view (no copy); a short signal is zero-padded to
    one frame."""
    if x.size < frame:
        x = np.pad(x, (0, frame - x.size))
    return sliding_window_view(x, frame)[::hop]


def _level_db(frames: Floats) -> Floats:
    return 10.0 * np.log10(np.mean(frames * frames, axis=1) + TINY)


def _runs(mask: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Each maximal run of True as (first, last) indices, inclusive."""
    padded = np.concatenate(([False], mask, [False]))
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    return [(int(a), int(b) - 1) for a, b in zip(edges[::2], edges[1::2], strict=True)]


# --- R1: flatness ------------------------------------------------------------------------


def flatness(frames: Floats) -> Floats:
    """Spectral flatness per frame: the geometric over the arithmetic mean of the
    Hann-windowed power spectrum (0 for a pure tone, near 1 for white noise)."""
    window = np.hanning(frames.shape[1])
    out: list[Floats] = []
    for start in range(0, frames.shape[0], BLOCK_FRAMES):
        block = frames[start : start + BLOCK_FRAMES] * window
        power = np.abs(np.fft.rfft(block, axis=1)) ** 2 + TINY
        out.append(np.exp(np.mean(np.log(power), axis=1)) / np.mean(power, axis=1))
    return np.concatenate(out) if out else np.zeros(0)


def _r1(x: Floats, rate: int) -> list[Hit]:
    hop = round(FLAT_HOP_S * rate)
    framed = frames(x, round(FLAT_FRAME_S * rate), hop)
    flat = (flatness(framed) > FLATNESS_MAX) & (_level_db(framed) > SILENCE_DB)
    hits: list[Hit] = []
    for first, last in _runs(flat):
        held = (last - first + 1) * hop / rate
        if held > FLAT_SUSTAIN_S + 1e-9:
            hits.append(
                Hit(
                    rule="R1",
                    at_s=first * hop / rate,
                    detail=(
                        f"spectral flatness over {FLATNESS_MAX:g} held {held:.2f} s "
                        f"(max {FLAT_SUSTAIN_S:g} s)"
                    ),
                )
            )
    return hits


# --- R2: crescendo -----------------------------------------------------------------------


def _r2(x: Floats, rate: int) -> list[Hit]:
    hop = round(RISE_HOP_S * rate)
    level = _level_db(frames(x, round(RISE_WINDOW_S * rate), hop))
    if level.size < 2:
        return []
    audible = level > SILENCE_DB
    step = np.diff(level)
    rising = (
        (step >= -RISE_JITTER_DB)
        & (step <= RISE_STEP_MAX_DB)
        & audible[:-1]
        & audible[1:]
    )
    hits: list[Hit] = []
    for first_step, last_step in _runs(rising):
        seg = level[first_step : last_step + 2]  # step i joins windows i and i + 1
        rise = seg - np.minimum.accumulate(seg)
        top = int(np.argmax(rise))
        if rise[top] + 1e-9 < RISE_MIN_DB:
            continue
        bottom = int(np.argmin(seg[: top + 1]))
        end = bottom + int(np.argmax(seg[bottom : top + 1] >= seg[top] - RISE_JITTER_DB))
        near_bottom = np.flatnonzero(seg[bottom : end + 1] <= seg[bottom] + RISE_JITTER_DB)
        start = bottom + int(near_bottom[-1])
        span = (end - start) * hop / rate
        if span + 1e-9 >= RISE_MIN_S:
            hits.append(
                Hit(
                    rule="R2",
                    at_s=(first_step + start) * hop / rate,
                    detail=(
                        f"crescendo of {float(rise[top]):.1f} dB over {span:.2f} s in steps "
                        f"of at most {RISE_STEP_MAX_DB:g} dB (min {RISE_MIN_DB:g} dB over "
                        f"{RISE_MIN_S:g} s)"
                    ),
                )
            )
    return hits


# --- R3 and R4: per sound ----------------------------------------------------------------


def sounds(x: Floats, rate: int) -> list[tuple[float, float]]:
    """Each sound as (start_s, end_s): audible windows, a silence shorter than
    `EVENT_GAP_S` bridged."""
    win = round(EVENT_WINDOW_S * rate)
    audible = _level_db(frames(x, win, win)) > SILENCE_DB
    out: list[tuple[float, float]] = []
    for first, last in _runs(audible):
        start, end = first * win / rate, (last + 1) * win / rate
        if out and start - out[-1][1] < EVENT_GAP_S:
            out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def _r3(events: list[tuple[float, float]]) -> list[Hit]:
    return [
        Hit(
            rule="R3",
            at_s=start,
            detail=f"one sound {end - start:.2f} s long (max {CUE_MAX_S:g} s)",
        )
        for start, end in events
        if end - start > CUE_MAX_S + 1e-9
    ]


def attack_s(x: Floats, rate: int) -> float:
    """How long the sound takes from `ATTACK_FLOOR_DB` under its peak to the peak: from
    the first window after the last one under the floor to the first window within
    `ATTACK_PEAK_TOL_DB` of the peak. A sound that enters above the floor is timed from
    its first window."""
    hop = round(ATTACK_HOP_S * rate)
    level = _level_db(frames(x, round(ATTACK_WINDOW_S * rate), hop))
    peak = float(np.max(level))
    reached = int(np.argmax(level >= peak - ATTACK_PEAK_TOL_DB))
    under = np.flatnonzero(level[:reached] < peak - ATTACK_FLOOR_DB)
    start = int(under[-1]) + 1 if under.size else 0
    return (reached - start) * hop / rate


def _r4(x: Floats, rate: int, events: list[tuple[float, float]]) -> list[Hit]:
    hits: list[Hit] = []
    for start, end in events:
        attack = attack_s(x[round(start * rate) : round(end * rate)], rate)
        if attack > ATTACK_MAX_S + 1e-9:
            hits.append(
                Hit(
                    rule="R4",
                    at_s=start,
                    detail=(
                        f"attack of {attack:.2f} s from -{ATTACK_FLOOR_DB:g} dB to the peak "
                        f"(max {ATTACK_MAX_S:g} s)"
                    ),
                )
            )
    return hits
