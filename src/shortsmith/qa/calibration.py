"""The critic-versus-phone calibration (decisions 10.2, 10.3, 10.4; ticket 034).

The critic is ADVISORY until it has matched the phone verdict on at least four of the
last five rated shorts; from then on it is BLOCKING, and that moment is when the
system counts as automated (10.2). "Matched" is pass/fail at the same line: the critic
passes a short at `overall >= 7`, the phone at `rating >= 6`.

`data/calibration.json` (`<data_dir>/calibration.json`) holds one entry per rated job,
in rating order; `record(job)` appends the job (or replaces its entry when it is rated
again, so a second look never counts twice) from the rating and the critic summary on
`job.json`. `mode(data_dir)` reads the streak, `agreed_line` is the page's "critic
agreed N of last 5".

The verdict (10.4) is `verdict(critic, rating)`:

    advisory   unrated -> `delivered`; rating >= 6 -> `passed`; rating < 6 -> `rejected`
    blocking   critic >= 7 and (unrated or rating >= 6) -> `passed`; either failing ->
               `rejected`; so a blocking critic settles an unrated job at delivery

A critic that could not answer (`unavailable`) has no verdict to block with, so under
either mode the rating alone decides, and the job stays `delivered` until it is rated:
an API outage never rejects a short. Which rule a job is judged by is the mode the
critic ran under, recorded on its summary (`advisory`), not the mode at rating time:
the page showed that badge, and the calibration compared that report.

`apply(job)` reads the summary and the rating from `job.json`, computes the verdict and
`jobs.settle`s the job. The pipeline calls it once at `delivered`; the rating route
calls it after every rating. A `delivered` job stays downloadable whatever the verdict.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from shortsmith import jobs
from shortsmith.jobs import CriticSummary, Job, Rating, Status

FILE = "calibration.json"
WINDOW = 5  # 10.2: "4 of 5 consecutive shorts"
AGREE_MIN = 4
CRITIC_PASS = 7  # 10.2: the critic's pass line once blocking
PHONE_PASS = 6  # 10.2 / 14.1: the phone's pass line
NO_RATED_JOBS = "no rated jobs yet"

Mode = Literal["advisory", "blocking"]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Entry(BaseModel):
    """One rated job: what the critic said, what the phone said, whether they agreed."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    critic_overall: int | None  # None: the critic could not answer
    critic_pass: bool
    rating: int
    phone_pass: bool
    matched: bool
    at: datetime


class Calibration(BaseModel):
    """`calibration.json`: the entries in rating order."""

    model_config = ConfigDict(extra="forbid")

    entries: list[Entry] = []


def path(data_dir: Path) -> Path:
    return data_dir / FILE


def load(data_dir: Path) -> Calibration:
    """The file, or an empty calibration when there is none yet."""
    file = path(data_dir)
    if not file.is_file():
        return Calibration()
    return Calibration.model_validate_json(file.read_text(encoding="utf-8"))


def save(data_dir: Path, calibration: Calibration) -> Path:
    file = path(data_dir)
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".json.tmp")
    tmp.write_text(calibration.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(file)
    return file


# --- the streak (10.2) ----------------------------------------------------------------------


def window(calibration: Calibration) -> list[Entry]:
    return calibration.entries[-WINDOW:]


def agreed(calibration: Calibration) -> tuple[int, int]:
    """(matches, entries) over the last five rated jobs."""
    last = window(calibration)
    return sum(1 for e in last if e.matched), len(last)


def mode_of(calibration: Calibration) -> Mode:
    """`blocking` once the last five rated jobs carry at least four matches (10.2);
    fewer than five rated jobs need the same four, so four of four flips it too."""
    matches, _ = agreed(calibration)
    return "blocking" if matches >= AGREE_MIN else "advisory"


def mode(data_dir: Path) -> Mode:
    return mode_of(load(data_dir))


def agreed_line(calibration: Calibration) -> str:
    """The page's line (10.3): "critic agreed N of last 5"."""
    matches, count = agreed(calibration)
    if count == 0:
        return NO_RATED_JOBS
    return f"critic agreed {matches} of last {count}"


# --- record (10.3) --------------------------------------------------------------------------


def critic_passes(summary: CriticSummary | None) -> bool | None:
    """True or False for a scored critic against its pass line; None when there is no
    verdict to compare (no critic ran, or it could not answer)."""
    if summary is None or summary.status != "scored" or summary.overall is None:
        return None
    return summary.overall >= CRITIC_PASS


def phone_passes(rating: Rating) -> bool:
    return rating.score >= PHONE_PASS


def entry_for(job: Job, *, now: Clock = _utc_now) -> Entry:
    """The job's entry from job.json: a job without a rating has nothing to compare."""
    record = jobs.load(job.path).record
    if record.rating is None:
        raise ValueError(f"job {job.id} has no rating to calibrate on")
    critic = critic_passes(record.critic)
    phone = phone_passes(record.rating)
    return Entry(
        job_id=job.id,
        critic_overall=record.critic.overall if record.critic is not None else None,
        critic_pass=bool(critic),
        rating=record.rating.score,
        phone_pass=phone,
        # An unavailable critic never matches: it did not rate the short at all.
        matched=critic is not None and critic == phone,
        at=now(),
    )


def record(job: Job, *, now: Clock = _utc_now) -> Calibration:
    """Append the rated job to `calibration.json` under its data directory, replacing
    its earlier entry in place when it was rated before, and return the file's state."""
    entry = entry_for(job, now=now)
    data_dir = jobs.data_dir_of(job)
    calibration = load(data_dir)
    entries = calibration.entries
    for i, existing in enumerate(entries):
        if existing.job_id == entry.job_id:
            entries[i] = entry
            break
    else:
        entries.append(entry)
    save(data_dir, calibration)
    return calibration


# --- the verdict (10.4) ---------------------------------------------------------------------


def verdict(summary: CriticSummary | None, rating: Rating | None) -> Status:
    """The status a finished short belongs in, by the module note's table."""
    critic = critic_passes(summary)
    blocking = summary is not None and not summary.advisory and critic is not None
    if not blocking:
        if rating is None:
            return "delivered"
        return "passed" if phone_passes(rating) else "rejected"
    phone = rating is None or phone_passes(rating)
    return "passed" if critic and phone else "rejected"


def reason(summary: CriticSummary | None, rating: Rating | None) -> str:
    parts: list[str] = []
    if rating is not None:
        parts.append(f"rating {rating.score}/10")
    if summary is not None and summary.status == "scored" and summary.overall is not None:
        mode_word = "advisory" if summary.advisory else "blocking"
        parts.append(f"critic {summary.overall}/10 {mode_word}")
    return ", ".join(parts) or "no rating and no critic"


def apply(job: Job, *, now: Clock = _utc_now) -> Job:
    """Settle the job by its own summary and rating (`jobs.settle`); the job must
    already be `delivered`, `passed` or `rejected`."""
    record = jobs.load(job.path).record
    status = verdict(record.critic, record.rating)
    return jobs.settle(job, status, reason(record.critic, record.rating), now=now)
