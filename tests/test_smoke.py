"""`python -m shortsmith.smoke`: fixture -> job -> fake transcriber -> work/asr.json,
uploaded -> transcribing -> planning, exit 0 with one summary line, non-zero on a
failed assertion."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from shortsmith import smoke
from shortsmith.contracts import Transcript
from shortsmith.jobs import load
from shortsmith.transcriber import FakeTranscriber, Transcriber


def test_run_smoke_walks_the_path(tmp_path: Path) -> None:
    result = smoke.run_smoke(tmp_path)
    job = load(result.job_dir)
    assert job.status == "planning"
    assert (job.input_dir / "raw.mp4").is_file()
    assert (job.input_dir / "brief.md").is_file()
    assert (job.input_dir / "refs.json").is_file()
    assert job.record.input is not None and job.record.input.width == 1080
    asr = Transcript.model_validate_json((job.work_dir / "asr.json").read_text(encoding="utf-8"))
    assert len(asr.words) == 12
    log = job.log_path.read_text(encoding="utf-8").splitlines()
    assert [line.split(" ", 1)[1] for line in log] == [
        "created uploaded",
        "uploaded -> transcribing",
        "transcribing -> planning",
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


def test_module_entry_point() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "shortsmith.smoke"], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("smoke ok")
