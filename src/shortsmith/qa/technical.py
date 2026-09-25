"""The technical gate (decision 10.1): T1-T13 in order, stop at the first FAIL, write
`out/qa.json`. Ticket 006 shipped T1-T4; 016 the rescue limit and T9; 023 T6; 031 T5,
T7 and T10; 032 completes T8 and adds T11-T13, so `delivered` now requires all
thirteen to `pass` (10.4).

Each check is a pure function over what ffprobe, the loudness pass, `frame_stats`, the
envelope cross-correlation or the grammar measured plus the plan, the measurement and
the render spec, so the boundaries in 10.1 are unit-tested on both sides without
encoding anything; `run` does the measuring. `qa.json` lists the checks that ran, in
order, so a failed report ends at the failing check, and `report` passes only when
every listed check is present and `pass`: a report that stopped short never delivers.

    T1  H.264 in an mp4 container, 1080x1920, 30 fps, one video and one audio stream
    T2  frame count = round(duration x 30) on the video stream
    T3  duration <= 60.000 s, beats contiguous within 0.011 s, finale beat 0.8-1.2 s
    T4  master -14.0 +/- 0.5 LUFS integrated, true peak <= -1.5 dBTP (EBU R128 via loudnorm)
    T5  captions cover three seeded sample times (a caption page is on screen at each),
        and the voice stem sits 0 +/- 1 frame against the cut clip's audio (envelope
        cross-correlation, `lipsync_lag_s`)
    T6  no sweep: `sound.sweep` R1-R4 on work/stems/sfx.wav - R1/R2 on the whole stem,
        R3/R4 per cue slice of work/stems/cues.json (050), so a hit names the cue that
        offends; no stem is a pass that says so, never a bare pass
    T7  mean luma >= 12/255 on every frame (full range), no run of identical frames
        longer than 0.5 s before the finale (`ffmpeg.frame_stats`: signalstats + framehash)
    T8  plan clean: rescued beats (ladder rung 3-4) <= the style limit scaled to the
        runtime (4.4), work/plan.validated.json re-validates under the job's style with
        zero violations (the grammar, 8.2), and work/render.log has no NetworkError
    T9  rights log complete: every beat's asset has a row, every row a source URL or an
        owner/generated origin, every generated row a prompt, no photoreal named entity
    T10 no cut boundary (work/cut.json, source timeline) lands mid-word: none sits more
        than 0.03 s inside a word of work/asr.json; a boundary in a pause is not mid-word
    T11 PIP geometry (3.3): on every strip frame with a face, the box the detector found
        sits fully inside the PIP circle once the window is scaled into it, and the chin
        is above 90 % of the window; from job.json.presenter, never pixels
    T12 safe area (6.3): no caption word box, stamp, counter or lower-third of the render
        spec reaches the top 250, bottom 320 or right 140 px; from geometry, not pixels.
        The hook title and the finale word are set pieces read off the reference frames
        (the title sits at y 170 by design) and are not in 10.1's list, so not here.
    T13 budget (11.3): the ledger total, the per-step totals, the style's allowances
        against what the asset step spent, and the soft-cap flag, recorded; never a
        failure for cost alone (the hard cap already failed the job before a paid call)

`status: not_implemented` is kept only so a `qa.json` written before 032 (T11-T13 held
as placeholders) still loads on the job page; such a row is never `passed` and such a
report never delivers.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
from pydantic import TypeAdapter, model_validator

from shortsmith import assets, ffmpeg, grammar, jobs, ledger, presenter, render, rights, sound
from shortsmith.contracts import (
    AssetManifest,
    CaptionPage,
    Captions,
    CueRecord,
    CueSheet,
    PicturePlan,
    PlanReference,
    PresenterMeasurement,
    ReferenceRecord,
    RenderSpec,
    RightsRow,
    Span,
    StrictModel,
    Transcript,
    ValidatedPlan,
    Word,
)
from shortsmith.ffmpeg import FrameStat, Loudness
from shortsmith.jobs import Job, JobRecord
from shortsmith.sound import sweep
from shortsmith.styles import Budget, StyleSpec

REPORT_NAME = "qa.json"

WIDTH, HEIGHT, FPS = 1080, 1920, 30
MAX_DURATION_S = 60.0
BEAT_GAP_S = 0.011
FINALE_MIN_S, FINALE_MAX_S = 0.8, 1.2
TARGET_LUFS, LUFS_TOLERANCE = -14.0, 0.5
MAX_TRUE_PEAK_DBTP = -1.5

# `not_implemented` is legacy: reports written before 032 (see the module note).
CheckStatus = Literal["pass", "fail", "not_implemented"]

CHECK_ORDER: tuple[str, ...] = (
    "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "T13",
)  # fmt: skip

_REFS = TypeAdapter(list[ReferenceRecord])


class QaCheck(StrictModel):
    """One check's result. `status` is `pass` or `fail` from `passed`; a legacy
    `not_implemented` row (pre-032 qa.json) is never `passed`."""

    name: str
    passed: bool
    detail: str
    status: CheckStatus = "pass"

    @model_validator(mode="after")
    def _status_follows_passed(self) -> QaCheck:
        if self.status == "not_implemented":
            if self.passed:
                raise ValueError(f"{self.name}: a not_implemented check cannot be passed")
            return self
        self.status = "pass" if self.passed else "fail"
        return self


class QaReport(StrictModel):
    checks: list[QaCheck]
    passed: bool

    @property
    def failed(self) -> QaCheck | None:
        return next((c for c in self.checks if c.status == "fail"), None)


def report(checks: Sequence[QaCheck]) -> QaReport:
    """The report over `checks`: passed only when every check in `CHECK_ORDER` is
    present and `pass` - the `delivered` rule (10.4). A report that stopped at a FAIL,
    or one from before 032 with rows held back, never delivers."""
    statuses = {c.name: c.status for c in checks}
    passed = all(statuses.get(name) == "pass" for name in CHECK_ORDER)
    return QaReport(checks=list(checks), passed=passed)


# --- the checks ------------------------------------------------------------------------------


def _video_stream(info: dict[str, Any]) -> dict[str, Any] | None:
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    return videos[0] if len(videos) == 1 else None


def t1(info: dict[str, Any]) -> QaCheck:
    """Codec, container and geometry from an ffprobe dict."""
    streams = info.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    fmt = str(info.get("format", {}).get("format_name", ""))
    problems: list[str] = []
    if "mp4" not in fmt.split(","):
        problems.append(f"container {fmt!r} is not mp4")
    if len(videos) != 1:
        problems.append(f"{len(videos)} video streams")
    if len(audios) != 1:
        problems.append(f"{len(audios)} audio streams")
    size = ""
    if videos:
        v = videos[0]
        codec = v.get("codec_name")
        size = f"{v.get('width')}x{v.get('height')}"
        rate = v.get("r_frame_rate")
        if codec != "h264":
            problems.append(f"codec {codec} is not h264")
        if (v.get("width"), v.get("height")) != (WIDTH, HEIGHT):
            problems.append(f"size {size} is not {WIDTH}x{HEIGHT}")
        if rate != f"{FPS}/1":
            problems.append(f"frame rate {rate} is not {FPS}/1")
    if problems:
        return QaCheck(name="T1", passed=False, detail="; ".join(problems))
    detail = f"h264 in mp4, {size}, {FPS} fps, one audio stream"
    return QaCheck(name="T1", passed=True, detail=detail)


def t2(info: dict[str, Any]) -> QaCheck:
    """Frame count equals round(duration x 30) on the video stream."""
    video = _video_stream(info)
    if video is None:
        return QaCheck(name="T2", passed=False, detail="no single video stream")
    frames = int(video.get("nb_frames", 0))
    duration = float(video.get("duration", info.get("format", {}).get("duration", 0.0)))
    expected = round(duration * FPS)
    detail = f"{frames} frames, expected round({duration:.3f} x {FPS}) = {expected}"
    return QaCheck(name="T2", passed=frames == expected, detail=detail)


def t3(info: dict[str, Any], plan: PicturePlan) -> QaCheck:
    """Duration cap, beat contiguity and finale length; the finale check reads the plan."""
    duration = float(info.get("format", {}).get("duration", 0.0))
    problems: list[str] = []
    if duration > MAX_DURATION_S:
        problems.append(f"duration {duration:.3f} s exceeds {MAX_DURATION_S:.3f} s")
    for a, b in zip(plan.beats, plan.beats[1:], strict=False):
        delta = b.start - a.end
        if abs(delta) > BEAT_GAP_S + 1e-9:
            how = f"have a gap of {delta:.3f} s" if delta > 0 else f"overlap by {-delta:.3f} s"
            problems.append(f"beats {a.id} and {b.id} {how}")
    finale = next((b for b in plan.beats if b.id == plan.finale.beat_id), None)
    if finale is None:
        problems.append(f"finale beat {plan.finale.beat_id!r} is not in the plan")
    else:
        length = finale.end - finale.start
        if not FINALE_MIN_S - 1e-9 <= length <= FINALE_MAX_S + 1e-9:
            problems.append(
                f"finale beat {finale.id} is {length:.3f} s, not {FINALE_MIN_S}-{FINALE_MAX_S} s"
            )
    if problems:
        return QaCheck(name="T3", passed=False, detail="; ".join(problems))
    assert finale is not None
    return QaCheck(
        name="T3",
        passed=True,
        detail=(
            f"{duration:.3f} s, {len(plan.beats)} contiguous beats, "
            f"finale {finale.end - finale.start:.3f} s"
        ),
    )


def t4(loudness: Loudness) -> QaCheck:
    """Master within +/- 0.5 LU of -14 LUFS and true peak at or under -1.5 dBTP."""
    detail = f"{loudness.integrated:.1f} LUFS, true peak {loudness.true_peak:.1f} dBTP"
    ok = (
        abs(loudness.integrated - TARGET_LUFS) <= LUFS_TOLERANCE + 1e-9
        and loudness.true_peak <= MAX_TRUE_PEAK_DBTP + 1e-9
    )
    return QaCheck(name="T4", passed=ok, detail=detail)


# --- T5 caption coverage and lip-sync (6.1, 3.1) --------------------------------------------

T5_SEED = 101  # decision 10.1: the draw is seeded so a report is reproducible
T5_SAMPLES = 3
LAG_MAX_FRAMES = 1.0
LAG_MAX_SEARCH_S = 0.5  # the fixture's bursts repeat every second; never chase a neighbour
ENVELOPE_HOP_S = 0.001


@dataclass(frozen=True)
class LipSync:
    """How much later the voice stem sounds than the cut clip's audio, in seconds;
    positive is late, negative early."""

    lag_s: float
    fps: int = FPS

    @property
    def frames(self) -> float:
        return self.lag_s * self.fps


def sample_words(
    words: Sequence[Word], *, hide_from: float | None, seed: int = T5_SEED, count: int = T5_SAMPLES
) -> list[Word]:
    """`count` of the captioned words (on the cut timeline, before `hide_from`) drawn
    by a RNG seeded with `seed`, in time order: the moments T5 asks for a caption at."""
    shown = [w for w in words if hide_from is None or w.start < hide_from - 1e-6]
    if not shown:
        return []
    rng = random.Random(seed)
    picks = sorted(rng.sample(range(len(shown)), k=min(count, len(shown))))
    return [shown[i] for i in picks]


def _envelope(samples: npt.NDArray[np.float64], hop: int) -> npt.NDArray[np.float64]:
    n = samples.size // hop
    if n == 0:
        return np.zeros(0)
    return np.abs(samples[: n * hop]).reshape(n, hop).mean(axis=1)


def lipsync_lag_s(
    reference: npt.ArrayLike,
    other: npt.ArrayLike,
    rate: int,
    *,
    max_lag_s: float = LAG_MAX_SEARCH_S,
    hop_s: float = ENVELOPE_HOP_S,
) -> float:
    """Seconds by which `other` sounds later than `reference` (negative: earlier), from
    the peak of the cross-correlation of their amplitude envelopes at `hop_s` steps,
    searched within +/- `max_lag_s`. Two silent tracks have no lag."""
    hop = max(1, round(rate * hop_s))
    a = _envelope(np.asarray(reference, dtype=np.float64), hop)
    b = _envelope(np.asarray(other, dtype=np.float64), hop)
    n = min(a.size, b.size)
    a, b = a[:n], b[:n]
    if n == 0:
        return 0.0
    a = a - a.mean()
    b = b - b.mean()
    if not a.any() or not b.any():
        return 0.0
    nfft = 1 << (2 * n - 1).bit_length()
    spectrum_a = np.fft.rfft(a, nfft)
    spectrum_b = np.fft.rfft(b, nfft)
    # cc[k] = sum_t a[t] * b[t + k]: it peaks at k = d when b is a delayed by d hops.
    cc = np.fft.irfft(np.conj(spectrum_a) * spectrum_b, nfft)
    max_lag = min(n - 1, round(max_lag_s * rate / hop))
    lags = np.arange(-max_lag, max_lag + 1)
    scores = cc[lags % nfft]
    best = int(lags[int(np.argmax(scores))])
    return best * hop / rate


def measure_lipsync(voice: Path, cut: Path) -> LipSync:
    """`lipsync_lag_s` of the voice stem against the cut clip's first audio stream."""
    rate = ffmpeg.SAMPLE_RATE
    reference = np.frombuffer(ffmpeg.pcm_f32(cut, rate=rate), dtype="<f4")
    other = np.frombuffer(ffmpeg.pcm_f32(voice, rate=rate), dtype="<f4")
    return LipSync(lag_s=lipsync_lag_s(reference, other, rate))


def t5(
    pages: Sequence[CaptionPage],
    words: Sequence[Word],
    lag: LipSync,
    *,
    hide_from: float | None,
    seed: int = T5_SEED,
) -> QaCheck:
    """Caption coverage and lip-sync (6.1, 3.1). `words` are on the cut timeline (as
    `presenter.words_on_cut` places them) and `hide_from` is the finale's start, after
    which no caption is due; each sampled word's midpoint must sit inside a page's
    window, and the stem's lag must be within +/- 1 frame."""
    sampled = sample_words(words, hide_from=hide_from, seed=seed)
    if not sampled:
        return QaCheck(
            name="T5", passed=False, detail="no captioned words before the finale to sample"
        )
    problems: list[str] = []
    covered: list[str] = []
    for word in sampled:
        t = round((word.start + word.end) / 2, 3)
        page = next((p for p in pages if p.start - 1e-9 <= t <= p.end + 1e-9), None)
        if page is None:
            problems.append(f"no caption page at {t:.2f} s ({word.text!r})")
        else:
            covered.append(f"{t:.2f} s {word.text!r}")
    lag_text = f"lip-sync lag {lag.frames:+.1f} frames ({lag.lag_s * 1000:+.0f} ms)"
    if abs(lag.frames) > LAG_MAX_FRAMES + 1e-9:
        problems.append(f"{lag_text}, outside +/-{LAG_MAX_FRAMES:g} frame")
    if problems:
        return QaCheck(name="T5", passed=False, detail="; ".join(problems))
    detail = f"seed {seed}: pages cover {', '.join(covered)}; {lag_text}"
    return QaCheck(name="T5", passed=True, detail=detail)


# --- T6 no sweep on the SFX stem (7.3) ----------------------------------------------------

CUE_TOL_S = 0.05  # a hit this close to a cue's span is that cue's


def sorted_sheet(sheet: CueSheet | None) -> CueSheet | None:
    """The sheet in start order: the one order `cue_slices` and `t6` must share, since a
    hit's `slice` is an index into it (050)."""
    if sheet is None:
        return None
    return CueSheet(cues=sorted(sheet.cues, key=lambda c: (c.start_s, c.end_s, c.entry_id)))


def cue_slices(sheet: CueSheet) -> list[sweep.Slice]:
    """Each cue's stretch of the stem, in the sheet's order: from its start to the
    earlier of its end and the next cue's start (050). The sheet must be in start order
    (`sorted_sheet`)."""
    cues = sheet.cues
    out: list[sweep.Slice] = []
    for i, cue in enumerate(cues):
        end = cue.end_s if i + 1 == len(cues) else min(cue.end_s, cues[i + 1].start_s)
        out.append((cue.start_s, max(cue.start_s, end)))
    return out


def cue_at(at_s: float, sheet: CueSheet | None) -> CueRecord | None:
    """The cue sounding at `at_s` (the latest to start, if two overlap), else the last
    one to start before it; None when no cue has started by then."""
    cues = sheet.cues if sheet is not None else []
    sounding = [c for c in cues if c.start_s - CUE_TOL_S <= at_s <= c.end_s + CUE_TOL_S]
    earlier = sounding or [c for c in cues if c.start_s <= at_s]
    return max(earlier, key=lambda c: c.start_s) if earlier else None


def _cue_of(hit: sweep.Hit, sheet: CueSheet | None) -> CueRecord | None:
    """The cue a hit belongs to: the slice it was measured in (R3/R4 on a stem, 050),
    else the cue sounding at its time (R1/R2)."""
    if hit.slice is not None and sheet is not None and hit.slice < len(sheet.cues):
        return sheet.cues[hit.slice]
    return cue_at(hit.at_s, sheet)


def t6(hits: Sequence[sweep.Hit] | None, sheet: CueSheet | None) -> QaCheck:
    """No sweep (7.3): R1-R4 on `work/stems/sfx.wav`, each hit named by its cue. `hits`
    is None when there is no SFX stem - a pass, with the reason written down. `sheet`
    is the one the hits were sliced by (`_sfx_scan`), in that order."""
    if hits is None:
        return QaCheck(
            name="T6",
            passed=True,
            detail="no SFX stem: work/stems/sfx.wav is absent, so the short has no cues to scan",
        )
    if not hits:
        count = len(sheet.cues) if sheet is not None else 0
        noun = "cue" if count == 1 else "cues"
        return QaCheck(
            name="T6", passed=True, detail=f"R1-R4 clean on the SFX stem ({count} {noun})"
        )
    problems: list[str] = []
    for hit in hits:
        cue = _cue_of(hit, sheet)
        where = (
            f"cue {cue.entry_id} on {cue.beat_id} ({cue.intent!r})"
            if cue is not None
            else "no cue sounds there"
        )
        problems.append(f"{hit.rule} at {hit.at_s:.2f} s in {where}: {hit.detail}")
    return QaCheck(name="T6", passed=False, detail="; ".join(problems))


# --- T7 luma and frozen frames (4.4, 3.1) --------------------------------------------------

LUMA_MIN = 12.0  # of 255, full range
FROZEN_MAX_S = 0.5


def t7(frames: Sequence[FrameStat], *, fps: int = FPS, finale_start_s: float | None) -> QaCheck:
    """Every frame's mean luma at or over 12/255, and no run of identical frames longer
    than 0.5 s before the finale (the finale card may hold still). A run of n frames
    lasts n / fps."""
    problems: list[str] = []
    dark = [f for f in frames if f.luma < LUMA_MIN - 1e-9]
    if dark:
        first = dark[0]
        noun = "frame" if len(dark) == 1 else "frames"
        problems.append(
            f"{len(dark)} {noun} under {LUMA_MIN:g}/255 mean luma, the first at "
            f"{first.index / fps:.2f} s ({first.luma:.2f})"
        )
    before = (
        [f for f in frames if f.index < finale_start_s * fps - 1e-6]
        if finale_start_s is not None
        else list(frames)
    )
    longest = 0
    start = 0
    for i in range(1, len(before) + 1):
        if i == len(before) or before[i].hash != before[start].hash:
            n = i - start
            longest = max(longest, n)
            if n / fps > FROZEN_MAX_S + 1e-9:
                problems.append(
                    f"frozen for {n / fps:.2f} s from {before[start].index / fps:.2f} s to "
                    f"{(before[start].index + n) / fps:.2f} s"
                )
            start = i
    if problems:
        return QaCheck(name="T7", passed=False, detail="; ".join(problems))
    lowest = min((f.luma for f in frames), default=0.0)
    detail = (
        f"{len(frames)} frames, mean luma min {lowest:.1f}/255, longest identical run "
        f"{longest / fps:.2f} s before the finale"
    )
    return QaCheck(name="T7", passed=True, detail=detail)


# --- T8 plan clean (10.1, 4.4, 8.2) -------------------------------------------------------------

NETWORK_ERROR = "NetworkError"


def t8(
    manifest: AssetManifest | None, violations: Sequence[str] | None, log: str | None
) -> QaCheck:
    """Plan clean: the 4.4 rescue limit, the validated plan re-checked by the grammar
    (`violations`: its lines, None when there is no `work/plan.validated.json`), and
    the render log (`log`: its text, None when missing) free of NetworkError. Every
    problem is named, the rescues first."""
    if manifest is None:
        return QaCheck(name="T8", passed=False, detail="work/assets.json is missing")
    problems: list[str] = []
    rescue = (
        f"{manifest.rescued} rescued beats (max {manifest.rescued_max} over "
        f"{manifest.runtime_s:g} s)"
    )
    if manifest.rescued > manifest.rescued_max:
        problems.append(f"not enough relevant B-roll: {rescue}")
    if violations is None:
        problems.append("work/plan.validated.json is missing, nothing to re-validate")
    elif violations:
        noun = "violation" if len(violations) == 1 else "violations"
        problems.append(f"plan re-validation: {len(violations)} {noun}: {'; '.join(violations)}")
    if log is None:
        problems.append("work/render.log is missing")
    else:
        errors = sum(1 for line in log.splitlines() if NETWORK_ERROR in line)
        if errors:
            noun = "line" if errors == 1 else "lines"
            problems.append(f"render log has {errors} {NETWORK_ERROR} {noun}")
    if problems:
        return QaCheck(name="T8", passed=False, detail="; ".join(problems))
    detail = (
        f"{rescue}; plan re-validates with zero violations; render log has no {NETWORK_ERROR}"
    )
    return QaCheck(name="T8", passed=True, detail=detail)


def t9(
    rows: Sequence[RightsRow] | None, manifest: AssetManifest | None, plan: PicturePlan
) -> QaCheck:
    """Rights log completeness (5.4), the rule set in `rights.completeness`."""
    if rows is None:
        return QaCheck(name="T9", passed=False, detail="out/rights.json is missing")
    if manifest is None:
        return QaCheck(name="T9", passed=False, detail="work/assets.json is missing")
    problems = rights.completeness(rows, manifest, plan)
    if problems:
        return QaCheck(name="T9", passed=False, detail="; ".join(problems))
    noun = "row" if len(rows) == 1 else "rows"
    detail = f"{len(rows)} rights {noun}, every beat's asset logged"
    return QaCheck(name="T9", passed=True, detail=detail)


# --- T10 no cut mid-word (3.1) ---------------------------------------------------------------

CUT_TOL_S = 0.03


def t10(spans: Sequence[Span] | None, words: Sequence[Word]) -> QaCheck:
    """No cut boundary lands mid-word: every edge of the cut list (source timeline)
    lies within 0.03 s of a word's start or end, or outside every word (a cut in a
    pause is where an editor cuts; the grammar's snap treats silence the same way)."""
    if spans is None:
        return QaCheck(name="T10", passed=False, detail="work/cut.json is missing")
    boundaries = sorted({round(t, 3) for s in spans for t in (s.start, s.end)})
    problems: list[str] = []
    for t in boundaries:
        word = next(
            (w for w in words if w.start + CUT_TOL_S + 1e-9 < t < w.end - CUT_TOL_S - 1e-9), None
        )
        if word is None:
            continue
        nearest = min(t - word.start, word.end - t)
        problems.append(
            f"cut at {t:.3f} s is inside {word.text!r} ({word.start:g}-{word.end:g} s), "
            f"{nearest:.3f} s from its nearest edge"
        )
    if problems:
        return QaCheck(name="T10", passed=False, detail="; ".join(problems))
    noun = "boundary" if len(boundaries) == 1 else "boundaries"
    detail = f"{len(boundaries)} cut {noun}, none more than {CUT_TOL_S:g} s inside a word"
    return QaCheck(name="T10", passed=True, detail=detail)


# --- T11 PIP geometry (3.3) ---------------------------------------------------------------------

CHIN_MAX_FRACTION = 0.90


def _circle_overshoot(face: presenter.FaceBox, pip: presenter.PipGeometry) -> float:
    """How far, in circle pixels, the box's farthest corner sits past the circle's edge
    once the window is scaled into the circle (negative: inside by that much)."""
    scale = pip.diameter / pip.window_size
    radius = pip.diameter / 2
    farthest = max(
        math.hypot((x - pip.window_left) * scale - radius, (y - pip.window_top) * scale - radius)
        for x in (face.left, face.left + face.width)
        for y in (face.top, face.top + face.height)
    )
    return farthest - radius


def t11(measured: PresenterMeasurement | None) -> QaCheck:
    """Every strip frame's face box inside the PIP circle and its chin above 90 % of
    the window (3.3), from the measurement on job.json. A still the detector found no
    face on is counted, not judged: the 3.3 floor already passed at `transcribing`."""
    if measured is None:
        return QaCheck(
            name="T11", passed=False, detail="job.json has no presenter measurement (3.3)"
        )
    pip = measured.pip
    problems: list[str] = []
    found = 0
    lowest_chin = 0.0
    for n, face in enumerate(measured.faces, start=1):
        if face is None:
            continue
        found += 1
        overshoot = _circle_overshoot(face, pip)
        if overshoot > 1e-6:
            problems.append(f"frame {n}: face box leaves the circle by {overshoot:.0f} px")
        chin = (face.chin_y - pip.window_top) / pip.window_size
        lowest_chin = max(lowest_chin, chin)
        if chin > CHIN_MAX_FRACTION + 1e-9:
            problems.append(
                f"frame {n}: chin at {chin:.1%} of the window, below {CHIN_MAX_FRACTION:.0%}"
            )
    if found == 0:
        problems.append("no strip frame has a face")
    if problems:
        return QaCheck(name="T11", passed=False, detail="; ".join(problems))
    detail = (
        f"face on {found} of {len(measured.faces)} strip frames, every box inside the "
        f"{pip.diameter} px circle, chin at {lowest_chin:.0%} of the window "
        f"(max {CHIN_MAX_FRACTION:.0%})"
    )
    return QaCheck(name="T11", passed=True, detail=detail)


# --- T12 safe area (6.3) ------------------------------------------------------------------------

# The platform's reserved zones (6.3): top, bottom and right, in composition pixels.
SAFE_TOP_PX, SAFE_BOTTOM_PX, SAFE_RIGHT_PX = 250, 320, 140


def zone_hits(left: float, top: float, width: float, height: float) -> list[str]:
    """Which 6.3 zones the box reaches into, one line each; empty when it stays clear.
    An edge exactly on a zone's line is clear."""
    hits: list[str] = []
    if top < SAFE_TOP_PX - 1e-6:
        hits.append(f"reaches y {top:g}, inside the top zone")
    if top + height > HEIGHT - SAFE_BOTTOM_PX + 1e-6:
        hits.append(f"reaches y {top + height:g}, inside the bottom zone")
    if left + width > WIDTH - SAFE_RIGHT_PX + 1e-6:
        hits.append(f"reaches x {left + width:g}, inside the right rail")
    return hits


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def t12(spec: RenderSpec | None) -> QaCheck:
    """No caption word, stamp, counter or lower-third box of the render spec inside the
    6.3 reserved zones, each offender named with its page or beat."""
    if spec is None:
        return QaCheck(name="T12", passed=False, detail="work/render_spec.json is missing")
    problems: list[str] = []
    words = stamps = lowers = 0

    def judge(label: str, left: float, top: float, width: float, height: float) -> None:
        problems.extend(f"{label} {hit}" for hit in zone_hits(left, top, width, height))

    for page in spec.captions:
        for word in page.words:
            words += 1
            label = f"caption page {page.index} {word.text!r} at {page.start:.2f} s"
            judge(label, word.x, word.y, word.width, word.height)
    for beat in spec.beats:
        for kind, box in (("stamp", beat.stamp), ("counter", beat.counter)):
            if box is None:
                continue
            stamps += 1
            judge(f"{beat.id} {kind} {box.text!r}", box.left, box.top, box.width, box.height)
        lower = beat.lower_third
        if lower is not None:
            lowers += 1
            label = f"{beat.id} lower-third {lower.name!r}"
            judge(label, lower.left, lower.top, lower.width, lower.height)
    if problems:
        return QaCheck(name="T12", passed=False, detail="; ".join(problems))
    detail = (
        f"{_plural(words, 'caption word')}, {_plural(stamps, 'stamp')}, "
        f"{_plural(lowers, 'lower-third')}: none inside the reserved zones "
        f"(top {SAFE_TOP_PX}, bottom {SAFE_BOTTOM_PX}, right {SAFE_RIGHT_PX} px)"
    )
    return QaCheck(name="T12", passed=True, detail=detail)


# --- T13 budget (11.3) --------------------------------------------------------------------------


def _allowance(name: str, used: int, cap: int, unit: str) -> str:
    line = f"{name} {used}/{cap} {unit}"
    return f"{line} (allowance spent)" if cap and used >= cap else line


def t13(record: JobRecord, manifest: AssetManifest | None, budget: Budget | None) -> QaCheck:
    """The ledger total and per-step totals, the style's allowances against what the
    asset step spent, and the soft-cap flag, written down (11.3). Cost never fails the
    gate: the hard cap already failed the job before its next paid call."""
    cash = ledger.cash_total(record)
    line = f"ledger INR {cash:.2f} cash over {_plural(len(record.cost), 'row')}"
    steps = [f"{s.step} INR {s.cash_inr:.2f}" for s in ledger.by_step(record)]
    if steps:
        line += f" ({', '.join(steps)})"
    tokens = ledger.tokens_total(record)
    if tokens:
        line += (
            f" + {tokens} subscription tokens (INR {ledger.equivalent_total(record):.2f} equiv.)"
        )
    if manifest is None:
        allowances = "no work/assets.json to read the allowances against"
    elif budget is None:
        allowances = "no loaded style to read the allowances from"
    else:
        m, b = manifest, budget
        allowances = ", ".join(
            (
                _allowance("judge", m.judge_calls, b.judge_max_calls, "calls"),
                _allowance("search", m.search_queries, b.search_max_queries, "queries"),
                _allowance("generated", m.generated_images, b.gen_max_per_short, "images"),
            )
        )
    soft = "OVER SOFT CAP (flag only)" if record.over_soft_cap else "soft cap not passed"
    return QaCheck(name="T13", passed=True, detail=f"{line}; {allowances}; {soft}")


# --- running the gate on a job ---------------------------------------------------------


def report_path(job: Job) -> Path:
    return job.out_dir / REPORT_NAME


def write_report(job: Job, report: QaReport) -> Path:
    path = report_path(job)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_report(job: Job) -> QaReport | None:
    path = report_path(job)
    if not path.is_file():
        return None
    return QaReport.model_validate_json(path.read_text(encoding="utf-8"))


def _sfx_scan(job: Job) -> tuple[list[sweep.Hit] | None, CueSheet | None]:
    """The detector's hits on the job's SFX stem, None when there is no stem, and the
    cue sheet that names them - sorted once here, and the same object handed to `t6`,
    since R3/R4 hits index it (050). Without a sheet the stem is read whole."""
    stems = job.work_dir / "stems"
    stem = stems / "sfx.wav"
    sheet = sorted_sheet(sound.cue_sheet(stems))
    if not stem.is_file():
        return None, sheet
    if sheet is None or not sheet.cues:
        return sweep.detect(stem), sheet
    return sweep.detect(stem, slices=cue_slices(sheet)), sheet


def _finale_start(plan: PicturePlan) -> float | None:
    finale = next((b for b in plan.beats if b.id == plan.finale.beat_id), None)
    return finale.start if finale is not None else None


def _t5(job: Job, plan: PicturePlan) -> QaCheck:
    """T5 over the job's files: pages from `work/captions.json`, the words moved onto
    the cut timeline by `work/cut.json` and `work/asr.json`, the lag of
    `work/stems/voice.wav` against `work/cut.mp4`."""
    captions = job.work_dir / "captions.json"
    asr = job.work_dir / "asr.json"
    voice = job.work_dir / "stems" / "voice.wav"
    cut = job.work_dir / "cut.mp4"
    for needed in (captions, asr, voice, cut):
        if not needed.is_file():
            missing = needed.relative_to(job.work_dir).as_posix()
            return QaCheck(name="T5", passed=False, detail=f"work/{missing} is missing")
    spans = presenter.load_cut_list(job)
    if spans is None:
        return QaCheck(name="T5", passed=False, detail="work/cut.json is missing")
    pages = Captions.model_validate_json(captions.read_text(encoding="utf-8")).pages
    transcript = Transcript.model_validate_json(asr.read_text(encoding="utf-8"))
    words = [w for _, w in presenter.words_on_cut(spans, transcript.words)]
    return t5(pages, words, measure_lipsync(voice, cut), hide_from=_finale_start(plan))


def _t7(job: Job, plan: PicturePlan, info: dict[str, Any]) -> QaCheck:
    short = job.out_dir / "short.mp4"
    video = _video_stream(info) or {}
    full_range = video.get("color_range") == "pc"
    frames = ffmpeg.frame_stats(short, full_range=full_range)
    return t7(frames, finale_start_s=_finale_start(plan))


def _t10(job: Job) -> QaCheck:
    asr = job.work_dir / "asr.json"
    if not asr.is_file():
        return QaCheck(name="T10", passed=False, detail="work/asr.json is missing")
    transcript = Transcript.model_validate_json(asr.read_text(encoding="utf-8"))
    return t10(presenter.load_cut_list(job), transcript.words)


def revalidate(job: Job, specs: Mapping[str, StyleSpec]) -> list[str] | None:
    """The grammar's violation lines for `work/plan.validated.json` under the job's
    style, with the brief and the must-use references the planning step used (2.3);
    None when there is no validated plan to re-check. Input files the sweeper may have
    taken read as empty: the plan is re-checked, the must-use list is not."""
    path = job.work_dir / "plan.validated.json"
    if not path.is_file():
        return None
    validated = ValidatedPlan.model_validate_json(path.read_text(encoding="utf-8"))
    spec = specs.get(job.record.style)
    if spec is None:
        return [f"style {job.record.style!r} is not a loaded spec (loaded: {sorted(specs)})"]
    asr = job.work_dir / "asr.json"
    if not asr.is_file():
        return ["work/asr.json is missing, the plan cannot be re-validated"]
    transcript = Transcript.model_validate_json(asr.read_text(encoding="utf-8"))
    brief_path = job.input_dir / "brief.md"
    brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
    refs_path = job.input_dir / "refs.json"
    refs = _REFS.validate_json(refs_path.read_text(encoding="utf-8")) if refs_path.is_file() else []
    references = [
        PlanReference(
            id=r.id, kind="image" if r.kind == "image" else "clip_frame", caption=r.caption,
            width=r.width, height=r.height,
        )  # fmt: skip
        for r in refs
    ]
    out = grammar.validate(
        validated.picture, validated.sound, transcript, spec,
        brief=brief, must_use=grammar.must_use_ids(brief, references),
    )  # fmt: skip
    return out.lines() if isinstance(out, grammar.Violations) else []


def _t8(job: Job, specs: Mapping[str, StyleSpec]) -> QaCheck:
    log = job.work_dir / "render.log"
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else None
    return t8(assets.load_manifest(job.path), revalidate(job, specs), log_text)


def _t12(job: Job) -> QaCheck:
    path = job.work_dir / "render_spec.json"
    if not path.is_file():
        return t12(None)
    return t12(RenderSpec.model_validate_json(path.read_text(encoding="utf-8")))


def run(job: Job, *, specs: Mapping[str, StyleSpec] | None = None) -> QaReport:
    """T1-T13 in order on `out/short.mp4`, `work/plan.json`, `work/asr.json`,
    `work/captions.json`, `work/cut.json`, `work/cut.mp4`, `work/stems/`,
    `work/assets.json`, `out/rights.json`, `work/plan.validated.json`, `work/render.log`,
    `job.json` (the measurement, the ledger) and `work/render_spec.json`; stops at the
    first FAIL and writes `out/qa.json` either way. `specs` are the loaded styles the
    grammar judged the plan by (the worker's set: the smoke's is fixture-shaped); None
    loads the shipped ones."""
    specs = specs if specs is not None else render.loaded_styles()
    short = job.out_dir / "short.mp4"
    info = ffmpeg.probe(short)
    plan = PicturePlan.model_validate_json(
        (job.work_dir / "plan.json").read_text(encoding="utf-8")
    )
    # job.json has other writers inside a step (the ledger, the measurement): read it fresh.
    record = jobs.load(job.path).record
    spec = specs.get(record.style)
    checks: list[QaCheck] = []
    for check in (
        lambda: t1(info),
        lambda: t2(info),
        lambda: t3(info, plan),
        lambda: t4(ffmpeg.measure_loudness(short)),
        lambda: _t5(job, plan),
        lambda: t6(*_sfx_scan(job)),
        lambda: _t7(job, plan, info),
        lambda: _t8(job, specs),
        lambda: t9(rights.load(job.path), assets.load_manifest(job.path), plan),
        lambda: _t10(job),
        lambda: t11(record.presenter),
        lambda: _t12(job),
        lambda: t13(record, assets.load_manifest(job.path), spec.budget if spec else None),
    ):
        result = check()
        checks.append(result)
        if result.status == "fail":
            break
    out = report(checks)
    write_report(job, out)
    return out
