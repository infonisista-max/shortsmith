"""qa.technical: T1-T4 (decision 10.1), the 016 rescue limit (reported as T8 until 032
completes it) and T9 rights completeness, each with a passing and a failing input, the
boundaries on both sides, and `run(job)` stopping at the first FAIL and writing
`out/qa.json`. Boundary cases use ffprobe-shaped dicts and `Loudness` values; the
real-file cases encode small synthetic clips (12.1: never a committed video)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from shortsmith import assets, ffmpeg, jobs, rights, sound
from shortsmith.contracts import (
    AssetManifest,
    AssetRecord,
    Beat,
    BeatAsset,
    CueRecord,
    CueSheet,
    CutPlan,
    Finale,
    Hook,
    PicturePlan,
    Span,
)
from shortsmith.ffmpeg import Loudness
from shortsmith.qa import technical
from shortsmith.qa.technical import QaReport
from shortsmith.sound import sweep
from tests.conftest import Media, Sounds

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


# --- T8 rescue limit (4.4; the rest of T8 is ticket 032) ------------------------------------


def _owner(asset_id: str) -> AssetRecord:
    return AssetRecord(id=asset_id, origin="owner_supplied", licence="owner",
                       file=f"input/refs/{asset_id}.png", sha256="0" * 64, width=1080,
                       height=1920, fetched_at="2026-09-22T12:00:00+00:00")  # fmt: skip


def _manifest(records: list[AssetRecord], beats: list[BeatAsset], *, rescued_max: int = 4,
              runtime_s: float = 60.0) -> AssetManifest:  # fmt: skip
    return AssetManifest(assets=records, beats=beats, runtime_s=runtime_s,
                         rescued_max=rescued_max)  # fmt: skip


def _rescues(n: int, total: int = 12) -> list[BeatAsset]:
    return [
        BeatAsset(beat_id=f"b{i:02d}", asset_id=None if i < n else "a1",
                  treatment="gradient" if i < n else "card", fallback_rung=4 if i < n else 0)
        for i in range(total)
    ]  # fmt: skip


def test_t8_four_rescues_in_sixty_seconds_pass() -> None:
    check = technical.t8(_manifest([_owner("a1")], _rescues(4)))
    assert (check.name, check.passed) == ("T8", True)
    assert "4 rescued beats (max 4" in check.detail


def test_t8_the_fifth_rescue_fails_with_not_enough_relevant_broll() -> None:
    check = technical.t8(_manifest([_owner("a1")], _rescues(5)))
    assert not check.passed
    assert check.detail.startswith("not enough relevant B-roll")
    assert "5 rescued beats (max 4" in check.detail


def test_t8_counts_rung_3_as_a_rescue() -> None:
    beats = [BeatAsset(beat_id="b1", asset_id="a1", treatment="card", fallback_rung=3),
             BeatAsset(beat_id="b2", asset_id="a1", treatment="card", fallback_rung=2)]  # fmt: skip
    assert not technical.t8(_manifest([_owner("a1")], beats, rescued_max=0)).passed
    assert technical.t8(_manifest([_owner("a1")], beats, rescued_max=1)).passed


def test_t8_without_a_manifest_fails() -> None:
    check = technical.t8(None)
    assert not check.passed and "work/assets.json" in check.detail


# --- T9 rights completeness (5.4) ----------------------------------------------------------


def test_t9_passes_a_complete_log() -> None:
    plan = _good_plan()
    manifest = _manifest([_owner("a1")], [])
    check = technical.t9(rights.rows(manifest, plan), manifest, plan)
    assert (check.name, check.passed) == ("T9", True)
    assert check.detail == "1 rights row, every beat's asset logged"


def test_t9_fails_naming_each_problem() -> None:
    plan = _good_plan()
    manifest = _manifest([], [])
    check = technical.t9([], manifest, plan)
    assert not check.passed
    assert check.detail.startswith("b1: asset a1 has no rights row")


def test_t9_without_a_rights_log_fails() -> None:
    check = technical.t9(None, _manifest([], []), _good_plan())
    assert not check.passed and "out/rights.json" in check.detail


# --- T6 no sweep on the SFX stem (7.3) -------------------------------------------------------


def _sheet() -> CueSheet:
    return CueSheet(
        cues=[
            CueRecord(beat_id="b1", intent="bass", entry_id="sfx_bass", start_s=0.5, end_s=0.9),
            CueRecord(beat_id="b2", intent="reveal", entry_id="sfx_rise", start_s=2.0, end_s=4.0),
        ]
    )


def test_t6_without_an_sfx_stem_passes_with_its_reason() -> None:
    check = technical.t6(None, None)
    assert (check.name, check.passed) == ("T6", True)
    assert check.detail == (
        "no SFX stem: work/stems/sfx.wav is absent, so the short has no cues to scan"
    )


def test_t6_passes_a_clean_stem() -> None:
    check = technical.t6([], _sheet())
    assert (check.name, check.passed) == ("T6", True)
    assert check.detail == "R1-R4 clean on the SFX stem (2 cues)"


def test_t6_fails_naming_the_cue_sounding_at_the_hit() -> None:
    hit = sweep.Hit(rule="R2", at_s=2.1, detail="crescendo of 9.0 dB over 0.23 s")
    check = technical.t6([hit], _sheet())
    assert not check.passed
    assert check.detail == (
        "R2 at 2.10 s in cue sfx_rise on b2 ('reveal'): crescendo of 9.0 dB over 0.23 s"
    )


def test_t6_names_the_last_cue_before_a_hit_between_cues() -> None:
    hit = sweep.Hit(rule="R3", at_s=1.5, detail="one sound 5.10 s long")
    check = technical.t6([hit], _sheet())
    assert not check.passed and "cue sfx_bass on b1" in check.detail


def test_t6_says_so_when_no_cue_sounds_before_a_hit() -> None:
    hit = sweep.Hit(rule="R1", at_s=0.1, detail="flat")
    check = technical.t6([hit], _sheet())
    assert not check.passed and "no cue sounds there" in check.detail


def _with_sfx_stem(job: jobs.Job, source: Path, sheet: CueSheet) -> None:
    stems = job.work_dir / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, stems / "sfx.wav")
    (stems / sound.CUES_NAME).write_text(sheet.model_dump_json(indent=2), encoding="utf-8")


def test_run_fails_t6_naming_the_offending_cue(
    media: Media, sounds: Sounds, tmp_path: Path
) -> None:
    job = _job_with(tmp_path, media.clip(duration_s=2.0, ext=".mp4"), _good_plan())
    sheet = CueSheet(
        cues=[CueRecord(beat_id="b1", intent="whoosh", entry_id="sfx_noise", start_s=0.0,
                        end_s=1.0)]  # fmt: skip
    )
    _with_sfx_stem(job, sounds("noise_500ms"), sheet)
    report = technical.run(job)
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4", "T6"]
    assert report.failed is not None and report.failed.name == "T6"
    assert report.failed.detail.startswith("R1 at 0.00 s in cue sfx_noise on b1 ('whoosh')")


def test_run_passes_t6_on_a_clean_stem(media: Media, sounds: Sounds, tmp_path: Path) -> None:
    job = _job_with(tmp_path, media.clip(duration_s=2.0, ext=".mp4"), _good_plan())
    _with_sfx_stem(job, sounds("clicks"), _sheet())
    report = technical.run(job)
    t6 = next(c for c in report.checks if c.name == "T6")
    assert t6.passed and t6.detail == "R1-R4 clean on the SFX stem (2 cues)"


# --- run(job) ------------------------------------------------------------------------------


def _job_with(tmp_path: Path, short: Path, plan: PicturePlan,
              manifest: AssetManifest | None = None) -> jobs.Job:  # fmt: skip
    job = jobs.create(tmp_path)
    (job.work_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (job.out_dir / "short.mp4").write_bytes(short.read_bytes())
    manifest = manifest or _manifest([_owner("a1")], [])
    assets.write_manifest(job.path, manifest)
    rights.write(job.path, manifest, plan)
    return job


def test_run_writes_qa_json_with_every_check_passing(media: Media, tmp_path: Path) -> None:
    # A 440 Hz sine at 0.3 full scale measures about -14.2 LUFS (0.28 measured -14.8).
    job = _job_with(tmp_path, media.clip(duration_s=2.0, amplitude=0.3, ext=".mp4"), _good_plan())
    report = technical.run(job)
    assert report.passed
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4", "T6", "T8", "T9"]
    on_disk = QaReport.model_validate_json((job.out_dir / "qa.json").read_text(encoding="utf-8"))
    assert on_disk == report
    assert all(c.detail for c in on_disk.checks)
    t6 = next(c for c in on_disk.checks if c.name == "T6")
    assert t6.passed and "work/stems/sfx.wav is absent" in t6.detail, "never a bare pass"


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


def test_run_fails_t8_on_too_many_rescues(media: Media, tmp_path: Path) -> None:
    manifest = _manifest([_owner("a1")], _rescues(2, total=3), rescued_max=1, runtime_s=5.0)
    job = _job_with(tmp_path, media.clip(duration_s=2.0, ext=".mp4"), _good_plan(), manifest)
    report = technical.run(job)
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4", "T6", "T8"]
    assert report.failed is not None and report.failed.name == "T8"


def test_run_fails_t9_on_an_incomplete_log(media: Media, tmp_path: Path) -> None:
    job = _job_with(tmp_path, media.clip(duration_s=2.0, ext=".mp4"), _good_plan())
    (job.out_dir / "rights.json").write_text("[]", encoding="utf-8")
    report = technical.run(job)
    assert report.failed is not None and report.failed.name == "T9"
