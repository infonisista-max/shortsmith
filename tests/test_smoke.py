"""`python -m shortsmith.smoke`: fixture -> job -> fake transcriber -> fake planner ->
work/{asr,plan,sound,captions}.json -> Remotion -> work/picture.mp4 -> out/short.mp4
-> assets through the fake sources, out/rights.json and out/credits.md (016) ->
T1-T13 in out/qa.json -> out/contact.jpg, uploaded -> transcribing -> planning ->
sourcing -> rendering -> qa -> delivered, exit 0 with one summary line, non-zero on a
failed assertion. The render is the real engine (12.1), so the walk is the slow test
in the suite."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from shortsmith import assets, contact_sheet, ffmpeg, rights, smoke
from shortsmith.contracts import (
    PicturePlan,
    PlanFeedback,
    PlanRequest,
    RenderSpec,
    SoundStory,
    Transcript,
    ValidatedPlan,
)
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
    # 009: the grammar ran; the fake plan's only clamp is the keyword trim (6.1).
    validated = ValidatedPlan.model_validate_json(
        (job.work_dir / "plan.validated.json").read_text("utf-8")
    )
    assert validated.picture == plan and [c.rule for c in validated.clamps] == ["6.1"]
    assert (job.work_dir / "plan.raw.json").is_file()
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
    assert [c.name for c in report.checks] == list(technical.CHECK_ORDER)
    # 031 / 032: every check ran on the real short and the real files, and passed.
    assert all(c.status == "pass" for c in report.checks)
    # 033: the fake critic scored the delivered short from the real strips, advisory.
    assert report.critic is not None and report.critic.status == "scored"
    assert report.critic.advisory is True and report.critic.model == "fake"
    assert len(report.critic.lines) == 10 and report.critic.category == plan.category
    # 016: every sourced beat found its picture through the fakes, none rescued; the
    # photo beat is a full-bleed photo, the card beat a card; the rights log is complete.
    manifest = assets.load_manifest(job.path)
    assert manifest is not None and manifest.rescued == 0
    assert [b.beat_id for b in manifest.beats] == [
        b.id for b in plan.beats
        if b.subject_kind is not None and b.kind not in assets.NOT_SOURCED
    ]  # fmt: skip
    # 020: the map beat is drawn, not sourced, and its markers are fake-geocoded
    spec = RenderSpec.model_validate_json((job.work_dir / "render_spec.json").read_text("utf-8"))
    layout = next(b for b in spec.beats if b.kind == "map").map
    assert layout is not None and [m.source for m in layout.markers] == ["fake", "fake"]
    treatments = {b.beat_id: b.treatment for b in manifest.beats}
    assert (treatments["b03"], treatments["b04"]) == ("photo", "card")
    rows = rights.load(job.path)
    assert rows is not None and rights.completeness(rows, manifest, plan) == []
    assert (job.out_dir / "credits.md").read_text("utf-8").startswith("Photo: fake ")
    sheet = job.out_dir / "contact.jpg"
    assert sheet.is_file() and sheet.stat().st_size < contact_sheet.MAX_BYTES
    with Image.open(sheet) as image:
        assert image.format == "JPEG" and image.width == contact_sheet.SHEET_W
    log = job.log_path.read_text(encoding="utf-8").splitlines()
    noted = [line.split(" ", 1)[1] for line in log]
    # 022: the steps' own notes sit between the status lines, so the trail is the status
    # lines alone; the sound director's summary is one of those notes, inside `rendering`.
    assert [line for line in noted if line == "created uploaded" or " -> " in line] == [
        "created uploaded",
        "uploaded -> transcribing",
        "transcribing -> planning",
        "planning -> sourcing",
        "sourcing -> rendering",
        "rendering -> qa",
        "qa -> delivered",
    ]
    (sound_note,) = [line for line in noted if line.startswith("sound: bed ")]
    assert noted.index("sourcing -> rendering") < noted.index(sound_note) < noted.index(
        "rendering -> qa"
    )
    assert "ok" in result.summary and job.id in result.summary
    assert "180 frames" in result.summary and "short" in result.summary
    assert "T1 T2 T3 T4 T5 T6 T7 T8 T9 T10 T11 T12 T13 pass" in result.summary
    assert f"critic {report.critic.overall}/10 advisory" in result.summary
    assert "not implemented" not in result.summary and "contact" in result.summary
    assert f"{len(manifest.assets)} assets" in result.summary


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
    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        plan = super().plan_picture(request)
        first = plan.beats[0].model_copy(update={"end": plan.beats[0].end - 0.1})
        return plan.model_copy(update={"beats": [first, *plan.beats[1:]]})


def test_plan_assertion_failure_names_the_gap(capsys: pytest.CaptureFixture[str]) -> None:
    """009: the grammar now catches the gap at `planning` (3.1), twice, and the smoke
    reports the failed job with the violation list."""
    assert smoke.main([], planner=_GappyPlanner()) != 0
    err = capsys.readouterr().err
    assert "failed at planning" in err and "gap" in err and "(3.1)" in err


def test_module_entry_point() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "shortsmith.smoke"], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("smoke ok")
