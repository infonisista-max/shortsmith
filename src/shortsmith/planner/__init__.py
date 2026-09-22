"""The planner (PRD `planner`; decisions 8.1, 8.2, 8.3, 12.1).

`base` holds the interface, `fake` the canned fixture plans, `prompt` the one prompt
builder over the versioned files in `prompts/`, `parse` the shared reply parser and
`claude_code` the CLI adapter on the operator's subscription. `PLANNER` selects the
adapter; `api` (015) still fails the job at `planning` with its ticket named, never a
silent fallback to the fake.
"""

from __future__ import annotations

from collections.abc import Callable

from shortsmith.config import Settings
from shortsmith.ledger import Ledger
from shortsmith.planner import claude_code, parse, prompt
from shortsmith.planner.base import (
    PlanInvalid,
    Planner,
    PlannerError,
    PlannerUnavailable,
    UnavailablePlanner,
)
from shortsmith.planner.claude_code import ClaudeCodePlanner
from shortsmith.planner.fake import FakePlanner, kinds_named

__all__ = [
    "ClaudeCodePlanner",
    "FakePlanner",
    "PlanInvalid",
    "Planner",
    "PlannerError",
    "PlannerUnavailable",
    "UnavailablePlanner",
    "claude_code",
    "from_settings",
    "kinds_named",
    "parse",
    "prompt",
]


def from_settings(settings: Settings, *, ledger: Callable[[], Ledger]) -> Planner:
    """The adapter `PLANNER` names; `ledger` resolves the app's ledger at call time."""
    if settings.planner == "fake":
        return FakePlanner()
    if settings.planner == "claude_code":
        return ClaudeCodePlanner(ledger)
    return UnavailablePlanner(settings.planner, "015")
