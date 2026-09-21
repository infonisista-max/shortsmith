"""qa.technical: T1-T4 (decision 10.1) each with a passing and a failing input, the
boundaries on both sides, and `run(job)` stopping at the first FAIL and writing
`out/qa.json`. Boundary cases use ffprobe-shaped dicts and `Loudness` values; the
real-file cases encode small synthetic clips (12.1: never a committed video)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from shortsmith import ffmpeg, jobs
from shortsmith.contracts import Beat, CutPlan, Finale, Hook, PicturePlan, Span
from shortsmith.ffmpeg import Loudness
from shortsmith.qa import technical
from shortsmith.qa.technical import QaReport
from tests.conftest import Media

MP4 = "mov,mp4,m4a,3gp,3g2,mj2"


def _info(
    *,
    width: int = 1080,
    height: int = 1920,
    fps: str = "30/1",
    codec: str = "h264",
    fmt: str = MP4,
    audio: int = 1,
    nb_frames: int = 180,
    duration: float = 6.0,
) -> dict[str, Any]:
    video = {
        "codec_type": "video",
        "codec_name": codec,
        "width": width,
        "height": height,
        "r_frame_rate": fps,
        "avg_frame_rate": fps,
        "nb_frames": str(nb_frames),
        "duration": f"{duration:.6f}",
    }
    streams: list[dict[str, Any]] = [video]
    streams += [{"codec_type": "audio", "codec_name": "aac"} for _ in range(audio)]
    return {"streams": streams, "format": {"format_name": fmt, "duration": f"{duration:.6f}"}}


def _beat(id: str, start: float, end: float, kind: str = "photo") -> Beat:
    return Beat(id=id, start=start, end=end, mode="off", kind=kind, asset_id="a1")  # type: ignore[arg-type]


def _plan(beats: list[Beat], finale_id: str) -> PicturePlan:
    return PicturePlan(
        prompt_version="test",
        cut=CutPlan(keep=[Span(start=0.0, end=beats[-1].end)]),
        beats=beats,
        hook=Hook(
            title="t", cold_open_span=Span(start=0.0, end=0.5), original_position="drop",
            card_asset_ids=["a1"],
        ),  # fmt: skip
        finale=Finale(beat_id=finale_id, text="end"),
        title="t",
        description="d",
    )


def _good_plan(finale_len: float = 1.0, gap: float = 0.0) -> PicturePlan:
    beats = [
        _beat("b1", 0.0, 2.0),
        _beat("b2", 2.0 + gap, 4.0),
        _beat("b3", 4.0, 4.0 + finale_len, kind="finale"),
    ]
    return _plan(beats, "b3")


# --- T1 codec / container / geometry -------------------------------------------------


def test_t1_passes_a_conforming_probe() -> None:
    check = technical.t1(_info())
    assert check.name == "T1"
    assert check.passed
    assert "1080x1920" in check.detail


@pytest.mark.parametrize(
    ("info", "needle"),
    [
        (_info(width=720, height=1280), "720x1280"),
        (_info(fps="25/1"), "25/1"),
        (_info(codec="hevc"), "hevc"),
        (_info(fmt="matroska,webm"), "matroska"),
        (_info(audio=0), "0 audio"),
        (_info(audio=2), "2 audio"),
    ],
)
def test_t1_fails_and_names_the_offence(info: dict[str, Any], needle: str) -> None:
    check = technical.t1(info)
    assert not check.passed
    assert needle in check.detail


def test_t1_on_real_files(media: Media) -> None:
    good = ffmpeg.probe(media.clip(duration_s=2.0, ext=".mp4"))
    assert technical.t1(good).passed
    wrong_size = ffmpeg.probe(media.clip(duration_s=2.0, width=720, height=1280, ext=".mp4"))
    assert not technical.t1(wrong_size).passed


# --- T2 frame count ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nb_frames", "duration", "ok"),
    [(180, 6.0, True), (179, 6.0, False), (181, 6.0, False), (60, 2.0, True), (59, 2.0, False)],
)
def test_t2_frame_count_is_round_duration_times_30(
    nb_frames: int, duration: float, ok: bool
) -> None:
    check = technical.t2(_info(nb_frames=nb_frames, duration=duration))
    assert check.name == "T2"
    assert check.passed is ok
    assert str(nb_frames) in check.detail


def test_t2_on_real_files(media: Media, tmp_path: Path) -> None:
    good = media.clip(duration_s=2.0, ext=".mp4")
    assert technical.t2(ffmpeg.probe(good)).passed
    dropped = tmp_path / "dropped.mp4"
    ffmpeg.run(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(good),
            "-vf", "select=not(eq(n\\,10))", "-fps_mode", "vfr",
            "-c:v", "libx264", "-preset", "ultrafast", "-an", str(dropped),
        ]  # fmt: skip
    )
    check = technical.t2(ffmpeg.probe(dropped))
    assert not check.passed
    assert "59" in check.detail


# --- T3 duration, contiguity, finale ---------------------------------------------------


def test_t3_passes_a_conforming_plan_and_duration() -> None:
    check = technical.t3(_info(duration=6.0), _good_plan())
    assert check.name == "T3"
    assert check.passed


@pytest.mark.parametrize(("duration", "ok"), [(60.0, True), (60.001, False)])
def test_t3_duration_boundary(duration: float, ok: bool) -> None:
    check = technical.t3(_info(duration=duration), _good_plan())
    assert check.passed is ok
    if not ok:
        assert "60.001" in check.detail


@pytest.mark.parametrize(
    ("gap", "ok", "word"),
    [(0.011, True, ""), (0.012, False, "gap"), (-0.011, True, ""), (-0.012, False, "overlap")],
)
def test_t3_beats_contiguous_within_0_011(gap: float, ok: bool, word: str) -> None:
    check = technical.t3(_info(), _good_plan(gap=gap))
    assert check.passed is ok
    if not ok:
        assert "b1" in check.detail and "b2" in check.detail and word in check.detail


@pytest.mark.parametrize(
    ("finale_len", "ok"), [(0.8, True), (0.79, False), (1.2, True), (1.21, False)]
)
def test_t3_finale_between_0_8_and_1_2_s(finale_len: float, ok: bool) -> None:
    check = technical.t3(_info(), _good_plan(finale_len=finale_len))
    assert check.passed is ok
    if not ok:
        assert "finale" in check.detail


def test_t3_names_a_missing_finale_beat() -> None:
    plan = _plan([_beat("b1", 0.0, 1.0)], "nope")
    check = technical.t3(_info(), plan)
    assert not check.passed
    assert "nope" in check.detail


def test_t3_on_an_over_long_real_file(media: Media) -> None:
    info = ffmpeg.probe(media.clip(duration_s=60.5, width=180, height=320, ext=".mp4"))
    check = technical.t3(info, _good_plan())
    assert not check.passed
    assert "60.5" in check.detail


# --- T4 master loudness ------------------------------------------------------------------


def _loud(integrated: float = -14.0, true_peak: float = -1.5) -> Loudness:
    return Loudness(
        integrated=integrated, true_peak=true_peak, lra=5.0, threshold=-24.0, offset=0.0
    )


@pytest.mark.parametrize(
    ("integrated", "true_peak", "ok"),
    [
        (-14.0, -1.5, True),
        (-14.5, -1.5, True),
        (-13.5, -1.5, True),
        (-14.51, -1.5, False),
        (-13.49, -1.5, False),
        (-14.0, -1.49, False),
        (-14.0, -3.0, True),
    ],
)
def test_t4_master_within_half_lu_and_under_true_peak(
    integrated: float, true_peak: float, ok: bool
) -> None:
    check = technical.t4(_loud(integrated, true_peak))
    assert check.name == "T4"
    assert check.passed is ok
    assert "LUFS" in check.detail and "dBTP" in check.detail


def test_t4_on_a_quiet_real_master(media: Media) -> None:
    quiet = media.clip(duration_s=2.0, amplitude=0.01, ext=".mp4")
    check = technical.t4(ffmpeg.measure_loudness(quiet))
    assert not check.passed


# --- run(job) ------------------------------------------------------------------------------


def _job_with(tmp_path: Path, short: Path, plan: PicturePlan) -> jobs.Job:
    job = jobs.create(tmp_path)
    (job.work_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (job.out_dir / "short.mp4").write_bytes(short.read_bytes())
    return job


def test_run_writes_qa_json_with_every_check_passing(media: Media, tmp_path: Path) -> None:
    # A 440 Hz sine at 0.3 full scale measures about -14.2 LUFS (0.28 measured -14.8).
    job = _job_with(tmp_path, media.clip(duration_s=2.0, amplitude=0.3, ext=".mp4"), _good_plan())
    report = technical.run(job)
    assert report.passed
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4"]
    on_disk = QaReport.model_validate_json((job.out_dir / "qa.json").read_text(encoding="utf-8"))
    assert on_disk == report
    assert all(c.detail for c in on_disk.checks)


def test_run_stops_at_the_first_failure_and_names_it(media: Media, tmp_path: Path) -> None:
    job = _job_with(
        tmp_path, media.clip(duration_s=2.0, width=720, height=1280, ext=".mp4"), _good_plan()
    )
    report = technical.run(job)
    assert not report.passed
    assert [c.name for c in report.checks] == ["T1"]
    assert report.failed is not None and report.failed.name == "T1"
    written = json.loads((job.out_dir / "qa.json").read_text(encoding="utf-8"))
    assert written["passed"] is False
    assert written["checks"][0]["name"] == "T1"


def test_run_reaches_t3_when_the_plan_is_the_problem(media: Media, tmp_path: Path) -> None:
    job = _job_with(tmp_path, media.clip(duration_s=2.0, ext=".mp4"), _good_plan(finale_len=0.5))
    report = technical.run(job)
    assert [c.name for c in report.checks] == ["T1", "T2", "T3"]
    assert report.failed is not None and report.failed.name == "T3"
