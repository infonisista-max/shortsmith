"""planner.claude_code: the CLI adapter on the operator's subscription (8.3). It writes
the builder's prompt to `work/planner/request_<call>.md`, runs `claude -p
--output-format json` with no tools, no MCP servers, no CLAUDE.md and no session,
from the job's planner directory, with the prompt on stdin and no API key in the
child's environment (so the subscription is what pays), reads the CLI's JSON envelope,
parses the reply with the shared parser, and records one ledger row per call at INR 0
with the CLI's token usage. Tests stub the subprocess with the envelopes under
`tests/fixtures/claude_cli/`; the real CLI never runs here."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shortsmith import fixture, jobs
from shortsmith.config import Settings
from shortsmith.contracts import (
    Constraints,
    PicturePlan,
    PlanFeedback,
    PlanRequest,
    PlanStyle,
    SoundStory,
)
from shortsmith.ledger import Caps, Ledger, Prices
from shortsmith.planner import (
    ClaudeCodePlanner,
    FakePlanner,
    PlanInvalid,
    PlannerError,
    PlannerUnavailable,
    UnavailablePlanner,
    claude_code,
    from_settings,
    parse,
    prompt,
)
from shortsmith.transcriber import FakeTranscriber

CLI = Path(__file__).parent / "fixtures" / "claude_cli"
PRICES = Prices({"api_equivalent": {"input_tokens": 0.25, "output_tokens": 1.25}})


def _envelope(name: str) -> bytes:
    return (CLI / f"{name}.json").read_bytes()


@dataclass
class Call:
    argv: list[str]
    stdin: str
    cwd: Path
    env: Mapping[str, str]


@dataclass
class StubCli:
    """Replies with the queued stdout payloads in order, recording every call."""

    replies: list[bytes]
    returncode: int = 0
    stderr: bytes = b""
    calls: list[Call] = field(default_factory=lambda: [])

    def __call__(
        self, argv: list[str], stdin: str, cwd: Path, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(Call(argv, stdin, cwd, env))
        return subprocess.CompletedProcess(argv, self.returncode, self.replies.pop(0), self.stderr)


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


def _planner(cli: StubCli, job: jobs.Job) -> ClaudeCodePlanner:
    book = Ledger(PRICES, Caps(per_job=None, hard=None, per_day=500))
    return ClaudeCodePlanner(lambda: book, run=cli).bind(job)


def test_the_picture_call_writes_the_prompt_and_runs_the_cli_without_tools(
    job: jobs.Job, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    cli = StubCli([_envelope("picture")])
    plan = _planner(cli, job).plan_picture(_request())
    expected = prompt.build_prompt(_request(), "picture")
    written = job.work_dir / "planner" / "run1" / "request_picture.md"
    assert written.read_text(encoding="utf-8") == expected
    (call,) = cli.calls
    assert call.argv[:4] == ["claude", "-p", "--output-format", "json"]
    assert call.argv[call.argv.index("--tools") + 1] == ""
    for flag in ("--safe-mode", "--strict-mcp-config", "--no-session-persistence"):
        assert flag in call.argv, flag
    assert "JSON only" in call.argv[call.argv.index("--system-prompt") + 1]
    assert call.stdin == expected
    assert call.cwd == job.work_dir / "planner" / "run1"
    assert "ANTHROPIC_API_KEY" not in call.env  # the subscription pays, never an API key
    assert isinstance(plan, PicturePlan)
    assert plan.beats == FakePlanner().plan_picture(_request()).beats
    assert plan.prompt_version == prompt.PROMPT_VERSION


def test_each_call_is_a_ledger_row_at_zero_inr_with_the_cli_tokens(job: jobs.Job) -> None:
    """8.3 / 11.3: input tokens count the cache writes and reads the CLI reports."""
    cli = StubCli([_envelope("picture"), _envelope("sound")])
    planner = _planner(cli, job)
    picture = planner.plan_picture(_request())
    planner.plan_sound(_request(), picture)
    first, second = jobs.load(job.path).record.cost
    assert (first.step, first.provider) == ("planning", "claude_code")
    assert first.model == "claude-sonnet-5"
    assert first.inr == 0.0
    assert first.units == {"input_tokens": 12 + 9000 + 2000, "output_tokens": 1800}
    assert first.tokens_estimated == 11012 + 1800
    assert first.inr_equivalent == pytest.approx(11012 * 0.25 / 1000 + 1800 * 1.25 / 1000)
    assert second.units == {"input_tokens": 8 + 3500 + 9000, "output_tokens": 420}


def test_the_sound_call_sends_the_picture_plan_and_the_catalogue_tags(job: jobs.Job) -> None:
    cli = StubCli([_envelope("sound")])
    picture = FakePlanner().plan_picture(_request())
    story = _planner(cli, job).plan_sound(_request(), picture, ["suspense", "money"])
    expected = prompt.build_prompt(
        _request(), "sound", picture=picture, catalogue_tags=["suspense", "money"]
    )
    assert cli.calls[0].stdin == expected
    assert (job.work_dir / "planner" / "run1" / "request_sound.md").read_text("utf-8") == expected
    assert isinstance(story, SoundStory)
    assert story.prompt_version == prompt.PROMPT_VERSION


def test_a_retry_sends_the_feedback_and_keeps_the_first_request_on_disk(job: jobs.Job) -> None:
    cli = StubCli([_envelope("picture"), _envelope("picture")])
    planner = _planner(cli, job)
    planner.plan_picture(_request())
    feedback = PlanFeedback(previous="{}", violations=["b03 (4.1): no motion"])
    planner.plan_picture(_request(), feedback=feedback)
    folder = job.work_dir / "planner" / "run1"
    assert "b03 (4.1): no motion" not in (folder / "request_picture.md").read_text("utf-8")
    assert "- b03 (4.1): no motion" in (folder / "request_picture_retry.md").read_text("utf-8")
    assert "- b03 (4.1): no motion" in cli.calls[1].stdin
    assert len(jobs.load(job.path).record.cost) == 2  # every call and retry is a row (8.2)


def test_a_reply_that_is_not_a_plan_is_plan_invalid_and_still_a_ledger_row(
    job: jobs.Job,
) -> None:
    envelope = json.loads(_envelope("picture"))
    envelope["result"] = "Sorry, I need more detail about the brief."
    cli = StubCli([json.dumps(envelope).encode()])
    with pytest.raises(PlanInvalid) as caught:
        _planner(cli, job).plan_picture(_request())
    assert caught.value.reply == "Sorry, I need more detail about the brief."
    assert caught.value.violations == ["plan (8.2): the reply holds no JSON object"]
    assert len(jobs.load(job.path).record.cost) == 1
    reply = job.work_dir / "planner" / "run1" / "reply_picture.json"
    assert json.loads(reply.read_text("utf-8"))["result"].startswith("Sorry")


def test_a_cli_error_is_a_planner_error_not_a_retry(job: jobs.Job) -> None:
    """Usage limit, auth or crash: the job fails at planning with the CLI's words; the
    8.2 retry is for plans the grammar or the models reject, not for a broken CLI."""
    with pytest.raises(PlannerError, match="Internal server error") as caught:
        _planner(StubCli([_envelope("error")]), job).plan_picture(_request())
    assert not isinstance(caught.value, claude_code.QuotaSpent)
    crashed = StubCli([b"not json"], returncode=1, stderr=b"Error: not logged in")
    with pytest.raises(PlannerError, match="not logged in"):
        _planner(crashed, job).plan_picture(_request())


def test_run04s_spent_credits_reply_is_quota_spent_with_the_cli_words(job: jobs.Job) -> None:
    """065 (2): status 429 is the signal; the CLI's `result` stays in the text."""
    with pytest.raises(claude_code.QuotaSpent, match="out of usage credits"):
        _planner(StubCli([_envelope("quota")]), job).plan_picture(_request())


def test_a_limit_reply_without_its_status_is_still_recognised_by_its_phrase(
    job: jobs.Job,
) -> None:
    envelope = json.loads(_envelope("quota"))
    del envelope["api_error_status"]
    with pytest.raises(claude_code.QuotaSpent, match="out of usage credits"):
        _planner(StubCli([json.dumps(envelope).encode()]), job).plan_picture(_request())
    for words in ("Claude AI usage limit reached|1790000000", "You've hit your limit"):
        envelope["result"] = words
        with pytest.raises(claude_code.QuotaSpent):
            _planner(StubCli([json.dumps(envelope).encode()]), job).plan_picture(_request())


def test_a_zero_token_cli_error_writes_no_ledger_row(job: jobs.Job) -> None:
    """065 (3): no `unknown`, 0-token row; a rejected reply that used tokens keeps its row
    (`test_a_reply_that_is_not_a_plan_is_plan_invalid_and_still_a_ledger_row`)."""
    with pytest.raises(PlannerError):
        _planner(StubCli([_envelope("quota")]), job).plan_picture(_request())
    with pytest.raises(PlannerError):
        _planner(StubCli([_envelope("error")]), job).plan_picture(_request())
    assert jobs.load(job.path).record.cost == []


def test_every_call_and_retry_asks_for_the_pinned_model_and_logs_what_was_used(
    job: jobs.Job,
) -> None:
    """065 (4): `--model <PLANNER_CLI_MODEL>` on every call; one `asked / used` line each,
    `(differs)` when the CLI answered on another model."""
    cli = StubCli([_envelope("picture"), _envelope("picture"), _envelope("sound")])
    book = Ledger(PRICES, Caps(per_job=None, hard=None, per_day=500))
    planner = ClaudeCodePlanner(lambda: book, run=cli, model=lambda: "claude-sonnet-5").bind(job)
    picture = planner.plan_picture(_request())
    planner.plan_picture(_request(), feedback=PlanFeedback(previous="{}", violations=["x"]))
    planner.plan_sound(_request(), picture)
    assert [c.argv[c.argv.index("--model") + 1] for c in cli.calls] == ["claude-sonnet-5"] * 3
    log = (job.path / "job.log").read_text(encoding="utf-8")
    assert "planner: picture asked claude-sonnet-5, used claude-sonnet-5\n" in log
    assert "planner: picture_retry asked claude-sonnet-5, used claude-sonnet-5\n" in log
    assert "planner: sound asked claude-sonnet-5, used claude-sonnet-5\n" in log

    other = ClaudeCodePlanner(
        lambda: book, run=StubCli([_envelope("picture")]), model=lambda: "claude-opus-5-5"
    ).bind(job)
    other.plan_picture(_request())
    last = (job.path / "job.log").read_text(encoding="utf-8").splitlines()[-1]
    assert last.endswith("planner: picture asked claude-opus-5-5, used claude-sonnet-5 (differs)")


def test_the_model_is_read_when_each_job_binds_so_an_edit_needs_no_restart(
    tmp_path: Path,
) -> None:
    setting = ["claude-opus-5-5"]
    cli = StubCli([_envelope("picture"), _envelope("picture")])
    book = Ledger(PRICES, Caps(per_job=None, hard=None, per_day=500))
    planner = ClaudeCodePlanner(lambda: book, run=cli, model=lambda: setting[0])
    first = jobs.create(tmp_path, style="explainer")
    planner.bind(first).plan_picture(_request())
    setting[0] = "claude-sonnet-5"  # the operator edits .env between jobs
    planner.bind(jobs.create(tmp_path, style="explainer")).plan_picture(_request())
    assert [c.argv[c.argv.index("--model") + 1] for c in cli.calls] == [
        "claude-opus-5-5",
        "claude-sonnet-5",
    ]


def test_the_model_defaults_to_the_setting_and_from_settings_rereads_it() -> None:
    settings = Settings(_env_file=None, planner="claude_code")  # pyright: ignore[reportCallIssue]
    assert settings.planner_cli_model == "claude-opus-5-5"
    book = Ledger(PRICES, Caps(per_job=None, hard=None, per_day=500))
    edited = [settings]
    chosen = from_settings(settings, ledger=lambda: book, reload=lambda: edited[0])
    assert isinstance(chosen, ClaudeCodePlanner)
    assert chosen.cli_model() == "claude-opus-5-5"
    edited[0] = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        planner="claude_code",
        planner_cli_model="claude-sonnet-5",
    )
    assert chosen.cli_model() == "claude-sonnet-5"


def test_a_second_bind_writes_a_new_run_folder_and_never_over_the_first(
    job: jobs.Job,
) -> None:
    """065 (1): each pipeline run of `planning` binds once and gets `run<n>`."""
    book = Ledger(PRICES, Caps(per_job=None, hard=None, per_day=500))
    with pytest.raises(PlannerError):
        ClaudeCodePlanner(lambda: book, run=StubCli([_envelope("quota")])).bind(
            job
        ).plan_picture(_request())
    run1 = job.work_dir / "planner" / "run1"
    before = (run1 / "reply_picture.json").read_bytes()
    assert before == _envelope("quota")
    ClaudeCodePlanner(lambda: book, run=StubCli([_envelope("picture")])).bind(job).plan_picture(
        _request()
    )
    assert (run1 / "reply_picture.json").read_bytes() == before
    assert (job.work_dir / "planner" / "run2" / "reply_picture.json").read_bytes() == _envelope(
        "picture"
    )


def test_an_unbound_planner_refuses_to_call(job: jobs.Job) -> None:
    book = Ledger(PRICES, Caps(per_job=None, hard=None, per_day=500))
    with pytest.raises(PlannerError, match="bind"):
        ClaudeCodePlanner(lambda: book, run=StubCli([])).plan_picture(_request())


def test_a_missing_cli_is_planner_unavailable(tmp_path: Path) -> None:
    with pytest.raises(PlannerUnavailable, match="not on PATH"):
        claude_code.run_cli(["shortsmith-no-such-cli-xyz", "-p"], "hi", tmp_path, {})


def test_fake_cli_and_parser_return_the_same_model_classes(job: jobs.Job) -> None:
    """8.3: switching adapters changes cost, never the output shape."""
    request = _request()
    fake = FakePlanner()
    fake_picture = fake.plan_picture(request)
    fake_sound = fake.plan_sound(request, fake_picture)
    cli = StubCli([_envelope("picture"), _envelope("sound")])
    real = _planner(cli, job)
    cli_picture = real.plan_picture(request)
    cli_sound = real.plan_sound(request, cli_picture)
    parsed_picture = parse.parse_reply(
        fake_picture.model_dump_json(), "picture", prompt_version="v1"
    )
    parsed_sound = parse.parse_reply(fake_sound.model_dump_json(), "sound", prompt_version="v1")
    assert {type(fake_picture), type(cli_picture), type(parsed_picture)} == {PicturePlan}
    assert {type(fake_sound), type(cli_sound), type(parsed_sound)} == {SoundStory}


def test_from_settings_selects_the_cli_adapter_for_claude_code() -> None:
    settings = Settings(_env_file=None, planner="claude_code")  # pyright: ignore[reportCallIssue]
    book = Ledger(PRICES, Caps(per_job=None, hard=None, per_day=500))
    assert isinstance(from_settings(settings, ledger=lambda: book), ClaudeCodePlanner)
    api = Settings(_env_file=None, planner="api")  # pyright: ignore[reportCallIssue]
    assert not isinstance(from_settings(api, ledger=lambda: book), ClaudeCodePlanner)


def test_an_adapter_a_later_ticket_delivers_still_refuses_with_its_ticket_named() -> None:
    """`UnavailablePlanner` outlives 015: it is what a not-yet-built adapter selects."""
    chosen = UnavailablePlanner("api", "015")
    with pytest.raises(PlannerUnavailable, match="ticket 015"):
        chosen.plan_picture(_request())
