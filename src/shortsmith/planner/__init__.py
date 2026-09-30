"""The planner (PRD `planner`; decisions 8.1, 8.2, 8.3, 12.1).

`base` holds the interface, `fake` the canned fixture plans, `prompt` the one prompt
builder over the versioned files in `prompts/`, `parse` the shared reply parser and
`claude_code` the CLI adapter on the operator's subscription, `api` the Messages API
adapter paid per token. `PLANNER` selects the adapter; both real ones send the same
prompt through the same parser, so the choice changes cost and nothing else.

`failover` (095) wraps the two: under `PLANNER=claude_code` with `ANTHROPIC_API_KEY`
set, `from_settings` returns `FailoverPlanner(cli, api)`, so a spent subscription or a
CLI that fails twice moves the call to the API at `PLANNER_MODEL` instead of failing
the job; without the key the CLI adapter runs alone, as before. Every adapter also
answers `ask`, the editor's free-text call (the fake raises `PlannerUnavailable`).
"""

from __future__ import annotations

from collections.abc import Callable

from shortsmith.config import Settings
from shortsmith.ledger import Ledger
from shortsmith.planner import api, claude_code, failover, parse, prompt
from shortsmith.planner.api import ApiPlanner
from shortsmith.planner.base import (
    PlanInvalid,
    Planner,
    PlannerError,
    PlannerUnavailable,
    UnavailablePlanner,
)
from shortsmith.planner.claude_code import ClaudeCodePlanner
from shortsmith.planner.failover import FailoverPlanner
from shortsmith.planner.fake import FakePlanner, kinds_named

__all__ = [
    "ApiPlanner",
    "ClaudeCodePlanner",
    "FailoverPlanner",
    "FakePlanner",
    "PlanInvalid",
    "Planner",
    "PlannerError",
    "PlannerUnavailable",
    "UnavailablePlanner",
    "api",
    "claude_code",
    "failover",
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
    it the model is the one in `settings`. 095: `claude_code` with `ANTHROPIC_API_KEY`
    set is the CLI adapter with the API adapter (`PLANNER_MODEL`) as its failover."""
    if settings.planner == "fake":
        return FakePlanner()
    if settings.planner == "claude_code":
        fresh = reload or (lambda: settings)
        cli = ClaudeCodePlanner(ledger, model=lambda: fresh().planner_cli_model)
        if settings.anthropic_api_key is None:
            return cli
        backup = ApiPlanner(
            ledger, api_key=settings.anthropic_api_key, model=settings.planner_model
        )
        return FailoverPlanner(cli, backup)  # 095: the API answers when the CLI cannot
    return ApiPlanner(ledger, api_key=settings.anthropic_api_key, model=settings.planner_model)
