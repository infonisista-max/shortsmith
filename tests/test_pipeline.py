"""pipeline: the worker runs a job's steps in order (11.1), one job at a time in
submission order (9.1). Only transcribing exists yet; a job stops at `planning`.
A failing step marks the job `failed` with the step named and a fixed message."""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

import pytest

from shortsmith import jobs, pipeline
from shortsmith.contracts import Transcript
from shortsmith.transcriber import FakeTranscriber, Transcriber


def _uploaded(data_dir: Path, clip: Path) -> jobs.Job:
    job = jobs.create(data_dir)
    shutil.copyfile(clip, job.input_dir / "raw.mp4")
    return job


def test_run_job_transcribes_and_stops_at_planning(tmp_path: Path, fixture_clip: Path) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = pipeline.run_job(job, transcriber=FakeTranscriber())
    assert done.status == "planning"
    asr = Transcript.model_validate_json((job.work_dir / "asr.json").read_text(encoding="utf-8"))
    assert len(asr.words) == 12
    log = [line.split(" ", 1)[1] for line in job.log_path.read_text("utf-8").splitlines()]
    assert log == ["created uploaded", "uploaded -> transcribing", "transcribing -> planning"]


class _Broken(Transcriber):
    def transcribe(self, audio: Path) -> Transcript:
        raise RuntimeError("groq said no")


def test_step_exception_marks_the_job_failed_at_that_step(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = pipeline.run_job(job, transcriber=_Broken())
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "transcribing"
    assert done.record.error.message == pipeline.STEP_MESSAGES["transcribing"]
    assert "groq said no" in done.record.error.detail
    assert jobs.load(job.path).status == "failed"


def test_run_job_refuses_a_job_that_is_not_uploaded(tmp_path: Path, fixture_clip: Path) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    job = jobs.transition(job, "transcribing")
    with pytest.raises(pipeline.NotRunnable):
        pipeline.run_job(job, transcriber=FakeTranscriber())


def test_worker_runs_submissions_in_order_one_at_a_time(
    tmp_path: Path, fixture_clip: Path
) -> None:
    first = _uploaded(tmp_path, fixture_clip)
    second = _uploaded(tmp_path, fixture_clip)
    worker = pipeline.Worker(transcriber=FakeTranscriber())
    worker.submit(first.path)
    worker.submit(second.path)
    assert worker.pending() == [first.path, second.path]

    assert worker.run_next() is True
    assert jobs.load(first.path).status == "planning"
    assert jobs.load(second.path).status == "uploaded"
    assert worker.pending() == [second.path]

    assert worker.run_next() is True
    assert jobs.load(second.path).status == "planning"
    assert worker.run_next() is False


class _Blocking(Transcriber):
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio: Path) -> Transcript:
        self.started.set()
        assert self.release.wait(timeout=10)
        return FakeTranscriber().transcribe(audio)


def test_worker_thread_keeps_the_second_job_uploaded_while_the_first_runs(
    tmp_path: Path, fixture_clip: Path
) -> None:
    transcriber = _Blocking()
    worker = pipeline.Worker(transcriber=transcriber)
    first = _uploaded(tmp_path, fixture_clip)
    second = _uploaded(tmp_path, fixture_clip)
    worker.start()
    try:
        worker.submit(first.path)
        worker.submit(second.path)
        assert transcriber.started.wait(timeout=10)
        assert jobs.load(first.path).status == "transcribing"
        assert jobs.load(second.path).status == "uploaded"
        transcriber.release.set()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and jobs.load(second.path).status != "planning":
            time.sleep(0.05)
        assert jobs.load(first.path).status == "planning"
        assert jobs.load(second.path).status == "planning"
    finally:
        transcriber.release.set()
        worker.stop()


def test_worker_survives_a_failing_job(tmp_path: Path, fixture_clip: Path) -> None:
    worker = pipeline.Worker(transcriber=_Broken())
    job = _uploaded(tmp_path, fixture_clip)
    worker.submit(job.path)
    assert worker.run_next() is True
    assert jobs.load(job.path).status == "failed"


def test_worker_skips_a_job_that_vanished(tmp_path: Path) -> None:
    worker = pipeline.Worker(transcriber=FakeTranscriber())
    worker.submit(tmp_path / "jobs" / "20260920-090000-abcdef")
    assert worker.run_next() is True
    assert worker.pending() == []
