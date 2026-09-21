"""The worker (PRD `pipeline`): runs a job's steps in the 11.1 order, one job at a time
in submission order (9.1).

`run_job` is the synchronous path: it takes an `uploaded` job through every step that
exists (today: transcribing, planning) and stops at the first status whose step has
no implementation yet (today: `sourcing`, ticket 016). Any exception inside a step
marks the job `failed` at that step with the fixed user-facing sentence from
`STEP_MESSAGES` and the exception text as `detail` (11.1).

The `planning` step builds the PlanRequest from `job.json`, `brief.md`, `refs.json`
and `work/asr.json` (2.3), calls the planner twice (picture, then sound; 8.1), pages
the captions (6.1) and writes `work/plan.json`, `work/sound.json`,
`work/captions.json`. The grammar validator between the two calls is ticket 009; the
style loader and resolver are ticket 008, so until then the style is always
`explainer` with its prose read from `styles/explainer.md`.

`Worker` wraps `run_job` in a FIFO queue on one daemon thread for the web app;
`run_next` drains one job synchronously so tests and smoke use the same code path
without threads.

Limits (11.2): the queue depth counts the running job, the waiting jobs and the
slots the upload route has reserved; `submit`/`reserve` raise `QueueFull` at
`max_queue`. A waiting job's position is its 1-based place among the waiting jobs.
`max_job_minutes` arms a `subproc.Watchdog` per job that kills the running step's
subprocesses at the deadline; whichever way the step then ends, the job is `failed`
at that step with "job exceeded N minutes" and the worker moves on.
"""

from __future__ import annotations

import logging
import queue
import threading
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import TypeAdapter

from shortsmith import captions, jobs, subproc
from shortsmith.captions import PagerNumbers
from shortsmith.contracts import (
    Constraints,
    PlanReference,
    PlanRequest,
    PlanStyle,
    ReferenceRecord,
    Transcript,
)
from shortsmith.jobs import Clock, Job, Status
from shortsmith.planner import Planner
from shortsmith.transcriber import Transcriber

log = logging.getLogger(__name__)

DEFAULT_MAX_QUEUE = 3
DEFAULT_MAX_JOB_MINUTES = 30


def _utc_now() -> datetime:
    return datetime.now(UTC)


def timeout_message(max_job_minutes: float) -> str:
    minutes = int(max_job_minutes) if float(max_job_minutes).is_integer() else max_job_minutes
    return f"The job exceeded {minutes} minutes and was stopped."

STEP_MESSAGES: dict[str, str] = {
    "transcribing": "We could not transcribe the recording.",
    "planning": "We could not plan the short.",
    "sourcing": "We could not find or make the pictures for the short.",
    "rendering": "We could not render the short.",
    "qa": "The short failed a technical check.",
}
LAST_IMPLEMENTED_STEP: Status = "planning"

STYLES_DIR = Path(__file__).resolve().parents[2] / "styles"
DEFAULT_STYLE = "explainer"  # the resolver (1.1) arrives with ticket 008
MAX_DURATION_S = 60.0  # 3.1 / T3; the style default target comes with 008
EXPLAINER_PAGER = PagerNumbers(words_per_page=(2, 4), prefer=3)  # front matter in 008

_REFS = TypeAdapter(list[ReferenceRecord])


class NotRunnable(Exception):
    """The job is not `uploaded`, so the worker has nothing to start."""


class QueueFull(Exception):
    """`max_queue` jobs are running, waiting or reserved; the submission is refused."""


Step = Callable[[Job], None]


def run_job(
    job: Job,
    *,
    transcriber: Transcriber,
    planner: Planner,
    max_job_minutes: float | None = None,
    clock: Clock = _utc_now,
    watchdog_interval_s: float = 1.0,
) -> Job:
    if job.status != "uploaded":
        raise NotRunnable(f"job {job.id} is {job.status!r}, not 'uploaded'")
    steps: list[tuple[Status, Step]] = [
        ("transcribing", lambda j: _transcribe(j, transcriber)),
        ("planning", lambda j: _plan(j, planner)),
    ]
    watchdog: subproc.Watchdog | None = None
    if max_job_minutes is not None:
        deadline = clock() + timedelta(minutes=max_job_minutes)
        watchdog = subproc.Watchdog(deadline=deadline, clock=clock, interval_s=watchdog_interval_s)
        watchdog.start()
    try:
        for status, step in steps:
            job = jobs.transition(job, status)
            detail = ""
            try:
                with subproc.guarded(watchdog):
                    step(job)
            except Exception as exc:  # noqa: BLE001 - every step failure lands in job.json the same way
                detail = f"{exc}\n{traceback.format_exc()}"
                if watchdog is None or not watchdog.check():
                    return jobs.fail(job, step=status, message=STEP_MESSAGES[status], detail=detail)
            if watchdog is not None and watchdog.check():
                assert max_job_minutes is not None
                return jobs.fail(
                    job, step=status, message=timeout_message(max_job_minutes), detail=detail
                )
    finally:
        if watchdog is not None:
            watchdog.stop()
    return jobs.transition(job, "sourcing")


def _transcribe(job: Job, transcriber: Transcriber) -> None:
    assert job.record.input is not None or (job.input_dir / "raw.mp4").is_file()
    raw = job.input_dir / (job.record.input.file if job.record.input else "raw.mp4")
    transcript = transcriber.transcribe(raw)
    (job.work_dir / "asr.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")


def build_plan_request(job: Job) -> PlanRequest:
    """PlanRequest per 2.3 from the job's files; nothing else reaches the planner."""
    transcript = Transcript.model_validate_json(
        (job.work_dir / "asr.json").read_text(encoding="utf-8")
    )
    brief = (job.input_dir / "brief.md").read_text(encoding="utf-8")
    refs_path = job.input_dir / "refs.json"
    refs = _REFS.validate_json(refs_path.read_text(encoding="utf-8")) if refs_path.is_file() else []
    style_path = STYLES_DIR / f"{DEFAULT_STYLE}.md"
    prose = style_path.read_text(encoding="utf-8") if style_path.is_file() else ""
    return PlanRequest(
        brief=brief,
        style=PlanStyle(name=DEFAULT_STYLE, prose=prose),
        style_note=job.record.style_line,
        transcript=transcript,
        references=[
            PlanReference(
                id=r.id,
                kind="image" if r.kind == "image" else "clip_frame",
                caption=r.caption,
                width=r.width,
                height=r.height,
            )
            for r in refs
        ],
        constraints=Constraints(
            max_duration_s=MAX_DURATION_S,
            target_duration_s=min(MAX_DURATION_S, transcript.duration_s),
        ),
        asset_policy="any",
    )


def _plan(job: Job, planner: Planner) -> None:
    request = build_plan_request(job)
    picture = planner.plan_picture(request)
    story = planner.plan_sound(request, picture)
    pages = captions.page(
        request.transcript.words,
        picture.keywords,
        EXPLAINER_PAGER,
        duration_s=request.transcript.duration_s,
    )
    work = job.work_dir
    (work / "plan.json").write_text(picture.model_dump_json(indent=2), encoding="utf-8")
    (work / "sound.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    (work / "captions.json").write_text(
        TypeAdapter(list[captions.CaptionPage]).dump_json(pages, indent=2).decode("utf-8"),
        encoding="utf-8",
    )


class Worker:
    """One thread, one job at a time, submission order, `max_queue` deep."""

    def __init__(
        self,
        *,
        transcriber: Transcriber,
        planner: Planner,
        max_queue: int = DEFAULT_MAX_QUEUE,
        max_job_minutes: float | None = DEFAULT_MAX_JOB_MINUTES,
        clock: Clock = _utc_now,
        watchdog_interval_s: float = 1.0,
    ) -> None:
        self._transcriber = transcriber
        self._planner = planner
        self._max_queue = max_queue
        self._max_job_minutes = max_job_minutes
        self._clock = clock
        self._watchdog_interval_s = watchdog_interval_s
        self._queue: queue.Queue[Path | None] = queue.Queue()
        self._waiting: list[Path] = []
        self._running: Path | None = None
        self._reserved = 0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # -- admission (11.2) --

    def _depth_locked(self) -> int:
        return len(self._waiting) + (1 if self._running is not None else 0) + self._reserved

    def depth(self) -> int:
        """Running + waiting + reserved slots."""
        with self._lock:
            return self._depth_locked()

    def reserve(self) -> None:
        """Hold a slot before the upload is read; `release` it or `submit(reserved=True)`."""
        with self._lock:
            if self._depth_locked() >= self._max_queue:
                raise QueueFull(self._max_queue)
            self._reserved += 1

    def release(self) -> None:
        with self._lock:
            self._reserved = max(0, self._reserved - 1)

    def submit(self, job_dir: Path, *, reserved: bool = False) -> None:
        with self._lock:
            if reserved:
                self._reserved = max(0, self._reserved - 1)
            elif self._depth_locked() >= self._max_queue:
                raise QueueFull(self._max_queue)
            self._waiting.append(job_dir)
        self._queue.put(job_dir)

    def pending(self) -> list[Path]:
        """The running job (if any) followed by the waiting ones, in submission order."""
        with self._lock:
            running = [self._running] if self._running is not None else []
            return running + list(self._waiting)

    def position(self, job_dir: Path) -> int | None:
        """1-based place among the waiting jobs; None when running or not queued."""
        with self._lock:
            if job_dir in self._waiting:
                return self._waiting.index(job_dir) + 1
            return None

    # -- running --

    def run_next(self, *, timeout_s: float = 0.0) -> bool:
        """Run the next queued job synchronously; False when the queue is empty."""
        try:
            item = self._queue.get(timeout=timeout_s) if timeout_s else self._queue.get_nowait()
        except queue.Empty:
            return False
        if item is None:
            return False
        self._run(item)
        return True

    def _run(self, job_dir: Path) -> None:
        with self._lock:
            if job_dir in self._waiting:
                self._waiting.remove(job_dir)
            self._running = job_dir
        try:
            self._run_unguarded(job_dir)
        finally:
            with self._lock:
                self._running = None

    def _run_unguarded(self, job_dir: Path) -> None:
        if not (job_dir / "job.json").is_file():
            log.warning("job %s vanished before it ran", job_dir.name)
            return
        job = jobs.load(job_dir)
        try:
            run_job(
                job,
                transcriber=self._transcriber,
                planner=self._planner,
                max_job_minutes=self._max_job_minutes,
                clock=self._clock,
                watchdog_interval_s=self._watchdog_interval_s,
            )
        except NotRunnable as exc:
            log.warning("%s", exc)
        except Exception:  # noqa: BLE001 - the worker thread must never die
            log.exception("job %s crashed outside a step", job.id)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="shortsmith-worker", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            self._run(item)

    def stop(self, *, timeout_s: float = 30.0) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout=timeout_s)
        self._thread = None
