"""The planner (PRD `planner`; decisions 8.1, 8.2, 8.3, 12.1).

`base` holds the interface, `fake` the canned fixture plans, `prompt` the one prompt
builder over the versioned files in `prompts/`, `parse` the shared reply parser and
`claude_code` the CLI adapter on the operator's subscription, `api` the Messages API
adapter paid per token. `PLANNER` selects the adapter; both real ones send the same
prompt through the same parser, so the choice changes cost and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable

from shortsmith.config import Settings
from shortsmith.ledger import Ledger
from shortsmith.planner import api, claude_code, parse, prompt
from shortsmith.planner.api import ApiPlanner
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
    "ApiPlanner",
    "ClaudeCodePlanner",
    "FakePlanner",
    "PlanInvalid",
    "Planner",
    "PlannerError",
    "PlannerUnavailable",
    "UnavailablePlanner",
    "api",
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
    return ApiPlanner(ledger, api_key=settings.anthropic_api_key, model=settings.planner_model)
