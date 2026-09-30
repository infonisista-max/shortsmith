"""The planner failover (095, operator answer 2): the CLI planner first, the API behind it.

`FailoverPlanner(primary, backup)` runs every call (`plan_picture`, `plan_sound`, `ask`)
on the primary. A `PlannerError` that is not `QuotaSpent` is taken as transient and
the same call is retried once on the primary; after that second failure, or at once
on `QuotaSpent` or `PlannerUnavailable` (no CLI on PATH), the same call goes to the
backup, which gets one retry of a transient `PlannerError` of its own. If the backup
fails too, its last error is raised (chained to the primary's) and the job fails at
`planning` with Retry, as before; no plain short is made. Each call starts on the
primary again, so a sound call after a switched picture call tries the CLI first.

Only transport failures move: `PlanInvalid` (a reply that is not a plan) is the 8.2
rejection the pipeline retries on the same adapter, and `ledger.BudgetExceeded` /
`LedgerError` are hard stops; all three propagate untouched from whichever adapter
raised them. Every retry and switch writes a job.log line naming the adapter, the call
and the error that moved it.

`bind(job)` binds the primary at once and the backup on its first use in that binding,
so the backup's plan files land in their own `work/planner/run<n>/` rather than over the
primary's; `ask` on the backup is named `<name>_backup` in `work/editor/` for the same
reason. The backup's ledger rows are its own (`planner`, cash), so the job page shows
what the switch cost.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from typing import Self, TypeVar

from shortsmith import jobs
from shortsmith.contracts import PicturePlan, PlanFeedback, PlanRequest, SoundStory
from shortsmith.jobs import Job
from shortsmith.planner.base import Planner, PlannerError, PlannerUnavailable
from shortsmith.planner.claude_code import QuotaSpent

T = TypeVar("T")
BACKUP_SUFFIX = "_backup"


def _switches_at_once(exc: Exception) -> bool:
    """Errors that no retry on the same adapter can cure."""
    return isinstance(exc, QuotaSpent | PlannerUnavailable)


class FailoverPlanner(Planner):
    def __init__(self, primary: Planner, backup: Planner) -> None:
        self.primary = primary
        self.backup = backup
        self._job: Job | None = None
        self._unbound_backup: Planner | None = None

    def bind(self, job: Job) -> Self:
        bound = copy.copy(self)
        bound._job = job
        bound.primary = self.primary.bind(job)
        bound._unbound_backup = self._unbound_backup or self.backup
        return bound

    def _backup(self) -> Planner:
        """The backup, bound to this binding's job on first use (see the module doc)."""
        if self._unbound_backup is not None and self._job is not None:
            self.backup = self._unbound_backup.bind(self._job)
            self._unbound_backup = None
        return self.backup

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        return self._run("picture", lambda p: p.plan_picture(request, feedback=feedback))

    def plan_sound(
        self,
        request: PlanRequest,
        picture: PicturePlan,
        catalogue_tags: Sequence[str] = (),
        *,
        feedback: PlanFeedback | None = None,
    ) -> SoundStory:
        return self._run(
            "sound",
            lambda p: p.plan_sound(request, picture, catalogue_tags, feedback=feedback),
        )

    def ask(self, name: str, system: str, text: str, *, step: str) -> str:
        return self._run(
            name,
            lambda p: p.ask(
                name if p is self.primary else name + BACKUP_SUFFIX, system, text, step=step
            ),
        )

    def _run(self, call: str, attempt: Callable[[Planner], T]) -> T:
        primary = self.primary
        try:
            return self._twice(call, primary, attempt)
        except (PlannerError, PlannerUnavailable) as exc:
            first = exc
        backup = self._backup()
        self._note(f"planner: {call} switched from {_name(primary)} to {_name(backup)}: {first}")
        try:
            return self._twice(call, backup, attempt)
        except (PlannerError, PlannerUnavailable) as exc:
            self._note(f"planner: {call} failed on {_name(backup)} too: {exc}")
            raise exc from first

    def _twice(self, call: str, planner: Planner, attempt: Callable[[Planner], T]) -> T:
        """One call, and one retry when the error is transient."""
        try:
            return attempt(planner)
        except (PlannerError, PlannerUnavailable) as exc:
            if _switches_at_once(exc):
                raise
            self._note(f"planner: {call} on {_name(planner)} failed, retrying once: {exc}")
        return attempt(planner)

    def _note(self, line: str) -> None:
        if self._job is not None:
            jobs.note(self._job, line)


def _name(planner: Planner) -> str:
    return type(planner).__name__
