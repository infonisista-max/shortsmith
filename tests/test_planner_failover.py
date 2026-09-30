"""planner.failover (095, operator answer 2): the CLI planner first, the API behind it.
A spent subscription moves the call to the API at once; a transient CLI error is retried
once on the CLI; both failing raises the last error; a reply that is not a plan never
fails over. `ask` is the editor's free-text call on both adapters: files under
`work/editor/`, one ledger row at the step it names. The CLI is a scripted runner and
the API a scripted create function over the recorded fixtures; nothing paid runs."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from anthropic.types import Message
from pydantic import SecretStr

from shortsmith import fixture, jobs
from shortsmith.config import Settings
from shortsmith.contracts import Constraints, PicturePlan, PlanRequest, PlanStyle
from shortsmith.ledger import BudgetExceeded, Caps, Ledger, Prices
from shortsmith.planner import (
    ApiPlanner,
    ClaudeCodePlanner,
    FailoverPlanner,
    FakePlanner,
    PlanInvalid,
    PlannerError,
    PlannerUnavailable,
    UnavailablePlanner,
    from_settings,
)
from shortsmith.planner.claude_code import QuotaSpent
from shortsmith.transcriber import FakeTranscriber

FIXTURES = Path(__file__).parent / "fixtures"
CLI = FIXTURES / "claude_cli"
ANTHROPIC = FIXTURES / "anthropic"
KEY = "sk-ant-test-not-real"
PRICES = Prices(
    {
        "planner": {
            "input_tokens": 0.25,
            "cache_write_input_tokens": 0.3125,
            "cache_read_input_tokens": 0.025,
            "output_tokens": 1.25,
        },
        "api_equivalent": {"input_tokens": 0.25, "output_tokens": 1.25},
    }
)


def _envelope(name: str) -> bytes:
    return (CLI / f"{name}.json").read_bytes()


def _text_envelope(text: str) -> bytes:
    """A successful CLI envelope whose `result` is `text`, with some token usage."""
    envelope = json.loads(_envelope("picture"))
    envelope["result"] = text
    return json.dumps(envelope).encode("utf-8")


def _message(name: str, text: str | None = None) -> Message:
    body: dict[str, Any] = json.loads((ANTHROPIC / f"{name}.json").read_text(encoding="utf-8"))
    if text is not None:
        body["content"] = [{"type": "text", "text": text}]
    return Message.model_validate(body)


@dataclass
class ScriptedCli:
    """Answers each run with the next scripted stdout; counts the runs."""

    replies: list[bytes | Exception]
    argvs: list[list[str]] = field(default_factory=lambda: [])

    def __call__(
        self, argv: list[str], stdin: str, cwd: Path, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[bytes]:
        self.argvs.append(argv)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return subprocess.CompletedProcess(argv, 0, reply, b"")


@dataclass
class ScriptedApi:
    """Answers each Messages call with the next scripted reply; records the calls."""

    replies: list[Message | Exception]
    requests: list[dict[str, Any]] = field(default_factory=lambda: [])

    def __call__(self, **params: Any) -> Message:
        self.requests.append(params)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _request() -> PlanRequest:
    return PlanRequest(
        brief="Topic: nothing. Must-say: twelve words.",
        style=PlanStyle(
            name="explainer", numbers={"broll": {"kinds": ["photo"], "tier2_kinds": []}}
        ),
        style_note="explainer",
        transcript=FakeTranscriber().transcribe(Path("unused.mp4")),
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )


@pytest.fixture
def job(tmp_path: Path) -> jobs.Job:
    return jobs.create(tmp_path, style="explainer", style_note="explainer")


def _book(hard: float | None = None) -> Ledger:
    return Ledger(PRICES, Caps(per_job=None, hard=hard, per_day=500))


def _failover(
    cli: ScriptedCli, api: ScriptedApi, job: jobs.Job, *, book: Ledger | None = None
) -> FailoverPlanner:
    ledger = book or _book()
    primary = ClaudeCodePlanner(lambda: ledger, run=cli)
    backup = ApiPlanner(lambda: ledger, api_key=SecretStr(KEY), model="claude-sonnet-5", create=api)
    return FailoverPlanner(primary, backup).bind(job)


def _log(job: jobs.Job) -> str:
    return job.log_path.read_text(encoding="utf-8")


def _rows(job: jobs.Job) -> list[tuple[str, str]]:
    return [(row.step, row.provider) for row in jobs.load(job.path).record.cost]


def test_a_spent_cli_quota_moves_the_call_to_the_api_at_once(job: jobs.Job) -> None:
    cli = ScriptedCli([_envelope("quota")])
    api = ScriptedApi([_message("picture")])
    plan = _failover(cli, api, job).plan_picture(_request())
    assert isinstance(plan, PicturePlan)
    assert plan.beats == FakePlanner().plan_picture(_request()).beats
    assert len(cli.argvs) == 1  # a spent quota is not retried on the CLI
    assert len(api.requests) == 1
    log = _log(job)
    assert "switched from ClaudeCodePlanner to ApiPlanner" in log
    assert "usage is spent" in log
    assert _rows(job) == [("planning", "planner")]  # the quota envelope used no tokens
    # the backup writes its own run folder, never over the CLI's reply
    assert (job.work_dir / "planner" / "run1" / "reply_picture.json").read_bytes() == _envelope(
        "quota"
    )
    assert (job.work_dir / "planner" / "run2" / "reply_picture.json").is_file()


def test_a_transient_cli_error_is_retried_once_on_the_cli(job: jobs.Job) -> None:
    cli = ScriptedCli([_envelope("error"), _envelope("picture")])
    api = ScriptedApi([])
    plan = _failover(cli, api, job).plan_picture(_request())
    assert isinstance(plan, PicturePlan)
    assert len(cli.argvs) == 2 and api.requests == []
    log = _log(job)
    assert "picture on ClaudeCodePlanner failed, retrying once" in log
    assert "switched" not in log


def test_a_cli_error_twice_moves_to_the_api_and_a_missing_cli_moves_at_once(
    job: jobs.Job,
) -> None:
    cli = ScriptedCli([_envelope("error"), _envelope("error")])
    api = ScriptedApi([_message("picture")])
    assert isinstance(_failover(cli, api, job).plan_picture(_request()), PicturePlan)
    assert len(cli.argvs) == 2 and len(api.requests) == 1

    missing = ScriptedCli([PlannerUnavailable("the 'claude' CLI is not on PATH")])
    api = ScriptedApi([_message("picture")])
    assert isinstance(_failover(missing, api, job).plan_picture(_request()), PicturePlan)
    assert len(missing.argvs) == 1 and len(api.requests) == 1


def test_both_planners_failing_raise_the_backups_last_error(job: jobs.Job) -> None:
    cli = ScriptedCli([_envelope("quota")])
    refused = _message("refusal")
    api = ScriptedApi([refused, refused])
    with pytest.raises(PlannerError, match="refused") as caught:
        _failover(cli, api, job).plan_picture(_request())
    assert not isinstance(caught.value, QuotaSpent)
    assert isinstance(caught.value.__cause__, QuotaSpent)
    assert len(api.requests) == 2  # the backup's one transient retry
    assert "failed on ApiPlanner too" in _log(job)


def test_a_reply_that_is_not_a_plan_never_fails_over(job: jobs.Job) -> None:
    cli = ScriptedCli([_text_envelope("no json here")])
    api = ScriptedApi([])
    with pytest.raises(PlanInvalid):
        _failover(cli, api, job).plan_picture(_request())
    assert len(cli.argvs) == 1 and api.requests == []


def test_the_hard_cap_on_the_backup_is_never_failed_over_or_retried(job: jobs.Job) -> None:
    cli = ScriptedCli([_envelope("quota")])
    api = ScriptedApi([])
    with pytest.raises(BudgetExceeded):
        _failover(cli, api, job, book=_book(hard=0.0)).plan_picture(_request())
    assert api.requests == []


def test_ask_on_the_cli_writes_editor_files_and_a_row_at_its_step(job: jobs.Job) -> None:
    book = _book()
    cli = ScriptedCli([_text_envelope('{"choices": []}')])
    planner = ClaudeCodePlanner(lambda: book, run=cli).bind(job)
    reply = planner.ask("round1", "You are the editor.", "the snags", step="rendering")
    assert reply == '{"choices": []}'
    editor = job.work_dir / "editor"
    assert (editor / "request_round1.md").read_text(encoding="utf-8") == "the snags"
    assert (editor / "reply_round1.json").is_file()
    (argv,) = cli.argvs
    assert argv[argv.index("--system-prompt") + 1] == "You are the editor."
    assert argv.count("--system-prompt") == 1
    assert argv[argv.index("--tools") + 1] == ""
    assert _rows(job) == [("rendering", "claude_code")]


def test_ask_on_the_api_writes_editor_files_and_a_row_at_its_step(job: jobs.Job) -> None:
    book = _book()
    api = ScriptedApi([_message("picture", text='{"choices": []}')])
    planner = ApiPlanner(lambda: book, api_key=SecretStr(KEY), create=api).bind(job)
    reply = planner.ask("round1", "You are the editor.", "the snags", step="sourcing")
    assert reply == '{"choices": []}'
    editor = job.work_dir / "editor"
    assert (editor / "request_round1.md").read_text(encoding="utf-8") == "the snags"
    assert (editor / "reply_round1.json").is_file()
    (params,) = api.requests
    assert params["system"] == [{"type": "text", "text": "You are the editor."}]
    assert params["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "the snags"}]}
    ]
    assert _rows(job) == [("sourcing", "planner")]


def test_ask_on_the_api_raises_on_a_refusal_or_a_cut(job: jobs.Job) -> None:
    cut = _message("picture")
    cut = cut.model_copy(update={"stop_reason": "max_tokens"})
    api = ScriptedApi([_message("refusal"), cut])
    planner = ApiPlanner(_book, api_key=SecretStr(KEY), create=api).bind(job)
    with pytest.raises(PlannerError, match="refused"):
        planner.ask("round1", "sys", "text", step="qa")
    with pytest.raises(PlannerError, match="max_tokens"):
        planner.ask("round1", "sys", "text", step="qa")


def test_ask_fails_over_to_the_api_under_its_own_file_name(job: jobs.Job) -> None:
    cli = ScriptedCli([_envelope("quota")])
    api = ScriptedApi([_message("picture", text="ok")])
    assert _failover(cli, api, job).ask("round1", "sys", "text", step="sourcing") == "ok"
    editor = job.work_dir / "editor"
    assert (editor / "reply_round1.json").read_bytes() == _envelope("quota")
    assert (editor / "reply_round1_backup.json").is_file()


def test_the_fake_and_an_unavailable_planner_cannot_be_asked(job: jobs.Job) -> None:
    for planner in (FakePlanner(), UnavailablePlanner("api", "015")):
        with pytest.raises(PlannerUnavailable):
            planner.bind(job).ask("round1", "sys", "text", step="planning")


def test_from_settings_wraps_the_cli_in_the_failover_only_with_an_api_key() -> None:
    book = _book()
    keyed = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        planner="claude_code",
        planner_model="claude-opus-5",
        anthropic_api_key=SecretStr(KEY),
    )
    chosen = from_settings(keyed, ledger=lambda: book)
    assert isinstance(chosen, FailoverPlanner)
    assert isinstance(chosen.primary, ClaudeCodePlanner)
    assert isinstance(chosen.backup, ApiPlanner) and chosen.backup.model == "claude-opus-5"
    bare = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        planner="claude_code",
        anthropic_api_key=None,
    )
    assert isinstance(from_settings(bare, ledger=lambda: book), ClaudeCodePlanner)
