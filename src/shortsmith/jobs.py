"""Job directory and status machine.

Layout per decision 2.2: `<data_dir>/jobs/<job_id>/{job.json, input/, work/, out/}`.
`job.json` is the only index; there is no database. Statuses per 11.1:

    uploaded -> transcribing -> planning -> sourcing -> rendering -> qa -> delivered
    delivered -> passed | rejected
    any non-terminal -> failed, carrying error {step, message, detail}
    failed -> uploaded, by `requeue` only (043: the retry), carrying `retry_from`

Every transition rewrites `job.json` and appends one timestamped line to `job.log`.
Illegal transitions raise `IllegalTransition` and touch nothing on disk. A requeued
job may jump from `uploaded` straight to its `retry_from` step and to no other, so
the pipeline re-enters where it failed without any other job being able to skip one.

The verdict (10.4, ticket 034): `delivered`, `passed` and `rejected` are the three
settled statuses a short can sit in, and they move among themselves by `settle` alone,
never by `transition` (which still treats `passed` and `rejected` as terminal for the
pipeline). What moves a job between them is the phone rating (`rate`, on
`job.json.rating`) judged with the critic's summary (`job.json.critic`, written by the
critic step) under the calibration's rule in `qa.calibration`; a `delivered` job is
always downloadable, `rejected` or not. The YouTube performance fields
(`set_performance`, 14.1(a)) are bookkeeping on the same record and change no status.

`job.json` has more than one writer inside a step (the ledger appends cost rows, the
renderer reports progress) while the worker holds its own `Job` value, so every write
goes through `amend`: it re-reads the file, applies the change and writes the result.
A field another writer added between two of the worker's writes therefore survives.
There is one worker thread, so read-apply-write needs no lock.
"""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

# 034 / 035: the ledger row, the phone rating, the critic summary and the audience are
# defined in `contracts` so `Meta` can carry them; they keep their old names here
# (`jobs.CostRow`, `jobs.Rating`, ...), as do the slider's bounds.
from shortsmith.contracts import RATING_MAX as RATING_MAX
from shortsmith.contracts import RATING_MIN as RATING_MIN
from shortsmith.contracts import (
    CostRow,
    CriticSummary,
    Performance,
    PresenterMeasurement,
    Rating,
    ViewsSource,
)

IST = timezone(timedelta(hours=5, minutes=30))  # fixed offset: no tzdata needed on Windows

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
# The five statuses that are a step the worker runs, and the only ones a retry (043)
# may re-enter at.
STEPS: tuple[Status, ...] = STATUS_ORDER[1:-1]
TERMINAL: frozenset[Status] = frozenset({"passed", "rejected", "failed"})
# The statuses that have stopped moving: the terminal ones and `delivered`, which only
# changes again by a rating (034). The page's elapsed clock stops here, and the sweeper
# (042) touches nothing outside this set: a queued or running job keeps every file.
SETTLED: frozenset[Status] = TERMINAL | frozenset[Status]({"delivered"})
# 10.4: the three statuses a finished short sits in; `settle` moves among them.
VERDICTS: frozenset[Status] = frozenset({"delivered", "passed", "rejected"})
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
    """The 11.1 failure payload. `message` is user-facing; `detail` stays in job.json/log.
    `violations` is the grammar's list when the planner was rejected twice (8.2): the
    page renders it, one line per beat id and rule."""

    model_config = ConfigDict(extra="forbid")

    step: str
    message: str
    detail: str = ""
    violations: list[str] = []


class InputSummary(BaseModel):
    """What was uploaded (decision 2.2: job.json records the inputs)."""

    model_config = ConfigDict(extra="forbid")

    file: str  # raw.mp4 or raw.mov, relative to input/
    original_name: str
    duration_s: float
    width: int
    height: int
    size_bytes: int
    references: int = 0


class JobRecord(BaseModel):
    """Contents of job.json."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Status
    created_at: datetime
    updated_at: datetime
    # Decisions 1.1 / 1.4 / 2.2: the resolved spec name, the full style line as the
    # planner's note, and the draft-redirect notice ("" when none).
    style: str = "explainer"
    style_note: str = ""
    style_notice: str = ""
    input: InputSummary | None = None
    warnings: list[str] = []
    error: JobError | None = None
    cost: list[CostRow] = []
    over_soft_cap: bool = False  # 11.3: a flag for the page and the sheet, nothing more
    progress: int | None = None  # percentage during `rendering` (11.1); cleared on transition
    prompt_version: str | None = None  # 8.3: the planner prompt the job's plans came from
    # 035 / 1.2: the version of the style spec's front matter the plan was judged by,
    # recorded at `planning` beside the prompt version; `meta.json` copies both.
    style_version: str | None = None
    # 013 / 3.3: the face box, the PIP window and the circle diameter, measured once at
    # `transcribing`; the render reads the geometry from here and a retry never re-measures.
    presenter: PresenterMeasurement | None = None
    swept_at: datetime | None = None  # 2.2: when input/ and work/ were deleted (042)
    # 043: the step this run re-enters at, set by `requeue`. It is what makes the one
    # forward jump out of `uploaded` legal, and it stays on the record afterwards as
    # the note that this run was a retry.
    retry_from: Status | None = None
    # 034: the phone rating (10.3), the critic's summary (10.2) and the published
    # short's audience (14.1(a)); `meta.json` (035) copies all three.
    rating: Rating | None = None
    critic: CriticSummary | None = None
    performance: Performance | None = None

    @model_validator(mode="before")
    @classmethod
    def _legacy_style_line(cls, data: object) -> object:
        """Before ticket 008 job.json held the raw line as `style_line`; it is the
        note now, so an older data directory keeps loading."""
        raw: object = data
        if isinstance(raw, dict) and "style_line" in raw:
            fields: dict[str, Any] = dict(raw)  # pyright: ignore[reportUnknownArgumentType]
            fields.setdefault("style_note", fields.pop("style_line"))
            return fields
        return data


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


def create(
    data_dir: Path,
    *,
    style: str = "explainer",
    style_note: str = "",
    style_notice: str = "",
    input: InputSummary | None = None,
    warnings: list[str] | None = None,
    now: Clock = _utc_now,
) -> Job:
    stamp = now()
    job_id = new_job_id(stamp)
    path = data_dir / "jobs" / job_id
    if path.exists():  # same second and a 24-bit collision; try once more
        job_id = new_job_id(stamp)
        path = data_dir / "jobs" / job_id
    for sub in ("input", "work", "out"):
        (path / sub).mkdir(parents=True, exist_ok=False)
    record = JobRecord(
        id=job_id,
        status="uploaded",
        created_at=stamp,
        updated_at=stamp,
        style=style,
        style_note=style_note,
        style_notice=style_notice,
        input=input,
        warnings=list(warnings or []),
    )
    job = Job(path=path, record=record)
    _write_json(job)
    _append_log(job, stamp, "created uploaded")
    return job


def load(job_dir: Path) -> Job:
    record = JobRecord.model_validate_json(_read_json(job_dir / "job.json"))
    return Job(path=job_dir, record=record)


JOB_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def find(data_dir: Path, job_id: str) -> Job | None:
    """Load a job by id; None for an unknown or malformed id (never a path lookup)."""
    if not JOB_ID.match(job_id):
        return None
    job_dir = data_dir / "jobs" / job_id
    if not (job_dir / "job.json").is_file():
        return None
    return load(job_dir)


def iter_jobs(data_dir: Path) -> Iterator[Job]:
    """Every job on disk, newest first (the ids sort by submission time). A directory
    mid-write - no job.json yet, one that does not parse, or one the sweeper took
    between the listing and the read - is skipped: one job never breaks a listing."""
    root = data_dir / "jobs"
    if not root.is_dir():
        return
    for d in sorted((d for d in root.iterdir() if JOB_ID.match(d.name)), reverse=True):
        try:
            yield load(d)
        except (OSError, ValidationError):
            continue


def list_recent(data_dir: Path, n: int = 50, *, since: datetime | None = None) -> list[Job]:
    """The `n` most recent jobs by `created_at`, newest first (11.1: the job list).
    The directory name only resolves to the second, so job.json decides the order.
    With `since`, jobs created before it are left out before the cut to `n`."""
    found = [j for j in iter_jobs(data_dir) if since is None or j.record.created_at >= since]
    return sorted(found, key=lambda j: j.record.created_at, reverse=True)[:n]


def created_since(data_dir: Path, since: datetime) -> int:
    """How many jobs were created at or after `since` (11.2: the per-day limit)."""
    return sum(1 for job in iter_jobs(data_dir) if job.record.created_at >= since)


def can_transition(
    current: Status, requested: Status, *, retry_from: Status | None = None
) -> bool:
    """The 11.1 machine: one step forward, or `failed` from anywhere in flight. The one
    exception is a retry (043): a job `requeue` sent back to `uploaded` carries the step
    it failed at, and may jump straight to that step and to no other, so a job that was
    never requeued still cannot skip one."""
    if current in TERMINAL or requested == current:
        return False
    if current == "uploaded" and retry_from is not None and requested == retry_from:
        return requested in STEPS
    if requested == "failed":
        return True
    if current == "delivered":
        return requested in ("passed", "rejected")
    if current in STATUS_ORDER and requested in STATUS_ORDER:
        return STATUS_ORDER.index(requested) == STATUS_ORDER.index(current) + 1
    return False


def amend(job: Job, **fields: Any) -> Job:
    """Rewrite job.json with `fields` applied to what is on disk now (see the module
    note), and return the fresh Job. `updated_at` is the caller's to set."""
    current = load(job.path).record
    updated = Job(path=job.path, record=current.model_copy(update=fields))
    _write_json(updated)
    return updated


def transition(
    job: Job, status: Status, *, error: JobError | None = None, now: Clock = _utc_now
) -> Job:
    if status not in ALL_STATUSES or not can_transition(
        job.status, status, retry_from=job.record.retry_from
    ):
        raise IllegalTransition(job.id, job.status, status)
    if status == "failed" and error is None:
        raise ValueError("transition to 'failed' needs a JobError")
    if status != "failed" and error is not None:
        raise ValueError(f"an error payload is only allowed on 'failed', not {status!r}")
    stamp = now()
    updated = amend(job, status=status, updated_at=stamp, error=error, progress=None)
    line = f"{job.status} -> {status}"
    if error is not None:
        line += f" step={error.step} message={error.message!r}"
    _append_log(updated, stamp, line)
    return updated


def set_progress(job: Job, percent: int, *, now: Clock = _utc_now) -> Job:
    """Record step progress in job.json (no log line: it changes every few frames)."""
    return amend(job, progress=max(0, min(100, percent)), updated_at=now())


def midnight_ist(now: datetime) -> datetime:
    """The most recent midnight in IST at or before `now` (11.2 jobs per day, 11.3 the
    daily cash guard)."""
    local = now.astimezone(IST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def fail(
    job: Job,
    *,
    step: str,
    message: str,
    detail: str = "",
    violations: Sequence[str] = (),
    now: Clock = _utc_now,
) -> Job:
    error = JobError(step=step, message=message, detail=detail, violations=list(violations))
    return transition(job, "failed", error=error, now=now)


def requeue(job: Job, *, now: Clock = _utc_now) -> Job:
    """Send a failed job back to `uploaded` to be run again from the step it failed at
    (043). This is the only way out of a terminal status, so it is written here rather
    than opened up in `can_transition`: `transition` can never resurrect a failed job.

    The error leaves job.json - the job is waiting again, and the page should say so -
    but job.log keeps it, so a job that fails twice at the same step keeps both. An
    error naming something that is not a step (there is none today) re-runs from the
    first step rather than refusing the retry."""
    if job.status != "failed":
        raise IllegalTransition(job.id, job.status, "uploaded")
    step = job.record.error.step if job.record.error is not None else ""
    start: Status = step if step in STEPS else STEPS[0]  # type: ignore[assignment]
    stamp = now()
    updated = amend(
        job, status="uploaded", updated_at=stamp, error=None, progress=None, retry_from=start
    )
    _append_log(updated, stamp, f"failed -> uploaded retry_from={start}")
    return updated


def note(job: Job, line: str, *, now: Clock = _utc_now) -> None:
    """Append a line to job.log without touching job.json (a retry inside a step)."""
    _append_log(job, now(), line)


def data_dir_of(job: Job) -> Path:
    """The data directory the job was created under (`<data_dir>/jobs/<id>`, 2.2):
    where `calibration.json` and the other cross-job files live."""
    return job.path.parent.parent


def _settled_or_raise(job: Job, requested: str) -> None:
    if job.status not in VERDICTS:
        raise IllegalTransition(job.id, job.status, requested)


def rate(job: Job, score: int, note: str, *, now: Clock = _utc_now) -> Job:
    """Store the phone rating on job.json (10.3) and log it. Only a job with a short
    (`delivered`, `passed`, `rejected`) can be rated; a score off the 1-10 scale is a
    `ValueError`. The status is not touched here: the verdict is `qa.calibration`'s,
    which reads this rating and the critic's summary together."""
    _settled_or_raise(job, "rating")
    stamp = now()
    rating = Rating(score=score, note=note.strip(), rated_at=stamp)  # ValidationError
    updated = amend(job, rating=rating, updated_at=stamp)
    line = f"rated {rating.score}/10" + (f": {rating.note}" if rating.note else "")
    _append_log(updated, stamp, line)
    return updated


def set_performance(
    job: Job,
    *,
    published_url: str = "",
    views: int | None = None,
    retention_pct: float | None = None,
    views_source: ViewsSource = "manual",
    note: str = "",
    now: Clock = _utc_now,
) -> Job:
    """Store the published URL, views and retention on job.json (14.1(a)) and log
    them; a job without a short has nothing published. No status changes."""
    _settled_or_raise(job, "performance")
    stamp = now()
    performance = Performance(
        published_url=published_url.strip(),
        views=views,
        retention_pct=retention_pct,
        views_source=views_source,
        note=note.strip(),
        updated_at=stamp,
    )
    updated = amend(job, performance=performance, updated_at=stamp)
    parts = [f"performance: {performance.published_url or '(no url)'}"]
    if performance.views is not None:
        parts.append(f"views {performance.views} ({performance.views_source})")
    if performance.retention_pct is not None:
        parts.append(f"retention {performance.retention_pct:g}%")
    if performance.note:
        parts.append(performance.note)
    _append_log(updated, stamp, " ".join(parts))
    return updated


def settle(job: Job, status: Status, reason: str, *, now: Clock = _utc_now) -> Job:
    """Move a finished short among `delivered`, `passed` and `rejected` (10.4), logging
    `<from> -> <to> by <reason>`. This is the only way between them, since the verdict
    follows the rating and a re-rating may reverse it; `transition` never reopens
    `passed` or `rejected`. The same status again writes nothing."""
    _settled_or_raise(job, status)
    if status not in VERDICTS:
        raise IllegalTransition(job.id, job.status, status)
    current = load(job.path)
    if current.status == status:
        return current
    stamp = now()
    updated = amend(job, status=status, updated_at=stamp)
    _append_log(updated, stamp, f"{current.status} -> {status} by {reason}")
    return updated


REPLACE_ATTEMPTS = 100
REPLACE_RETRY_S = 0.01


def _read_json(path: Path) -> str:
    """Read job.json. On Windows an open that lands inside the writer's replace fails
    with PermissionError for a moment (the mirror of `_write_json`'s case), so the read
    retries the same way before giving up."""
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_RETRY_S)
    raise AssertionError("unreachable")


def _write_json(job: Job) -> None:
    """Atomic rewrite of job.json. On Windows the replace fails with PermissionError
    while another handle (the job page poll, a test) has the file open for reading, so
    it is retried for up to about a second before giving up."""
    tmp = job.json_path.with_suffix(".json.tmp")
    tmp.write_text(job.record.model_dump_json(indent=2), encoding="utf-8")
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            tmp.replace(job.json_path)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_RETRY_S)


def _append_log(job: Job, stamp: datetime, line: str) -> None:
    with job.log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp.isoformat()} {line}\n")
