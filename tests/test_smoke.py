"""`python -m shortsmith.smoke`: fixture -> job -> fake transcriber -> fake planner ->
work/{asr,plan,sound,captions}.json, uploaded -> transcribing -> planning -> sourcing,
exit 0 with one summary line, non-zero on a failed assertion."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from shortsmith import smoke
from shortsmith.contracts import PicturePlan, PlanRequest, SoundStory, Transcript
from shortsmith.jobs import load
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber, Transcriber


def test_run_smoke_walks_the_path(tmp_path: Path) -> None:
    result = smoke.run_smoke(tmp_path)
    job = load(result.job_dir)
    assert job.status == "sourcing"
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
    log = job.log_path.read_text(encoding="utf-8").splitlines()
    assert [line.split(" ", 1)[1] for line in log] == [
        "created uploaded",
        "uploaded -> transcribing",
        "transcribing -> planning",
        "planning -> sourcing",
    ]
    assert "ok" in result.summary and job.id in result.summary


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
