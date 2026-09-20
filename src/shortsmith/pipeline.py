"""The worker (PRD `pipeline`): runs a job's steps in the 11.1 order, one job at a time
in submission order (9.1).

`run_job` is the synchronous path: it takes an `uploaded` job through every step that
exists (today: transcribing) and stops at the first status whose step has no
implementation yet (today: `planning`, ticket 003). Any exception inside a step marks
the job `failed` at that step with the fixed user-facing sentence from `STEP_MESSAGES`
and the exception text as `detail` (11.1).

`Worker` wraps `run_job` in a FIFO queue on one daemon thread for the web app;
`run_next` drains one job synchronously so tests and smoke use the same code path
without threads. Queue depth, job-minute kill and restart recovery are ticket 041.
"""

from __future__ import annotations

import logging
import queue
import threading
import traceback
from pathlib import Path

from shortsmith import jobs
from shortsmith.jobs import Job, Status
from shortsmith.transcriber import Transcriber

log = logging.getLogger(__name__)

STEP_MESSAGES: dict[str, str] = {
    "transcribing": "We could not transcribe the recording.",
    "planning": "We could not plan the short.",
    "sourcing": "We could not find or make the pictures for the short.",
    "rendering": "We could not render the short.",
    "qa": "The short failed a technical check.",
}
LAST_IMPLEMENTED_STEP: Status = "transcribing"


class NotRunnable(Exception):
    """The job is not `uploaded`, so the worker has nothing to start."""


def run_job(job: Job, *, transcriber: Transcriber) -> Job:
    if job.status != "uploaded":
        raise NotRunnable(f"job {job.id} is {job.status!r}, not 'uploaded'")
    job = jobs.transition(job, "transcribing")
    try:
        _transcribe(job, transcriber)
    except Exception as exc:  # noqa: BLE001 - every step failure lands in job.json the same way
        detail = f"{exc}\n{traceback.format_exc()}"
        return jobs.fail(job, step="transcribing", message=STEP_MESSAGES["transcribing"],
                         detail=detail)
    return jobs.transition(job, "planning")


def _transcribe(job: Job, transcriber: Transcriber) -> None:
    assert job.record.input is not None or (job.input_dir / "raw.mp4").is_file()
    raw = job.input_dir / (job.record.input.file if job.record.input else "raw.mp4")
    transcript = transcriber.transcribe(raw)
    (job.work_dir / "asr.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")


class Worker:
    """One thread, one job at a time, submission order."""

    def __init__(self, *, transcriber: Transcriber) -> None:
        self._transcriber = transcriber
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
            run_job(job, transcriber=self._transcriber)
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
