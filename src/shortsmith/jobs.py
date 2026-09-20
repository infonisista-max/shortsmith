"""Job directory and status machine.

Layout per decision 2.2: `<data_dir>/jobs/<job_id>/{job.json, input/, work/, out/}`.
`job.json` is the only index; there is no database. Statuses per 11.1:

    uploaded -> transcribing -> planning -> sourcing -> rendering -> qa -> delivered
    delivered -> passed | rejected
    any non-terminal -> failed, carrying error {step, message, detail}

Every transition rewrites `job.json` and appends one timestamped line to `job.log`.
Illegal transitions raise `IllegalTransition` and touch nothing on disk.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict

Status = Literal[
    "uploaded",
    "transcribing",
    "planning",
    "sourcing",
    "rendering",
    "qa",
    "delivered",
    "passed",
    "rejected",
    "failed",
]

STATUS_ORDER: tuple[Status, ...] = (
    "uploaded",
    "transcribing",
    "planning",
    "sourcing",
    "rendering",
    "qa",
    "delivered",
)
TERMINAL: frozenset[Status] = frozenset({"passed", "rejected", "failed"})
ALL_STATUSES: frozenset[Status] = frozenset(get_args(Status))

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class IllegalTransition(Exception):
    def __init__(self, job_id: str, current: str, requested: str) -> None:
        super().__init__(f"job {job_id}: cannot go from {current!r} to {requested!r}")
        self.current = current
        self.requested = requested


class JobError(BaseModel):
    """The 11.1 failure payload. `message` is user-facing; `detail` stays in job.json/log."""

    model_config = ConfigDict(extra="forbid")

    step: str
    message: str
    detail: str = ""


class JobRecord(BaseModel):
    """Contents of job.json."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Status
    created_at: datetime
    updated_at: datetime
    style_line: str = ""
    error: JobError | None = None
    cost: list[dict[str, Any]] = []


@dataclass(frozen=True)
class Job:
    path: Path
    record: JobRecord

    @property
    def id(self) -> str:
        return self.record.id

    @property
    def status(self) -> Status:
        return self.record.status

    @property
    def json_path(self) -> Path:
        return self.path / "job.json"

    @property
    def log_path(self) -> Path:
        return self.path / "job.log"

    @property
    def input_dir(self) -> Path:
        return self.path / "input"

    @property
    def work_dir(self) -> Path:
        return self.path / "work"

    @property
    def out_dir(self) -> Path:
        return self.path / "out"


def new_job_id(now: datetime) -> str:
    """Time-prefixed so a directory listing sorts in submission order (11.1 queue)."""
    return f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"


def create(data_dir: Path, *, style_line: str = "", now: Clock = _utc_now) -> Job:
    stamp = now()
    job_id = new_job_id(stamp)
    path = data_dir / "jobs" / job_id
    if path.exists():  # same second and a 24-bit collision; try once more
        job_id = new_job_id(stamp)
        path = data_dir / "jobs" / job_id
    for sub in ("input", "work", "out"):
        (path / sub).mkdir(parents=True, exist_ok=False)
    record = JobRecord(
        id=job_id, status="uploaded", created_at=stamp, updated_at=stamp, style_line=style_line
    )
    job = Job(path=path, record=record)
    _write_json(job)
    _append_log(job, stamp, "created uploaded")
    return job


def load(job_dir: Path) -> Job:
    record = JobRecord.model_validate_json((job_dir / "job.json").read_text(encoding="utf-8"))
    return Job(path=job_dir, record=record)


def can_transition(current: Status, requested: Status) -> bool:
    if current in TERMINAL or requested == current:
        return False
    if requested == "failed":
        return True
    if current == "delivered":
        return requested in ("passed", "rejected")
    if current in STATUS_ORDER and requested in STATUS_ORDER:
        return STATUS_ORDER.index(requested) == STATUS_ORDER.index(current) + 1
    return False


def transition(
    job: Job, status: Status, *, error: JobError | None = None, now: Clock = _utc_now
) -> Job:
    if status not in ALL_STATUSES or not can_transition(job.status, status):
        raise IllegalTransition(job.id, job.status, status)
    if status == "failed" and error is None:
        raise ValueError("transition to 'failed' needs a JobError")
    if status != "failed" and error is not None:
        raise ValueError(f"an error payload is only allowed on 'failed', not {status!r}")
    stamp = now()
    record = job.record.model_copy(update={"status": status, "updated_at": stamp, "error": error})
    updated = Job(path=job.path, record=record)
    _write_json(updated)
    line = f"{job.status} -> {status}"
    if error is not None:
        line += f" step={error.step} message={error.message!r}"
    _append_log(updated, stamp, line)
    return updated


def fail(job: Job, *, step: str, message: str, detail: str = "", now: Clock = _utc_now) -> Job:
    return transition(
        job, "failed", error=JobError(step=step, message=message, detail=detail), now=now
    )


def _write_json(job: Job) -> None:
    tmp = job.json_path.with_suffix(".json.tmp")
    tmp.write_text(job.record.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(job.json_path)


def _append_log(job: Job, stamp: datetime, line: str) -> None:
    with job.log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp.isoformat()} {line}\n")
