"""planner.api: the paid planner (8.3). One Messages call per planner call through the
anthropic SDK: the builder's identical prompt text, split into a cached system prompt,
the instructions, the cached spec sections (1-2) and the request (3 onward); no tools;
the model from `PLANNER_MODEL`. The reply's usage becomes one cash ledger row (fresh,
cache-write and cache-read input tokens at their own price keys), recorded before the
reply is parsed by the same parser as the CLI adapter. The stub stands in for one
Messages call and answers with the recorded replies in `tests/fixtures/anthropic/`,
read through the SDK's own `Message` model; no network, no key."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anthropic import APIStatusError
from anthropic.types import Message
from pydantic import SecretStr

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
from shortsmith.ledger import BudgetExceeded, Caps, Ledger, Prices
from shortsmith.planner import (
    ApiPlanner,
    ClaudeCodePlanner,
    FakePlanner,
    PlanInvalid,
    PlannerError,
    from_settings,
    prompt,
)
from shortsmith.transcriber import FakeTranscriber

ANTHROPIC = Path(__file__).parent / "fixtures" / "anthropic"
CLI = Path(__file__).parent / "fixtures" / "claude_cli"
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


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((ANTHROPIC / f"{name}.json").read_text(encoding="utf-8"))


def _ok(name: str) -> Message:
    return Message.model_validate(_fixture(name))


def _status_error(status: int, body: dict[str, Any]) -> APIStatusError:
    """The SDK's error as it arrives, without building one of its http objects."""
    response = SimpleNamespace(status_code=status, headers={}, request=None)
    return APIStatusError("boom", response=cast(Any, response), body=body)


@dataclass
class StubApi:
    """Answers with the queued replies (or raises them) and records every call."""

    replies: list[Message | Exception]
    requests: list[dict[str, Any]] = field(default_factory=lambda: [])

    def __call__(self, **params: Any) -> Message:
        self.requests.append(params)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def body(self, index: int = 0) -> dict[str, Any]:
        """The call's arguments as JSON, the shape the SDK puts on the wire."""
        return cast(dict[str, Any], json.loads(json.dumps(self.requests[index])))


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


def _planner(api: StubApi, job: jobs.Job, *, book: Ledger | None = None) -> ApiPlanner:
    ledger = book or _book()
    return ApiPlanner(
        lambda: ledger, api_key=SecretStr(KEY), model="claude-sonnet-5", create=api
    ).bind(job)


def _texts(body: dict[str, Any]) -> list[str]:
    (message,) = body["messages"]
    return [block["text"] for block in message["content"]]


def _cli(job: jobs.Job, seen: list[str]) -> ClaudeCodePlanner:
    """The 014 adapter answering from the CLI fixtures, recording what it sent on stdin."""

    def run(argv: list[str], stdin: str, cwd: Path, env: object) -> Any:
        seen.append(stdin)
        name = "sound" if "## 7. Validated picture plan" in stdin else "picture"
        return subprocess.CompletedProcess(argv, 0, (CLI / f"{name}.json").read_bytes(), b"")

    return ClaudeCodePlanner(lambda: _book(), run=run).bind(job)  # pyright: ignore[reportArgumentType]


def test_the_picture_call_sends_the_cli_prompt_split_with_cache_markers(
    job: jobs.Job,
) -> None:
    """8.3: the identical text the CLI adapter sends on stdin, as system + user blocks;
    cache markers on the system prompt and on the spec sections; no tools."""
    stdin: list[str] = []
    _cli(job, stdin).plan_picture(_request())  # first, so the api adapter's files are last
    api = StubApi([_ok("picture")])
    plan = _planner(api, job).plan_picture(_request())

    body = api.body()
    texts = _texts(body)
    assert "".join(texts) == stdin[0] == prompt.build_prompt(_request(), "picture")
    assert texts[1].startswith("## 1. Style numbers") and texts[2].startswith("## 3. Brief")
    assert body["system"][0]["text"] == prompt.SYSTEM_PROMPT
    skeleton = _fixture("request")
    body["system"][0]["text"] = "<SYSTEM_PROMPT>"
    for block, placeholder in zip(
        body["messages"][0]["content"], _texts(skeleton), strict=True
    ):
        block["text"] = placeholder
    assert body == skeleton  # model, max_tokens, cache markers, and no tools
    assert isinstance(plan, PicturePlan)
    assert plan.prompt_version == prompt.PROMPT_VERSION
    folder = job.work_dir / "planner"
    assert (folder / "request_picture.md").read_text("utf-8") == stdin[0]
    assert json.loads((folder / "reply_picture.json").read_text("utf-8"))["id"].startswith("msg_")


def test_usage_is_a_cash_row_with_cached_tokens_at_their_own_price_keys(
    job: jobs.Job,
) -> None:
    api = StubApi([_ok("picture"), _ok("sound")])
    planner = _planner(api, job)
    planner.plan_sound(_request(), planner.plan_picture(_request()))
    first, second = jobs.load(job.path).record.cost
    assert (first.step, first.provider, first.model) == ("planning", "planner", "claude-sonnet-5")
    assert first.units == {
        "input_tokens": 2100,
        "cache_write_input_tokens": 9000,
        "cache_read_input_tokens": 0,
        "output_tokens": 1800,
    }
    assert first.inr == pytest.approx((2100 * 0.25 + 9000 * 0.3125 + 1800 * 1.25) / 1000)
    assert second.units["cache_read_input_tokens"] == 9000
    assert second.inr == pytest.approx((5400 * 0.25 + 9000 * 0.025 + 420 * 1.25) / 1000)


def test_the_hard_cap_stops_the_call_before_it_is_made(job: jobs.Job) -> None:
    api = StubApi([_ok("picture")])
    with pytest.raises(BudgetExceeded, match="planning"):
        _planner(api, job, book=_book(hard=0.01)).plan_picture(_request())
    assert api.requests == []
    assert jobs.load(job.path).record.cost == []


def test_the_sound_call_and_the_retry_send_the_builder_text(job: jobs.Job) -> None:
    api = StubApi([_ok("sound"), _ok("sound")])
    planner = _planner(api, job)
    picture = FakePlanner().plan_picture(_request())
    story = planner.plan_sound(_request(), picture, ["suspense", "money"])
    feedback = PlanFeedback(previous="{}", violations=["cue c01 (7.3): too loud"])
    planner.plan_sound(_request(), picture, ["suspense", "money"], feedback=feedback)
    first = prompt.build_prompt(
        _request(), "sound", picture=picture, catalogue_tags=["suspense", "money"]
    )
    retry = prompt.build_prompt(
        _request(), "sound", picture=picture, catalogue_tags=["suspense", "money"],
        feedback=feedback,
    )  # fmt: skip
    assert "".join(_texts(api.body(0))) == first
    assert "".join(_texts(api.body(1))) == retry
    folder = job.work_dir / "planner"
    assert (folder / "request_sound_retry.md").read_text("utf-8") == retry
    assert (folder / "reply_sound_retry.json").is_file()
    assert isinstance(story, SoundStory)


def test_a_reply_that_is_not_a_plan_is_plan_invalid_and_still_a_ledger_row(
    job: jobs.Job,
) -> None:
    reply = _fixture("picture")
    reply["content"] = [{"type": "text", "text": "Sorry, I need more detail."}]
    api = StubApi([Message.model_validate(reply)])
    with pytest.raises(PlanInvalid) as caught:
        _planner(api, job).plan_picture(_request())
    assert caught.value.violations == ["plan (8.2): the reply holds no JSON object"]
    assert len(jobs.load(job.path).record.cost) == 1


def test_a_refusal_or_a_cut_off_reply_is_a_planner_error_but_still_billed(
    job: jobs.Job,
) -> None:
    with pytest.raises(PlannerError, match="refus"):
        _planner(StubApi([_ok("refusal")]), job).plan_picture(_request())
    cut = _fixture("picture")
    cut["stop_reason"] = "max_tokens"
    with pytest.raises(PlannerError, match="max_tokens"):
        _planner(StubApi([Message.model_validate(cut)]), job).plan_picture(_request())
    assert len(jobs.load(job.path).record.cost) == 2


def test_an_http_error_is_a_planner_error_with_the_api_words_and_no_row(
    job: jobs.Job,
) -> None:
    api = StubApi([_status_error(529, _fixture("error"))])
    with pytest.raises(PlannerError, match="529.*Overloaded") as caught:
        _planner(api, job).plan_picture(_request())
    assert KEY not in str(caught.value)
    assert jobs.load(job.path).record.cost == []


def test_an_unbound_or_keyless_planner_refuses_to_call(job: jobs.Job) -> None:
    book = _book()
    with pytest.raises(PlannerError, match="bind"):
        ApiPlanner(lambda: book, api_key=SecretStr(KEY)).plan_picture(_request())
    with pytest.raises(PlannerError, match="ANTHROPIC_API_KEY"):
        ApiPlanner(lambda: book, api_key=None).bind(job).plan_picture(_request())


def test_the_same_reply_parses_identically_through_both_adapters(job: jobs.Job) -> None:
    """8.3: switching PLANNER changes cost and nothing else."""
    cli = _cli(job, [])
    api = _planner(StubApi([_ok("picture"), _ok("sound")]), job)
    cli_picture = cli.plan_picture(_request())
    api_picture = api.plan_picture(_request())
    assert api_picture == cli_picture
    assert api.plan_sound(_request(), api_picture) == cli.plan_sound(_request(), cli_picture)


def test_from_settings_selects_the_api_adapter_with_the_configured_model() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        planner="api",
        planner_model="claude-opus-5",
        anthropic_api_key=SecretStr(KEY),
    )
    chosen = from_settings(settings, ledger=_book)
    assert isinstance(chosen, ApiPlanner)
    assert chosen.model == "claude-opus-5"
    default = Settings(_env_file=None, planner="api")  # pyright: ignore[reportCallIssue]
    assert default.planner_model == "claude-sonnet-5"
