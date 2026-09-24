"""The technical gate (decision 10.1): T1-T13 in order, stop at the first FAIL, write
`out/qa.json`. Ticket 006 shipped T1-T4; 016 adds the rescue limit as T8 (the rest of
T8 arrives with 032) and T9; 023 adds T6; later tickets append the others to `run`.

Each check is a pure function over what ffprobe or the loudness pass measured plus the
plan, so the boundaries in 10.1 are unit-tested on both sides without encoding
anything; `run` does the measuring. `qa.json` lists the checks that ran, in order, so a
failed report ends at the failing check.

    T1  H.264 in an mp4 container, 1080x1920, 30 fps, one video and one audio stream
    T2  frame count = round(duration x 30) on the video stream
    T3  duration <= 60.000 s, beats contiguous within 0.011 s, finale beat 0.8-1.2 s
    T4  master -14.0 +/- 0.5 LUFS integrated, true peak <= -1.5 dBTP (EBU R128 via loudnorm)
    T6  no sweep: `sound.sweep` R1-R4 on work/stems/sfx.wav, a hit named by the cue at its
        time (work/stems/cues.json); no stem is a pass that says so, never a bare pass
    T8  (016 part) rescued beats (ladder rung 3-4) <= the style limit scaled to the runtime
    T9  rights log complete: every beat's asset has a row, every row a source URL or an
        owner/generated origin, every generated row a prompt, no photoreal named entity
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from shortsmith import assets, ffmpeg, rights, sound
from shortsmith.contracts import (
    AssetManifest,
    CueRecord,
    CueSheet,
    PicturePlan,
    RightsRow,
    StrictModel,
)
from shortsmith.ffmpeg import Loudness
from shortsmith.jobs import Job
from shortsmith.sound import sweep

REPORT_NAME = "qa.json"

WIDTH, HEIGHT, FPS = 1080, 1920, 30
MAX_DURATION_S = 60.0
BEAT_GAP_S = 0.011
FINALE_MIN_S, FINALE_MAX_S = 0.8, 1.2
TARGET_LUFS, LUFS_TOLERANCE = -14.0, 0.5
MAX_TRUE_PEAK_DBTP = -1.5


class QaCheck(StrictModel):
    name: str
    passed: bool
    detail: str


class QaReport(StrictModel):
    checks: list[QaCheck]
    passed: bool

    @property
    def failed(self) -> QaCheck | None:
        return next((c for c in self.checks if not c.passed), None)


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


CUE_TOL_S = 0.05  # a hit this close to a cue's span is that cue's


def cue_at(at_s: float, sheet: CueSheet | None) -> CueRecord | None:
    """The cue sounding at `at_s` (the latest to start, if two overlap), else the last
    one to start before it; None when no cue has started by then."""
    cues = sheet.cues if sheet is not None else []
    sounding = [c for c in cues if c.start_s - CUE_TOL_S <= at_s <= c.end_s + CUE_TOL_S]
    earlier = sounding or [c for c in cues if c.start_s <= at_s]
    return max(earlier, key=lambda c: c.start_s) if earlier else None


def t6(hits: Sequence[sweep.Hit] | None, sheet: CueSheet | None) -> QaCheck:
    """No sweep (7.3): R1-R4 on `work/stems/sfx.wav`, each hit named by its cue. `hits`
    is None when there is no SFX stem - a pass, with the reason written down."""
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
        cue = cue_at(hit.at_s, sheet)
        where = (
            f"cue {cue.entry_id} on {cue.beat_id} ({cue.intent!r})"
            if cue is not None
            else "no cue sounds there"
        )
        problems.append(f"{hit.rule} at {hit.at_s:.2f} s in {where}: {hit.detail}")
    return QaCheck(name="T6", passed=False, detail="; ".join(problems))


def t8(manifest: AssetManifest | None) -> QaCheck:
    """The 4.4 rescue limit: more rescued beats than `rescued_max` fails (032 folds the
    plan re-validation and the NetworkError scan into the same check)."""
    if manifest is None:
        return QaCheck(name="T8", passed=False, detail="work/assets.json is missing")
    count = manifest.rescued
    detail = (
        f"{count} rescued beats (max {manifest.rescued_max} over {manifest.runtime_s:g} s); "
        "plan re-validation and the NetworkError scan arrive with 032"
    )
    if count > manifest.rescued_max:
        return QaCheck(name="T8", passed=False, detail=f"not enough relevant B-roll: {detail}")
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
    cue sheet that names them."""
    stems = job.work_dir / "stems"
    stem = stems / "sfx.wav"
    hits = sweep.detect(stem) if stem.is_file() else None
    return hits, sound.cue_sheet(stems)


def run(job: Job) -> QaReport:
    """T1-T4, T6, T8 and T9 in order on `out/short.mp4`, `work/plan.json`,
    `work/stems/`, `work/assets.json` and `out/rights.json`; stops at the first FAIL and
    writes `out/qa.json` either way."""
    short = job.out_dir / "short.mp4"
    info = ffmpeg.probe(short)
    plan = PicturePlan.model_validate_json(
        (job.work_dir / "plan.json").read_text(encoding="utf-8")
    )
    checks: list[QaCheck] = []
    for check in (
        lambda: t1(info),
        lambda: t2(info),
        lambda: t3(info, plan),
        lambda: t4(ffmpeg.measure_loudness(short)),
        lambda: t6(*_sfx_scan(job)),
        lambda: t8(assets.load_manifest(job.path)),
        lambda: t9(rights.load(job.path), assets.load_manifest(job.path), plan),
    ):
        result = check()
        checks.append(result)
        if not result.passed:
            break
    report = QaReport(checks=checks, passed=all(c.passed for c in checks))
    write_report(job, report)
    return report
