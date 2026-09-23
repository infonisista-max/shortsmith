"""Retention (PRD `sweeper`; decisions 2.2, 11.2), as pure code with a clock injected.

Two ages, both counted from the moment the job was uploaded (`created_at`):

    > 24 h   `input/` and `work/` go; `out/` stays, so the short, the contact sheet
             and the rights evidence outlive the raw footage (2.2, user story 55).
    > 7 d    the whole job directory goes.

A job that is still in flight is never touched: only a `delivered`, `passed`,
`rejected` or `failed` job has stopped moving (`jobs.SETTLED`), so a queued or
running job cannot have the files of its next step deleted underneath it. The
24 h pass appends one line to `job.log` and records `swept_at` in `job.json`; the
7 d pass takes `job.log` with it, so that deletion is only a logger line and the
returned `Action`.

`sweep` returns what it did (or, with `dry_run`, what it would do and nothing else),
which is what the CLI prints and what the app's background task logs. The same
function is `python -m shortsmith.sweeper [--dry-run]`.

The disk guard (11.2) lives here too: `low_disk` is the 5 GB line the upload form
refuses new jobs below, and the refusal runs `sweep` at once.
"""

from __future__ import annotations

import logging
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from shortsmith import config, jobs
from shortsmith.jobs import SETTLED, Clock, Job

log = logging.getLogger(__name__)

WORKING_AFTER = timedelta(hours=24)  # 2.2: the upload and the working files
JOB_AFTER = timedelta(days=7)  # 2.2: the short and its rights evidence
WORKING_DIRS = ("input", "work")
INTERVAL_S = 15 * 60  # 11.2: the app's background pass
GIB = 1024**3
MIN_FREE_BYTES = 5 * GIB  # 11.2: below this the upload form refuses new jobs

Scope = Literal["working", "job"]
FreeBytes = Callable[[Path], int]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Action:
    """One deletion: which job, how much of it, and the entries that went."""

    job_id: str
    scope: Scope
    deleted: tuple[str, ...]

    def line(self) -> str:
        listed = ", ".join(f"{name}/" for name in self.deleted)
        if self.scope == "job":
            return f"{self.job_id}: deleted the whole job directory ({listed})"
        return f"{self.job_id}: deleted {listed}"


def sweep(
    data_dir: Path, *, now: Clock = _utc_now, dry_run: bool = False
) -> list[Action]:
    """Apply both retention ages to every settled job under `data_dir`."""
    stamp = now()
    actions: list[Action] = []
    for job in jobs.iter_jobs(data_dir):
        action = _plan(job, stamp)
        if action is None:
            continue
        actions.append(action)
        if not dry_run:
            _apply(job, action, stamp)
    return actions


def _plan(job: Job, stamp: datetime) -> Action | None:
    if job.status not in SETTLED:  # still queued or running: never touched
        return None
    age = stamp - job.record.created_at
    if age > JOB_AFTER:
        entries = tuple(sorted(p.name for p in job.path.iterdir()))
        return Action(job_id=job.id, scope="job", deleted=entries)
    if age > WORKING_AFTER:
        present = tuple(name for name in WORKING_DIRS if (job.path / name).is_dir())
        if present:
            return Action(job_id=job.id, scope="working", deleted=present)
    return None


def _apply(job: Job, action: Action, stamp: datetime) -> None:
    if action.scope == "job":
        # job.log goes with the directory, so this deletion is only a logger line.
        shutil.rmtree(job.path, ignore_errors=True)
        log.info("%s", action.line())
        return
    for name in action.deleted:
        shutil.rmtree(job.path / name, ignore_errors=True)
    jobs.amend(job, swept_at=stamp)
    jobs.note(job, f"swept: deleted {', '.join(f'{n}/' for n in action.deleted)}",
              now=lambda: stamp)  # fmt: skip
    log.info("%s", action.line())


# --- the disk guard (11.2) ------------------------------------------------------


def free_bytes(path: Path) -> int:
    """Free bytes on the filesystem holding `path`, or the nearest parent that exists
    (the data directory is made at startup, but the guard must answer before that)."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def low_disk(free: FreeBytes, data_dir: Path) -> bool:
    return free(data_dir) < MIN_FREE_BYTES


# --- the CLI --------------------------------------------------------------------


USAGE = "usage: python -m shortsmith.sweeper [--dry-run]"


def main(
    argv: list[str] | None = None,
    *,
    data_dir: Path | None = None,
    now: Clock = _utc_now,
) -> int:
    args = list(argv or [])
    if args not in ([], ["--dry-run"]):
        print(USAGE, file=sys.stderr)
        return 2
    dry_run = args == ["--dry-run"]
    root = data_dir if data_dir is not None else config.load().shortsmith_data_dir
    actions = sweep(root, now=now, dry_run=dry_run)
    if not actions:
        print("nothing to sweep")
        return 0
    for action in actions:
        print(action.line())
    print(f"{len(actions)} job(s){' (dry run: nothing was deleted)' if dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
