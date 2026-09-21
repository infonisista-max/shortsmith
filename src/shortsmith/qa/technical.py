"""The technical gate (decision 10.1): T1-T13 in order, stop at the first FAIL, write
`out/qa.json`. This ticket (006) ships T1-T4; later tickets append T5-T13 to `run`.

Each check is a pure function over what ffprobe or the loudness pass measured plus the
plan, so the boundaries in 10.1 are unit-tested on both sides without encoding
anything; `run` does the measuring. `qa.json` lists the checks that ran, in order, so a
failed report ends at the failing check.

    T1  H.264 in an mp4 container, 1080x1920, 30 fps, one video and one audio stream
    T2  frame count = round(duration x 30) on the video stream
    T3  duration <= 60.000 s, beats contiguous within 0.011 s, finale beat 0.8-1.2 s
    T4  master -14.0 +/- 0.5 LUFS integrated, true peak <= -1.5 dBTP (EBU R128 via loudnorm)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shortsmith import ffmpeg
from shortsmith.contracts import PicturePlan, StrictModel
from shortsmith.ffmpeg import Loudness
from shortsmith.jobs import Job

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


def run(job: Job) -> QaReport:
    """T1-T4 in order on `out/short.mp4` and `work/plan.json`; stops at the first FAIL
    and writes `out/qa.json` either way."""
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
    ):
        result = check()
        checks.append(result)
        if not result.passed:
            break
    report = QaReport(checks=checks, passed=all(c.passed for c in checks))
    write_report(job, report)
    return report
