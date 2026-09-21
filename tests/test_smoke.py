"""`python -m shortsmith.smoke`: fixture -> job -> fake transcriber -> fake planner ->
work/{asr,plan,sound,captions}.json -> Remotion -> work/picture.mp4 -> out/short.mp4
-> T1-T4 in out/qa.json -> out/contact.jpg, uploaded -> transcribing -> planning ->
sourcing -> rendering -> qa -> delivered, exit 0 with one summary line, non-zero on a
failed assertion. The render is the real engine (12.1), so the walk is the slow test
in the suite."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from shortsmith import contact_sheet, ffmpeg, smoke
from shortsmith.contracts import PicturePlan, PlanRequest, SoundStory, Transcript
from shortsmith.jobs import load
from shortsmith.planner import FakePlanner
from shortsmith.qa import technical
from shortsmith.transcriber import FakeTranscriber, Transcriber


def test_run_smoke_walks_the_path(tmp_path: Path) -> None:
    result = smoke.run_smoke(tmp_path)
    job = load(result.job_dir)
    assert job.status == "delivered"
    assert (job.input_dir / "raw.mp4").is_file()
    assert (job.input_dir / "brief.md").is_file()
    assert (job.input_dir / "refs.json").is_file()
    assert job.record.input is not None and job.record.input.width == 1080
    asr = Transcript.model_validate_json((job.work_dir / "asr.json").read_text(encoding="utf-8"))
    assert len(asr.words) == 12
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    SoundStory.model_validate_json((job.work_dir / "sound.json").read_text("utf-8"))
    assert (job.work_dir / "captions.json").is_file()
    assert plan.beats[-1].end == 6.0
    picture = job.work_dir / "picture.mp4"
    assert picture.is_file() and (job.work_dir / "render_spec.json").is_file()
    (video,) = ffmpeg.probe(picture)["streams"]
    assert video["codec_name"] == "h264" and int(video["nb_frames"]) == 180
    # 005: the cut, the stems and the muxed short with the picture stream untouched.
    cut = ffmpeg.probe(job.work_dir / "cut.mp4")["streams"]
    assert [s["codec_type"] for s in cut] == ["video", "audio"]
    assert int(cut[0]["has_b_frames"]) == 0 and cut[0]["avg_frame_rate"] == "30/1"
    assert (job.work_dir / "stems" / "voice.wav").is_file()
    assert (job.work_dir / "stems" / "mix.wav").is_file()
    short = job.out_dir / "short.mp4"
    assert short.is_file()
    assert {s["codec_type"] for s in ffmpeg.probe(short)["streams"]} == {"video", "audio"}
    assert ffmpeg.video_md5(short) == ffmpeg.video_md5(picture)
    assert float(ffmpeg.probe(short)["format"]["duration"]) == pytest.approx(6.0, abs=0.1)
    assert ffmpeg.measure_loudness(short).integrated == pytest.approx(-14.0, abs=1.0)
    # 006: the technical gate and the contact sheet, then `delivered`.
    report = technical.load_report(job)
    assert report is not None and report.passed
    assert [c.name for c in report.checks] == ["T1", "T2", "T3", "T4"]
    sheet = job.out_dir / "contact.jpg"
    assert sheet.is_file() and sheet.stat().st_size < contact_sheet.MAX_BYTES
    with Image.open(sheet) as image:
        assert image.format == "JPEG" and image.width == contact_sheet.SHEET_W
    log = job.log_path.read_text(encoding="utf-8").splitlines()
    assert [line.split(" ", 1)[1] for line in log] == [
        "created uploaded",
        "uploaded -> transcribing",
        "transcribing -> planning",
        "planning -> sourcing",
        "sourcing -> rendering",
        "rendering -> qa",
        "qa -> delivered",
    ]
    assert "ok" in result.summary and job.id in result.summary
    assert "180 frames" in result.summary and "short" in result.summary
    assert "T1-T4 pass" in result.summary and "contact" in result.summary


def test_main_prints_one_line_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main([]) == 0
    out = capsys.readouterr()
    assert out.out.count("\n") == 1
    assert out.out.startswith("smoke ok")


class _ShortTranscriber(Transcriber):
    def transcribe(self, audio: Path) -> Transcript:
        full = FakeTranscriber().transcribe(audio)
        return full.model_copy(update={"words": full.words[:3]})


def test_failed_assertion_exits_non_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main([], transcriber=_ShortTranscriber()) != 0
    out = capsys.readouterr()
    assert out.out == ""
    assert "smoke FAILED" in out.err and "12" in out.err


class _GappyPlanner(FakePlanner):
    def plan_picture(self, request: PlanRequest) -> PicturePlan:
        plan = super().plan_picture(request)
        first = plan.beats[0].model_copy(update={"end": plan.beats[0].end - 0.1})
        return plan.model_copy(update={"beats": [first, *plan.beats[1:]]})


def test_plan_assertion_failure_names_the_gap(capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main([], planner=_GappyPlanner()) != 0
    assert "gap" in capsys.readouterr().err


def test_module_entry_point() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "shortsmith.smoke"], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("smoke ok")
