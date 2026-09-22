"""assets.judge: the relevance judge, the cheap filter above the sources (5.2, 5.6).

The interface and the fake; the vision adapter's one Messages call (thumbnails in,
0-3 scores with reasons from the fixed list out) on the recorded reply in
`tests/fixtures/anthropic/`, its ledger row and its hard-cap check; and `Judging`,
the per-job bookkeeping: verdicts cached by candidate URL, the style's
`judge_max_calls` as the ceiling, and a judge that cannot answer never failing a job.
No network, no key."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anthropic import APIStatusError
from anthropic.types import Message
from PIL import Image
from pydantic import SecretStr

from shortsmith import jobs
from shortsmith.assets import judge as judging
from shortsmith.assets.judge import (
    FakeRelevanceJudge,
    JudgeError,
    Judging,
    Thumb,
    Verdict,
    VisionJudge,
)
from shortsmith.contracts import Candidate
from shortsmith.ledger import BudgetExceeded, Caps, Ledger, Prices

ANTHROPIC = Path(__file__).parent / "fixtures" / "anthropic"
KEY = "sk-ant-test-not-real"
PRICES = Prices({"judge": {"input_tokens": 0.25, "output_tokens": 1.25}})
QUERY = "India Gate Delhi"


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 30), (9, 9, 9)).save(buffer, format="PNG")
    return buffer.getvalue()


def _candidate(name: str, *, width: int = 1600, height: int = 1200) -> Candidate:
    return Candidate(url=f"https://e.example/{name}.jpg", width=width, height=height)


def _reply(name: str) -> Message:
    return Message.model_validate(json.loads((ANTHROPIC / f"{name}.json").read_text("utf-8")))


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
        return cast(dict[str, Any], json.loads(json.dumps(self.requests[index])))


@pytest.fixture
def job(tmp_path: Path) -> jobs.Job:
    return jobs.create(tmp_path, style="explainer", style_note="explainer")


def _book(hard: float | None = None) -> Ledger:
    return Ledger(PRICES, Caps(per_job=None, hard=hard, per_day=500))


def _judge(api: StubApi, job: jobs.Job, *, book: Ledger | None = None) -> VisionJudge:
    ledger = book or _book()
    return VisionJudge(
        lambda: ledger, api_key=SecretStr(KEY), model="claude-haiku-4-5-20251001", create=api
    ).bind(job)


# --- the fake (12.1) --------------------------------------------------------------------


def test_the_fake_scores_by_the_query_in_the_candidates_url() -> None:
    fake = FakeRelevanceJudge()
    scored = fake.score(
        "india gate",
        "entity",
        "Delhi",
        [
            Thumb(_candidate("india-gate-dusk")),
            Thumb(_candidate("india-monsoon")),
            Thumb(_candidate("paris-tower")),
        ],
    )
    assert [v.score for v in scored] == [3, 2, 0]
    assert scored[2].reasons == ("wrong_subject",)
    assert fake.calls == 1


# --- the vision adapter (5.2) -----------------------------------------------------------


def test_one_messages_call_carries_the_query_kind_topic_and_the_thumbnails(
    job: jobs.Job,
) -> None:
    api = StubApi([_reply("judge")])
    thumbs = [
        Thumb(_candidate("a"), _png()),
        Thumb(_candidate("b"), _png()),
        Thumb(_candidate("c")),
    ]
    _judge(api, job).score(QUERY, "entity", "Why Delhi built it", thumbs)

    body = api.body()
    assert body["model"] == "claude-haiku-4-5-20251001"
    (message,) = body["messages"]
    text = message["content"][0]["text"]
    assert QUERY in text and "entity" in text and "Why Delhi built it" in text
    assert "1600x1200" in text and "no thumbnail, URL only" in text
    images = [block for block in message["content"] if block["type"] == "image"]
    assert len(images) == 2  # the third candidate had no thumbnail
    assert images[0]["source"]["media_type"] == "image/png"
    # 5.2: the fixed reason list and the 0-3 scale are in the system prompt, cached.
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert all(reason in body["system"][0]["text"] for reason in judging.REASONS)


def test_the_reply_becomes_scores_with_reasons_from_the_fixed_list(job: jobs.Job) -> None:
    """5.2: scores 0-3, reasons only from {wrong_subject ... logo_only}; `hideous` is
    not on the list, so it is dropped rather than stored."""
    api = StubApi([_reply("judge")])
    thumbs = [Thumb(_candidate(n), _png()) for n in "abc"]
    scored = _judge(api, job).score(QUERY, "entity", "", thumbs)
    assert [v.score for v in scored] == [2, 3, 0]
    assert scored[0].reasons == ("watermark",)
    assert scored[2].reasons == ("wrong_subject", "meme")
    assert [v.accepted for v in scored] == [True, True, False]


def test_every_call_is_one_judge_ledger_row(job: jobs.Job) -> None:
    api = StubApi([_reply("judge")])
    _judge(api, job).score(QUERY, "entity", "", [Thumb(_candidate("a"), _png())])
    (row,) = jobs.load(job.path).record.cost
    assert (row.step, row.provider, row.model) == (
        "sourcing", "judge", "claude-haiku-4-5-20251001",
    )  # fmt: skip
    assert row.units == {"input_tokens": 1450.0, "output_tokens": 80.0}
    assert row.inr == pytest.approx(1450 * 0.25 / 1000 + 80 * 1.25 / 1000)


def test_the_hard_cap_stops_the_call_before_it_is_made(job: jobs.Job) -> None:
    """11.3: the call never happens, so it is never billed."""
    api = StubApi([_reply("judge")])
    with pytest.raises(BudgetExceeded, match="sourcing"):
        _judge(api, job, book=_book(hard=0.0001)).score(
            QUERY, "entity", "", [Thumb(_candidate("a"), _png())]
        )
    assert api.requests == []
    assert jobs.load(job.path).record.cost == []


def test_an_api_error_is_a_judge_error_in_the_apis_own_words(job: jobs.Job) -> None:
    response = SimpleNamespace(status_code=429, headers={}, request=None)
    error = APIStatusError(
        "boom",
        response=cast(Any, response),
        body={"error": {"message": "rate limit reached"}},
    )
    api = StubApi([error])
    with pytest.raises(JudgeError, match="429: rate limit reached"):
        _judge(api, job).score(QUERY, "entity", "", [Thumb(_candidate("a"), _png())])
    assert KEY not in str(jobs.load(job.path).record)


def test_a_refusal_is_a_judge_error_after_the_row(job: jobs.Job) -> None:
    api = StubApi([_reply("judge_refusal")])
    with pytest.raises(JudgeError, match="refused"):
        _judge(api, job).score(QUERY, "entity", "", [Thumb(_candidate("a"), _png())])
    assert len(jobs.load(job.path).record.cost) == 1  # the answered call is still billed


def test_an_unbound_judge_or_a_missing_key_says_so(job: jobs.Job) -> None:
    api = StubApi([_reply("judge")])
    unbound = VisionJudge(_book, api_key=SecretStr(KEY), create=api)
    with pytest.raises(JudgeError, match="bind"):
        unbound.score(QUERY, "entity", "", [])
    keyless = VisionJudge(_book, api_key=None, create=api).bind(job)
    with pytest.raises(JudgeError, match="ANTHROPIC_API_KEY"):
        keyless.score(QUERY, "entity", "", [])


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('{"candidates": [{"index": 1, "score": 9, "reasons": []}]}', 3),  # clamped to 3
        ('{"candidates": [{"index": 1, "score": -2, "reasons": []}]}', 0),
        ('here you go: {"candidates": [{"index": 1, "score": 2}]} hope that helps', 2),
        ('{"candidates": []}', 0),  # a candidate the model skipped scores 0
    ],
)
def test_the_parser_survives_what_a_model_actually_sends(reply: str, expected: int) -> None:
    (verdict,) = judging.parse_reply(reply, 1)
    assert verdict.score == expected


def test_a_reply_that_is_not_the_expected_json_is_a_judge_error() -> None:
    with pytest.raises(JudgeError, match="did not answer with JSON"):
        judging.parse_reply("I cannot see the images.", 2)
    with pytest.raises(JudgeError, match="no `candidates` list"):
        judging.parse_reply('{"verdicts": []}', 2)


# --- the per-job bookkeeping (5.6, 11.3) ------------------------------------------------


def _judging(**kwargs: Any) -> tuple[Judging, FakeRelevanceJudge]:
    fake = FakeRelevanceJudge()
    return Judging(judge=fake, **kwargs), fake


def _verdicts(book: Judging, candidates: list[Candidate]) -> list[Verdict] | None:
    return book.verdicts(QUERY, "entity", "", candidates, lambda _: _png())


def test_verdicts_are_cached_by_candidate_url() -> None:
    """5.6: a candidate judged once is never paid for again, even from another beat."""
    book, fake = _judging(max_calls=40)
    first = [_candidate("india-gate-a"), _candidate("india-gate-b")]
    assert _verdicts(book, first) is not None
    assert (fake.calls, book.calls) == (1, 1)

    assert _verdicts(book, first) is not None  # every URL cached: no call at all
    assert (fake.calls, book.calls) == (1, 1)

    later = [_candidate("india-gate-a"), _candidate("india-gate-c")]
    assert _verdicts(book, later) is not None  # one new URL: one call
    assert (fake.calls, book.calls) == (2, 2)


def test_the_styles_judge_max_calls_stops_the_judge_and_the_ladder_goes_on() -> None:
    """5.2 / 5.6: the ceiling spent means unjudged beats, never a failed beat."""
    book, fake = _judging(max_calls=2)
    for i in range(4):
        answered = _verdicts(book, [_candidate(f"india-gate-{i}")])
        assert (answered is not None) is (i < 2)
    assert (fake.calls, book.calls, book.capped) == (2, 2, True)
    assert book.notes == [
        "judge: the style's judge_max_calls (2) is spent; "
        "the remaining beats are sourced unjudged"
    ]


def test_a_judge_that_cannot_answer_leaves_the_beat_unjudged_not_failed() -> None:
    class Broken(FakeRelevanceJudge):
        def score(self, query: str, subject_kind: str, topic: str, thumbs: Any) -> Any:
            raise JudgeError("the judge could not be reached: boom")

    book = Judging(judge=Broken(), max_calls=40)
    assert _verdicts(book, [_candidate("a")]) is None
    assert book.notes == ["judge: the judge could not be reached: boom"]


def test_no_judge_and_no_candidates_mean_nothing_judged() -> None:
    assert _verdicts(Judging(), [_candidate("a")]) is None
    book, _ = _judging(max_calls=40)
    assert _verdicts(book, []) is None
    assert book.calls == 0
