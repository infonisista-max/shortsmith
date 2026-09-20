"""pipeline: the worker runs a job's steps in order (11.1), one job at a time in
submission order (9.1). Transcribing and planning exist; a job stops at `sourcing`.
A failing step marks the job `failed` with the step named and a fixed message."""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

import pytest

from shortsmith import jobs, pipeline
from shortsmith.contracts import PicturePlan, PlanRequest, SoundStory, Transcript
from shortsmith.planner import FakePlanner, Planner, PlannerUnavailable, UnavailablePlanner
from shortsmith.transcriber import FakeTranscriber, Transcriber
from tests.conftest import Media

BRIEF = "Topic: nothing. Angle: prove the pipeline. Must-say: twelve words. Hook wish: none."
TRAIL = [
    "created uploaded",
    "uploaded -> transcribing",
    "transcribing -> planning",
    "planning -> sourcing",
]


def _uploaded(data_dir: Path, clip: Path) -> jobs.Job:
    job = jobs.create(data_dir, style_line="explainer, energetic")
    shutil.copyfile(clip, job.input_dir / "raw.mp4")
    (job.input_dir / "brief.md").write_text(BRIEF, encoding="utf-8")
    (job.input_dir / "refs.json").write_text("[]", encoding="utf-8")
    return job


def _run(job: jobs.Job, *, transcriber: Transcriber | None = None,
         planner: Planner | None = None) -> jobs.Job:  # fmt: skip
    return pipeline.run_job(
        job, transcriber=transcriber or FakeTranscriber(), planner=planner or FakePlanner()
    )


def _pages(job: jobs.Job) -> list[dict[str, object]]:
    return json.loads((job.work_dir / "captions.json").read_text(encoding="utf-8"))


def test_run_job_transcribes_plans_and_stops_at_sourcing(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job)
    assert done.status == "sourcing"
    asr = Transcript.model_validate_json((job.work_dir / "asr.json").read_text(encoding="utf-8"))
    assert len(asr.words) == 12
    log = [line.split(" ", 1)[1] for line in job.log_path.read_text("utf-8").splitlines()]
    assert log == TRAIL


def test_planning_writes_plan_sound_and_captions(tmp_path: Path, fixture_clip: Path) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    _run(job)
    plan = PicturePlan.model_validate_json((job.work_dir / "plan.json").read_text("utf-8"))
    story = SoundStory.model_validate_json((job.work_dir / "sound.json").read_text("utf-8"))
    assert plan.beats[-1].end == 6.0 and story.cues
    pages = _pages(job)
    assert [len(p["word_indices"]) for p in pages] == [3, 3, 3, 3]  # type: ignore[arg-type]
    assert pages[-1]["end"] == 6.0  # last page clamped to the clip


class _Recording(FakePlanner):
    def __init__(self) -> None:
        self.requests: list[PlanRequest] = []

    def plan_picture(self, request: PlanRequest) -> PicturePlan:
        self.requests.append(request)
        return super().plan_picture(request)


def test_plan_request_is_built_from_the_job_files(
    tmp_path: Path, fixture_clip: Path, media: Media
) -> None:
    """2.3: brief verbatim, style (explainer until 008), the style line as the note,
    the fixed transcript, references as captioned lines, constraints, asset policy."""
    job = _uploaded(tmp_path, fixture_clip)
    ref = media.image(width=1200, height=1600)
    (job.input_dir / "refs").mkdir()
    shutil.copyfile(ref, job.input_dir / "refs" / "1_product.png")
    (job.input_dir / "refs.json").write_text(json.dumps([{
        "id": "ref1", "file": "refs/1_product.png", "kind": "image", "caption": "my product",
        "original_name": "product.png", "width": 1200, "height": 1600, "size_bytes": 10,
        "rights": "owner_supplied",
    }]), encoding="utf-8")  # fmt: skip
    planner = _Recording()
    _run(job, planner=planner)
    (req,) = planner.requests
    assert req.brief == BRIEF
    assert req.style.name == "explainer" and "Beat grammar" in req.style.prose
    assert req.style_note == "explainer, energetic"
    assert len(req.transcript.words) == 12
    assert [(r.id, r.kind, r.caption, r.width) for r in req.references] == [
        ("ref1", "image", "my product", 1200)
    ]
    assert req.constraints.max_duration_s == 60.0
    assert req.constraints.target_duration_s == 6.0
    assert req.asset_policy in ("any", "rights_safe")


def test_unavailable_planner_fails_the_job_at_planning_naming_the_ticket(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, planner=UnavailablePlanner("claude_code", "014"))
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "planning"
    assert done.record.error.message == pipeline.STEP_MESSAGES["planning"]
    assert "014" in done.record.error.detail
    assert PlannerUnavailable.__name__ in done.record.error.detail
    assert (job.work_dir / "asr.json").is_file()
    assert not (job.work_dir / "plan.json").exists()


class _Broken(Transcriber):
    def transcribe(self, audio: Path) -> Transcript:
        raise RuntimeError("groq said no")


def test_step_exception_marks_the_job_failed_at_that_step(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, transcriber=_Broken())
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
        _run(job)


def test_worker_runs_submissions_in_order_one_at_a_time(
    tmp_path: Path, fixture_clip: Path
) -> None:
    first = _uploaded(tmp_path, fixture_clip)
    second = _uploaded(tmp_path, fixture_clip)
    worker = pipeline.Worker(transcriber=FakeTranscriber(), planner=FakePlanner())
    worker.submit(first.path)
    worker.submit(second.path)
    assert worker.pending() == [first.path, second.path]

    assert worker.run_next() is True
    assert jobs.load(first.path).status == "sourcing"
    assert jobs.load(second.path).status == "uploaded"
    assert worker.pending() == [second.path]

    assert worker.run_next() is True
    assert jobs.load(second.path).status == "sourcing"
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
    worker = pipeline.Worker(transcriber=transcriber, planner=FakePlanner())
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
        while time.monotonic() < deadline and jobs.load(second.path).status != "sourcing":
            time.sleep(0.05)
        assert jobs.load(first.path).status == "sourcing"
        assert jobs.load(second.path).status == "sourcing"
    finally:
        transcriber.release.set()
        worker.stop()


def test_worker_survives_a_failing_job(tmp_path: Path, fixture_clip: Path) -> None:
    worker = pipeline.Worker(transcriber=_Broken(), planner=FakePlanner())
    job = _uploaded(tmp_path, fixture_clip)
    worker.submit(job.path)
    assert worker.run_next() is True
    assert jobs.load(job.path).status == "failed"


def test_worker_skips_a_job_that_vanished(tmp_path: Path) -> None:
    worker = pipeline.Worker(transcriber=FakeTranscriber(), planner=FakePlanner())
    worker.submit(tmp_path / "jobs" / "20260920-090000-abcdef")
    assert worker.run_next() is True
    assert worker.pending() == []
