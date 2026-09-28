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


def from_settings(
    settings: Settings,
    *,
    ledger: Callable[[], Ledger],
    reload: Callable[[], Settings] | None = None,
) -> Planner:
    """The adapter `PLANNER` names; `ledger` resolves the app's ledger at call time.
    `reload` re-reads the settings (the app passes `config.load`), so the CLI adapter
    picks up an edited `PLANNER_CLI_MODEL` at each job's planning step (065); without
    it the model is the one in `settings`."""
    if settings.planner == "fake":
        return FakePlanner()
    if settings.planner == "claude_code":
        fresh = reload or (lambda: settings)
        return ClaudeCodePlanner(ledger, model=lambda: fresh().planner_cli_model)
    return ApiPlanner(ledger, api_key=settings.anthropic_api_key, model=settings.planner_model)
