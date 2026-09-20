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
without threads. Queue depth, job-minute kill and restart recovery are ticket 041.
"""

from __future__ import annotations

import logging
import queue
import threading
import traceback
from collections.abc import Callable
from pathlib import Path

from pydantic import TypeAdapter

from shortsmith import captions, jobs
from shortsmith.captions import PagerNumbers
from shortsmith.contracts import (
    Constraints,
    PlanReference,
    PlanRequest,
    PlanStyle,
    ReferenceRecord,
    Transcript,
)
from shortsmith.jobs import Job, Status
from shortsmith.planner import Planner
from shortsmith.transcriber import Transcriber

log = logging.getLogger(__name__)

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


Step = Callable[[Job], None]


def run_job(job: Job, *, transcriber: Transcriber, planner: Planner) -> Job:
    if job.status != "uploaded":
        raise NotRunnable(f"job {job.id} is {job.status!r}, not 'uploaded'")
    steps: list[tuple[Status, Step]] = [
        ("transcribing", lambda j: _transcribe(j, transcriber)),
        ("planning", lambda j: _plan(j, planner)),
    ]
    for status, step in steps:
        job = jobs.transition(job, status)
        try:
            step(job)
        except Exception as exc:  # noqa: BLE001 - every step failure lands in job.json the same way
            detail = f"{exc}\n{traceback.format_exc()}"
            return jobs.fail(job, step=status, message=STEP_MESSAGES[status], detail=detail)
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
    """One thread, one job at a time, submission order."""

    def __init__(self, *, transcriber: Transcriber, planner: Planner) -> None:
        self._transcriber = transcriber
        self._planner = planner
        self._queue: queue.Queue[Path | None] = queue.Queue()
        self._pending: list[Path] = []
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def submit(self, job_dir: Path) -> None:
        with self._lock:
            self._pending.append(job_dir)
        self._queue.put(job_dir)

    def pending(self) -> list[Path]:
        with self._lock:
            return list(self._pending)

    def run_next(self, *, timeout_s: float = 0.0) -> bool:
        """Run the next queued job synchronously; False when the queue is empty."""
        try:
            item = self._queue.get(timeout=timeout_s) if timeout_s else self._queue.get_nowait()
        except queue.Empty:
            return False
        if item is None:
            return False
        try:
            self._run(item)
        finally:
            with self._lock:
                if item in self._pending:
                    self._pending.remove(item)
        return True

    def _run(self, job_dir: Path) -> None:
        if not (job_dir / "job.json").is_file():
            log.warning("job %s vanished before it ran", job_dir.name)
            return
        job = jobs.load(job_dir)
        try:
            run_job(job, transcriber=self._transcriber, planner=self._planner)
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
            try:
                self._run(item)
            finally:
                with self._lock:
                    if item in self._pending:
                        self._pending.remove(item)

    def stop(self, *, timeout_s: float = 30.0) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout=timeout_s)
        self._thread = None
