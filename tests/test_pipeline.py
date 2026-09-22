"""pipeline: the worker runs a job's steps in order (11.1), one job at a time in
submission order (9.1). Transcribing, planning, the sourcing placeholder, rendering
and the technical gate exist; a job that passes the gate with its deliverables on
disk is `delivered` (10.4). A failing step marks the job `failed` with the step named
and a fixed message; a failed check names itself in the message. Tests render through
`FakeRenderer` and gate through `FakeGate`; the real paths are covered by
test_render, test_qa_technical, test_contact_sheet and smoke."""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import jobs, pipeline, render, styles, subproc
from shortsmith.contracts import PicturePlan, PlanRequest, SoundStory, Transcript
from shortsmith.planner import FakePlanner, Planner, PlannerUnavailable, UnavailablePlanner
from shortsmith.qa.gate import FakeGate, Gate
from shortsmith.render import FakeRenderer, Renderer
from shortsmith.transcriber import FakeTranscriber, Transcriber
from tests.conftest import Media

BRIEF = "Topic: nothing. Angle: prove the pipeline. Must-say: twelve words. Hook wish: none."
TRAIL = [
    "created uploaded",
    "uploaded -> transcribing",
    "transcribing -> planning",
    "planning -> sourcing",
    "sourcing -> rendering",
    "rendering -> qa",
    "qa -> delivered",
]


def _uploaded(data_dir: Path, clip: Path) -> jobs.Job:
    job = jobs.create(data_dir, style="explainer", style_note="explainer, energetic")
    shutil.copyfile(clip, job.input_dir / "raw.mp4")
    (job.input_dir / "brief.md").write_text(BRIEF, encoding="utf-8")
    (job.input_dir / "refs.json").write_text("[]", encoding="utf-8")
    return job


def _run(job: jobs.Job, *, transcriber: Transcriber | None = None,
         planner: Planner | None = None, renderer: Renderer | None = None,
         gate: Gate | None = None) -> jobs.Job:  # fmt: skip
    return pipeline.run_job(
        job,
        transcriber=transcriber or FakeTranscriber(),
        planner=planner or FakePlanner(),
        renderer=renderer or FakeRenderer(),
        gate=gate or FakeGate(),
    )


def _worker(transcriber: Transcriber | None = None, **kwargs: object) -> pipeline.Worker:
    return pipeline.Worker(
        transcriber=transcriber or FakeTranscriber(), planner=FakePlanner(),
        renderer=FakeRenderer(), gate=FakeGate(), **kwargs,  # pyright: ignore[reportArgumentType]
    )  # fmt: skip


def _pages(job: jobs.Job) -> list[dict[str, object]]:
    return json.loads((job.work_dir / "captions.json").read_text(encoding="utf-8"))


def test_run_job_transcribes_plans_renders_gates_and_delivers(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job)
    assert done.status == "delivered"
    assert (job.out_dir / "qa.json").is_file()
    assert (job.out_dir / "contact.jpg").is_file()
    asr = Transcript.model_validate_json((job.work_dir / "asr.json").read_text(encoding="utf-8"))
    assert len(asr.words) == 12
    log = [line.split(" ", 1)[1] for line in job.log_path.read_text("utf-8").splitlines()]
    assert log == TRAIL


class _Watching(FakeRenderer):
    """Reads job.json while progress is reported, the way the job page's poll does."""

    def __init__(self) -> None:
        super().__init__()
        self.on_disk: list[int | None] = []

    def render(self, job: jobs.Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        def spy(pct: int) -> None:
            if on_progress is not None:
                on_progress(pct)
            self.on_disk.append(jobs.load(job.path).record.progress)

        return super().render(job, on_progress=spy)


def test_rendering_step_reports_progress_into_job_json(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    renderer = _Watching()
    done = _run(job, renderer=renderer)
    assert done.status == "delivered"
    assert renderer.jobs == [job.path]
    assert renderer.on_disk == [0, 50, 100]  # each report landed in job.json before the next
    assert jobs.load(job.path).record.status == "delivered"
    assert (job.work_dir / "picture.mp4").is_file()
    # 005: the fake stands in for the whole step, so every file the step leaves exists.
    assert (job.work_dir / "cut.mp4").is_file()
    assert (job.work_dir / "stems" / "voice.wav").is_file()
    assert (job.work_dir / "stems" / "mix.wav").is_file()
    assert (job.out_dir / "short.mp4").is_file()


class _BrokenRenderer(FakeRenderer):
    def render(self, job: jobs.Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        raise render.RenderError("remotion driver exited 1:\nno frame found")


def test_a_failing_render_fails_the_job_at_rendering(tmp_path: Path, fixture_clip: Path) -> None:
    done = _run(_uploaded(tmp_path, fixture_clip), renderer=_BrokenRenderer())
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "rendering"
    assert done.record.error.message == pipeline.STEP_MESSAGES["rendering"]
    assert "no frame found" in done.record.error.detail


def test_sourcing_is_a_placeholder_that_writes_nothing_until_016(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    _run(job)
    assert not (job.work_dir / "assets").exists()


def test_a_failed_check_fails_the_job_at_qa_and_names_the_check(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    done = _run(job, gate=FakeGate(fail="T2"))
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "qa"
    assert done.record.error.message == "The short failed a technical check (T2)."
    assert (job.out_dir / "qa.json").is_file()  # the report is written either way (10.1)
    assert not (job.out_dir / "contact.jpg").exists()  # no sheet from a failed short
    log = [line.split(" ", 1)[1] for line in job.log_path.read_text("utf-8").splitlines()]
    assert log[-1].startswith("qa -> failed step=qa")


class _SheetlessGate(FakeGate):
    def contact_sheet(self, job: jobs.Job) -> Path:
        return job.out_dir / "contact.jpg"  # never written


def test_missing_deliverables_fail_the_job_at_qa(tmp_path: Path, fixture_clip: Path) -> None:
    done = _run(_uploaded(tmp_path, fixture_clip), gate=_SheetlessGate())
    assert done.status == "failed"
    assert done.record.error is not None
    assert done.record.error.step == "qa"
    assert "contact.jpg" in done.record.error.detail


def test_the_worker_gates_through_the_technical_gate_by_default() -> None:
    from shortsmith.qa.gate import TechnicalGate

    worker = pipeline.Worker(transcriber=FakeTranscriber(), planner=FakePlanner())
    assert isinstance(worker._gate, TechnicalGate)  # pyright: ignore[reportPrivateUsage]


def test_the_worker_renders_through_remotion_by_default() -> None:
    worker = pipeline.Worker(transcriber=FakeTranscriber(), planner=FakePlanner())
    assert isinstance(worker._renderer, render.RemotionRenderer)  # pyright: ignore[reportPrivateUsage]


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
    """2.3: brief verbatim, the loaded style spec (numbers + prose, 1.2), the style
    line as the note, the fixed transcript, references as captioned lines, constraints,
    asset policy."""
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
    assert req.style.name == "explainer" and req.style.status == "shipped"
    assert "## Beat grammar" in req.style.prose and "7.1" in req.style.prose
    numbers = req.style.numbers
    assert numbers["beats"]["min_s"] == 0.7 and numbers["presenter"]["pip_max_run"] == 6  # type: ignore[index]
    assert numbers["sound"]["forbidden"] == ["sweep", "riser", "rumble_crescendo", "whoosh"]  # type: ignore[index]
    assert req.style_note == "explainer, energetic"
    assert len(req.transcript.words) == 12
    assert [(r.id, r.kind, r.caption, r.width) for r in req.references] == [
        ("ref1", "image", "my product", 1200)
    ]
    assert req.constraints.max_duration_s == 60.0
    assert req.constraints.target_duration_s == 6.0
    assert req.asset_policy in ("any", "rights_safe")


def test_a_job_whose_style_is_unknown_fails_at_planning_naming_it(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _uploaded(tmp_path, fixture_clip)
    record = job.record.model_copy(update={"style": "retro"})
    job.json_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    done = _run(jobs.load(job.path))
    assert done.status == "failed"
    assert done.record.error is not None and done.record.error.step == "planning"
    assert "retro" in done.record.error.detail


def test_the_pager_reads_words_per_page_from_the_style(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """6.1: `captions.words_per_page` / `prefer` come from front matter, not code."""
    job = _uploaded(tmp_path, fixture_clip)
    specs = styles.load_all(render.registry())
    wide = specs["explainer"].model_copy(deep=True)
    wide.captions.words_per_page = (2, 6)
    wide.captions.prefer = 6
    pipeline.run_job(
        job, transcriber=FakeTranscriber(), planner=FakePlanner(), renderer=FakeRenderer(),
        gate=FakeGate(), specs={"explainer": wide},
    )  # fmt: skip
    assert [len(p["word_indices"]) for p in _pages(job)] == [6, 6]  # type: ignore[arg-type]


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
    worker = _worker()
    worker.submit(first.path)
    worker.submit(second.path)
    assert worker.pending() == [first.path, second.path]

    assert worker.run_next() is True
    assert jobs.load(first.path).status == "delivered"
    assert jobs.load(second.path).status == "uploaded"
    assert worker.pending() == [second.path]

    assert worker.run_next() is True
    assert jobs.load(second.path).status == "delivered"
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
    worker = _worker(transcriber=transcriber)
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
        while time.monotonic() < deadline and jobs.load(second.path).status != "delivered":
            time.sleep(0.05)
        assert jobs.load(first.path).status == "delivered"
        assert jobs.load(second.path).status == "delivered"
    finally:
        transcriber.release.set()
        worker.stop()


def test_worker_survives_a_failing_job(tmp_path: Path, fixture_clip: Path) -> None:
    worker = _worker(transcriber=_Broken())
    job = _uploaded(tmp_path, fixture_clip)
    worker.submit(job.path)
    assert worker.run_next() is True
    assert jobs.load(job.path).status == "failed"


def test_worker_skips_a_job_that_vanished(tmp_path: Path) -> None:
    worker = _worker()
    worker.submit(tmp_path / "jobs" / "20260920-090000-abcdef")
    assert worker.run_next() is True
    assert worker.pending() == []


# --- ticket 041: queue depth, positions, job-minute kill (decisions 9.1, 11.2) -----


def test_fourth_submission_is_refused_at_max_queue_three(
    tmp_path: Path, fixture_clip: Path
) -> None:
    worker = _worker(max_queue=3)
    submitted = [_uploaded(tmp_path, fixture_clip) for _ in range(4)]
    for job in submitted[:3]:
        worker.submit(job.path)
    with pytest.raises(pipeline.QueueFull):
        worker.submit(submitted[3].path)
    assert worker.pending() == [j.path for j in submitted[:3]]
    assert worker.run_next() is True
    worker.submit(submitted[3].path)  # a slot is free again
    assert worker.pending() == [j.path for j in submitted[1:]]


def test_a_reservation_counts_toward_the_depth_until_released(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """The upload route reserves before it reads the body so a refused upload costs
    nothing; a rejected upload releases, an accepted one hands the slot to submit."""
    worker = _worker(max_queue=2)
    worker.reserve()
    worker.reserve()
    with pytest.raises(pipeline.QueueFull):
        worker.reserve()
    job, other = _uploaded(tmp_path, fixture_clip), _uploaded(tmp_path, fixture_clip)
    worker.submit(job.path, reserved=True)  # one reservation became a waiting job
    assert worker.depth() == 2
    with pytest.raises(pipeline.QueueFull):
        worker.submit(other.path)
    worker.release()  # the other upload was rejected
    worker.submit(other.path)
    assert worker.pending() == [job.path, other.path]
    assert worker.depth() == 2


def test_waiting_jobs_know_their_position_and_it_moves_as_jobs_finish(
    tmp_path: Path, fixture_clip: Path
) -> None:
    worker = _worker()
    first, second, third = (_uploaded(tmp_path, fixture_clip) for _ in range(3))
    for job in (first, second, third):
        worker.submit(job.path)
    assert [worker.position(j.path) for j in (first, second, third)] == [1, 2, 3]
    assert worker.run_next() is True
    assert worker.position(first.path) is None
    assert [worker.position(j.path) for j in (second, third)] == [1, 2]
    assert worker.run_next() is True
    assert worker.position(third.path) == 1


def test_the_running_job_has_no_position_but_still_counts_toward_the_depth(
    tmp_path: Path, fixture_clip: Path
) -> None:
    transcriber = _Blocking()
    worker = _worker(transcriber=transcriber, max_queue=3)
    first, second, third, fourth = (_uploaded(tmp_path, fixture_clip) for _ in range(4))
    worker.start()
    try:
        worker.submit(first.path)
        assert transcriber.started.wait(timeout=10)
        worker.submit(second.path)
        worker.submit(third.path)
        assert worker.position(first.path) is None
        assert [worker.position(j.path) for j in (second, third)] == [1, 2]
        with pytest.raises(pipeline.QueueFull):
            worker.submit(fourth.path)
    finally:
        transcriber.release.set()
        worker.stop()


T0 = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)


class _JumpingClock:
    """T0 until `jump` is set, then T0 plus `minutes`: the fake clock for the kill."""

    def __init__(self, minutes: float) -> None:
        self.jump = threading.Event()
        self.after = T0 + timedelta(minutes=minutes)

    def __call__(self) -> datetime:
        return self.after if self.jump.is_set() else T0


class _SleepsInAChild(Transcriber):
    """A step that spends its time in a subprocess, the way ffmpeg and Remotion will."""

    def __init__(self, clock: _JumpingClock) -> None:
        self.clock = clock
        self.outcome: str = "not run"

    def transcribe(self, audio: Path) -> Transcript:
        self.clock.jump.set()
        try:
            subproc.run([sys.executable, "-c", "import time; time.sleep(60)"])
        except subproc.Killed:
            self.outcome = "killed"
            raise
        self.outcome = "finished"
        return FakeTranscriber().transcribe(audio)


def test_past_max_job_minutes_the_step_process_is_killed_and_the_next_job_starts(
    tmp_path: Path, fixture_clip: Path
) -> None:
    clock = _JumpingClock(minutes=31)
    transcriber = _SleepsInAChild(clock)
    worker = _worker(
        transcriber=transcriber, max_job_minutes=30, clock=clock, watchdog_interval_s=0.02
    )
    first, second = _uploaded(tmp_path, fixture_clip), _uploaded(tmp_path, fixture_clip)
    worker.submit(first.path)
    worker.submit(second.path)

    started = time.monotonic()
    assert worker.run_next() is True
    assert time.monotonic() - started < 20  # the child slept for 60 s; it was killed
    assert transcriber.outcome == "killed"
    failed = jobs.load(first.path)
    assert failed.status == "failed"
    assert failed.record.error is not None
    assert failed.record.error.step == "transcribing"
    assert "job exceeded 30 minutes" in failed.record.error.message

    worker._transcriber = FakeTranscriber()  # pyright: ignore[reportPrivateUsage]
    assert worker.run_next() is True
    assert jobs.load(second.path).status == "delivered"


class _SlowInProcess(Transcriber):
    """A step with no subprocess cannot be interrupted; it fails on return."""

    def __init__(self, clock: _JumpingClock) -> None:
        self.clock = clock

    def transcribe(self, audio: Path) -> Transcript:
        self.clock.jump.set()
        return FakeTranscriber().transcribe(audio)


def test_a_step_that_returns_after_the_deadline_still_fails_the_job(
    tmp_path: Path, fixture_clip: Path
) -> None:
    clock = _JumpingClock(minutes=30)  # exactly the limit counts as exceeded
    job = _uploaded(tmp_path, fixture_clip)
    result = pipeline.run_job(
        job,
        transcriber=_SlowInProcess(clock),
        planner=FakePlanner(),
        renderer=FakeRenderer(),
        max_job_minutes=30,
        clock=clock,
    )
    assert result.status == "failed"
    assert result.record.error is not None
    assert result.record.error.step == "transcribing"
    assert "job exceeded 30 minutes" in result.record.error.message
    assert not (job.work_dir / "plan.json").exists()


def test_a_job_within_the_limit_is_untouched(tmp_path: Path, fixture_clip: Path) -> None:
    clock = _JumpingClock(minutes=29.9)
    job = _uploaded(tmp_path, fixture_clip)
    result = pipeline.run_job(
        job, transcriber=_SlowInProcess(clock), planner=FakePlanner(), renderer=FakeRenderer(),
        gate=FakeGate(), max_job_minutes=30, clock=clock,
    )  # fmt: skip
    assert result.status == "delivered"
