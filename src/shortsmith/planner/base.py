"""The planner interface (decisions 8.1, 8.2, 8.3).

Two sequential calls per job on one adapter: `plan_picture` then `plan_sound`, the
sound call receiving the validated, snapped picture plan (ticket 009) and the audio
catalogue tags (an empty list until 022). A call the grammar rejects is re-sent once
with `feedback`: the previous output as JSON and the violation list (8.2); the
adapter appends both to the same prompt.

`bind(job)` hands an adapter the job it is about to plan for, so a real adapter can
write its prompt under the job's `work/planner/` and record its ledger row; the fake
ignores it. A reply that is not a valid plan (no JSON, or JSON the models reject)
raises `PlanInvalid` carrying the reply and the 8.2 violation lines, which the
pipeline treats as a rejection: the same one retry applies. A planner that cannot
answer at all raises `PlannerError` and the job fails at `planning`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Self

from shortsmith.contracts import PicturePlan, PlanFeedback, PlanRequest, SoundStory
from shortsmith.jobs import Job


class PlannerUnavailable(Exception):
    """The selected planner adapter is not built yet (or cannot run here)."""


class PlannerError(Exception):
    """The planner could not answer at all (the CLI crashed, hit a usage limit, is not
    logged in): the job fails at `planning` with this text; no 8.2 retry applies."""


class PlanInvalid(Exception):
    """The planner's `call` reply did not parse into its model (8.2): `reply` is the
    text it sent, `violations` one line per problem in the grammar's line shape."""

    def __init__(self, call: str, reply: str, violations: Sequence[str]) -> None:
        self.call = call
        self.reply = reply
        self.violations = list(violations)
        super().__init__(f"the {call} reply is not a valid plan: " + "; ".join(self.violations))


class Planner(ABC):
    def bind(self, job: Job) -> Self:
        """This planner for `job`; adapters that write files or ledger rows override it."""
        return self

    @abstractmethod
    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        """The picture call (8.1): beats, hook, finale, keywords, title, description.
        `feedback` is set on the one retry after a rejection (8.2)."""

    @abstractmethod
    def plan_sound(
        self,
        request: PlanRequest,
        picture: PicturePlan,
        catalogue_tags: Sequence[str] = (),
        *,
        feedback: PlanFeedback | None = None,
    ) -> SoundStory:
        """The sound call (8.1), second because cues need the picture plan's beats."""


class UnavailablePlanner(Planner):
    """Stands in for an adapter that a later ticket delivers; every call raises."""

    def __init__(self, name: str, ticket: str) -> None:
        self.name = name
        self.ticket = ticket

    def _refuse(self) -> PlannerUnavailable:
        return PlannerUnavailable(
            f"PLANNER={self.name} is not implemented yet (ticket {self.ticket}); "
            "set PLANNER=fake to run without a paid planner"
        )

    def plan_picture(
        self, request: PlanRequest, *, feedback: PlanFeedback | None = None
    ) -> PicturePlan:
        raise self._refuse()

    def plan_sound(
        self,
        request: PlanRequest,
        picture: PicturePlan,
        catalogue_tags: Sequence[str] = (),
        *,
        feedback: PlanFeedback | None = None,
    ) -> SoundStory:
        raise self._refuse()
