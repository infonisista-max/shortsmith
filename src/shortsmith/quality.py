"""112: strict mode. A crash or a missing thing fails the job loudly instead of
delivering a downgraded reel; `forgiving` keeps every net exactly as on 9e28146.

The mode belongs to each job: `jobs.create` stamps `job.json.quality_mode` from
`QUALITY_MODE` (default `strict`); a job made before 112 has no stamp and reads the
current setting (`mode_of`).

Every gated site calls `downgrade` (one finding) or `downgrade_all` (a pass that walks
many beats records every finding and stops once): in strict mode it raises
`QualityStop` with the findings, in forgiving mode it runs `apply` - today's repair,
which records its own decision as before - and returns its result. No site has its own
`if strict`. The pipeline never rescues a `QualityStop`: the job ends `failed` at the
step it was in, the findings on `job.json.error.findings` for the page and one
`strict stop:` job.log line each.

Every finding, in both modes, is one row of `data/quality-log.tsv` (`log`): UTC date,
job id, beat, beat kind, outcome (`stop` | `repair` | `settled`) and cause. The file is
only ever appended to; the operator sorts it to see what breaks most often.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NoReturn

from shortsmith import config, jobs
from shortsmith.jobs import Clock, Job, QualityFinding

__all__ = [
    "LOG_COLUMNS",
    "LOG_NAME",
    "Finding",
    "QualityStop",
    "downgrade",
    "downgrade_all",
    "log",
    "log_path",
    "mode_of",
    "setting",
    "stop",
]

Finding = QualityFinding
Outcome = Literal["stop", "repair", "settled"]

LOG_NAME = "quality-log.tsv"
LOG_COLUMNS = ("date_utc", "job", "beat", "beat_kind", "outcome", "cause")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class QualityStop(Exception):
    """Strict mode stopped the job; `findings` lists every problem the pass found."""

    def __init__(self, findings: Sequence[QualityFinding], *, headline: str = "") -> None:
        self.findings = list(findings)
        # 112b: the stop's own sentence for the page (the pre-render gate's count);
        # empty, the page says how many problems the step found.
        self.headline = headline
        super().__init__("; ".join(f.line() for f in self.findings) or "strict stop")


def setting() -> config.QualityMode:
    """`QUALITY_MODE` as configured now (the environment, then `.env`)."""
    return config.load().quality_mode


def mode_of(job: Job) -> config.QualityMode:
    """The job's stamped mode; a job with no stamp (made before 112) reads the setting."""
    return job.record.quality_mode or setting()


def log_path(job: Job) -> Path:
    return jobs.data_dir_of(job) / LOG_NAME


def _cell(text: str) -> str:
    return " ".join(text.split())


def log(job: Job, outcome: Outcome, finding: QualityFinding, *, now: Clock = _utc_now) -> None:
    """Append one row to `data/quality-log.tsv` (the header first when the file is new)."""
    path = log_path(job)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file()
    row = (now().strftime("%Y-%m-%dT%H:%M:%SZ"), job.id, finding.beat or "-",
           finding.kind or "-", outcome, finding.cause)  # fmt: skip
    with path.open("a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("\t".join(LOG_COLUMNS) + "\n")
        f.write("\t".join(_cell(c) for c in row) + "\n")


def stop(job: Job, findings: Sequence[QualityFinding], *, headline: str = "",
         now: Clock = _utc_now) -> NoReturn:  # fmt: skip
    """Log every finding as `stop` and raise one `QualityStop` carrying them all."""
    for finding in findings:
        log(job, "stop", finding, now=now)
    raise QualityStop(findings, headline=headline)


def downgrade_all[T](
    job: Job, findings: Sequence[QualityFinding], apply: Callable[[], T], *,
    now: Clock = _utc_now,
) -> T:  # fmt: skip
    """Strict: `stop`. Forgiving: run `apply` (today's repair), log each finding as
    `repair`, and return what `apply` returned. No findings: `apply` in either mode."""
    if findings and mode_of(job) == "strict":
        stop(job, findings, now=now)
    result = apply()
    for finding in findings:
        log(job, "repair", finding, now=now)
    return result


def downgrade[T](
    job: Job, beat: str | None, cause: str, detail: str, apply: Callable[[], T], *,
    kind: str = "", now: Clock = _utc_now,
) -> T:  # fmt: skip
    """One finding's `downgrade_all`: `beat` (None for a step or a check), the `cause`
    in plain words and the technical `detail`."""
    finding = QualityFinding(beat=beat, kind=kind, cause=cause, detail=detail)
    return downgrade_all(job, [finding], apply, now=now)
