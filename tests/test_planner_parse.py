"""planner.parse: the one parser every adapter shares (8.1, 8.2). It finds the JSON
object in the reply (bare, fenced, or wrapped in a sentence), validates it with the
`extra="forbid"` models, and stamps the prompt version the builder used. A reply that
is not a valid plan raises `PlanInvalid` with one line per problem in the grammar's
`<beat id | plan> (<rule>): <message>` shape, so the 009 retry applies to it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shortsmith import fixture
from shortsmith.contracts import Constraints, PicturePlan, PlanRequest, PlanStyle, SoundStory
from shortsmith.planner import FakePlanner, PlanInvalid, parse
from shortsmith.transcriber import FakeTranscriber


def _request() -> PlanRequest:
    return PlanRequest(
        brief="Topic: nothing.",
        style=PlanStyle(name="explainer"),
        style_note="explainer",
        transcript=FakeTranscriber().transcribe(Path("unused.mp4")),
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )


def _picture_json() -> str:
    return FakePlanner().plan_picture(_request()).model_dump_json(indent=2)


@pytest.mark.parametrize(
    "wrap",
    [
        "{}",
        "```json\n{}\n```",
        "```\n{}\n```",
        "Here is the plan:\n\n{}\n\nLet me know if you want changes.",
    ],
)
def test_the_json_object_is_found_however_it_is_wrapped(wrap: str) -> None:
    reply = wrap.replace("{}", _picture_json())
    plan = parse.parse_reply(reply, "picture", prompt_version="v9")
    assert isinstance(plan, PicturePlan)
    assert plan.beats == FakePlanner().plan_picture(_request()).beats


def test_the_prompt_version_is_stamped_by_code_not_trusted_from_the_reply() -> None:
    data = json.loads(_picture_json())
    data["prompt_version"] = "whatever-the-model-said"
    plan = parse.parse_reply(json.dumps(data), "picture", prompt_version="v1")
    assert plan.prompt_version == "v1"
    del data["prompt_version"]
    missing = parse.parse_reply(json.dumps(data), "picture", prompt_version="v1")
    assert missing.prompt_version == "v1"


def test_the_sound_call_parses_into_a_sound_story() -> None:
    request = _request()
    fake = FakePlanner()
    story = fake.plan_sound(request, fake.plan_picture(request))
    parsed = parse.parse_reply(story.model_dump_json(), "sound", prompt_version="v1")
    assert isinstance(parsed, SoundStory)
    assert parsed.cues == story.cues


def test_no_json_in_the_reply_is_plan_invalid() -> None:
    with pytest.raises(PlanInvalid) as caught:
        parse.parse_reply("I could not plan this short, sorry.", "picture", prompt_version="v1")
    assert caught.value.call == "picture"
    assert caught.value.reply == "I could not plan this short, sorry."
    assert caught.value.violations == ["plan (8.2): the reply holds no JSON object"]


def test_broken_json_is_plan_invalid() -> None:
    with pytest.raises(PlanInvalid) as caught:
        parse.parse_reply('{"beats": [1, 2,}', "picture", prompt_version="v1")
    (line,) = caught.value.violations
    assert line.startswith("plan (8.2): the reply is not valid JSON")


def test_a_stray_field_and_a_missing_field_are_each_one_violation_line() -> None:
    """`extra="forbid"`: the schema is the contract, a stray key is an error."""
    data = json.loads(_picture_json())
    data["mood"] = "epic"
    del data["title"]
    data["beats"][2]["motion"] = "spin"
    with pytest.raises(PlanInvalid) as caught:
        parse.parse_reply(json.dumps(data), "picture", prompt_version="v1")
    lines = caught.value.violations
    assert len(lines) == 3
    assert all(line.startswith("plan (8.2): ") for line in lines)
    assert any("mood" in line and "Extra inputs are not permitted" in line for line in lines)
    assert any("title" in line and "Field required" in line for line in lines)
    assert any("beats.2.motion" in line for line in lines)


def test_a_json_array_is_not_a_plan() -> None:
    with pytest.raises(PlanInvalid):
        parse.parse_reply("[1, 2, 3]", "sound", prompt_version="v1")
