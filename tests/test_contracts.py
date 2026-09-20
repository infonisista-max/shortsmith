"""Global contracts: Transcript with words and per-segment logprob flags, plus the
planner-facing PlanRequest, PicturePlan, SoundStory and CaptionPage, all extra="forbid"
so the JSON schema generated from them is the one source of truth (2.3, 8.1)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from shortsmith import contracts
from shortsmith.contracts import (
    TIER1_KINDS,
    TIER2_KINDS,
    Beat,
    CaptionPage,
    PicturePlan,
    PlanRequest,
    Segment,
    SoundStory,
    Span,
    Transcript,
    Word,
)
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber

ENGINE_TERMS = re.compile(r"remotion|ffmpeg|filter", re.IGNORECASE)


def _transcript() -> Transcript:
    return Transcript(
        language="en",
        duration_s=6.0,
        segments=[Segment(start=0.2, end=0.5, avg_logprob=-0.1, low_confidence=False)],
        words=[Word(text="hello", start=0.2, end=0.35, segment=0)],
    )


def test_transcript_round_trips_through_json() -> None:
    t = _transcript()
    assert Transcript.model_validate_json(t.model_dump_json()) == t


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        Word.model_validate({"text": "x", "start": 0.0, "end": 0.1, "segment": 0, "score": 1})
    with pytest.raises(ValidationError):
        Transcript.model_validate({**_transcript().model_dump(), "engine": "whisper"})


def test_word_end_must_not_precede_start() -> None:
    with pytest.raises(ValidationError):
        Word(text="x", start=1.0, end=0.9, segment=0)


def test_segment_flags_default_off() -> None:
    seg = Segment(start=0.0, end=1.0, avg_logprob=-0.2)
    assert (seg.low_confidence, seg.no_speech) == (False, False)


# --- planner-facing models (ticket 003) ------------------------------------------


def _request() -> PlanRequest:
    transcript = FakeTranscriber().transcribe(Path("unused.mp4"))
    return PlanRequest(
        brief="Topic: nothing. Angle: prove the pipeline. Must-say: twelve words.",
        style=contracts.PlanStyle(name="explainer", prose="## Beat grammar\n- Beats 2-6 s."),
        style_note="explainer",
        transcript=transcript,
        references=[
            contracts.PlanReference(
                id="ref1", kind="image", caption="my product", width=1200, height=1600
            )
        ],
        constraints=contracts.Constraints(max_duration_s=60.0, target_duration_s=6.0),
        asset_policy="any",
    )


def test_plan_request_round_trips_and_forbids_extras() -> None:
    req = _request()
    assert PlanRequest.model_validate_json(req.model_dump_json()) == req
    with pytest.raises(ValidationError):
        PlanRequest.model_validate({**req.model_dump(), "pixels": []})


def test_picture_plan_and_sound_story_forbid_extras() -> None:
    plan = FakePlanner().plan_picture(_request())
    assert PicturePlan.model_validate_json(plan.model_dump_json()) == plan
    with pytest.raises(ValidationError):
        PicturePlan.model_validate({**plan.model_dump(), "composition": "Short"})
    with pytest.raises(ValidationError):
        Beat.model_validate({**plan.beats[0].model_dump(), "filter": "scale"})
    story = FakePlanner().plan_sound(_request(), plan)
    assert SoundStory.model_validate_json(story.model_dump_json()) == story
    with pytest.raises(ValidationError):
        SoundStory.model_validate({**story.model_dump(), "track": "x.mp3"})


def test_picture_plan_schema_is_generatable_and_engine_agnostic() -> None:
    """8.1: the schema embedded in the prompt is generated from the model and carries
    no Remotion or ffmpeg terms."""
    for model in (PicturePlan, SoundStory):
        schema = model.model_json_schema()
        text = json.dumps(schema)
        assert schema["additionalProperties"] is False
        assert not ENGINE_TERMS.search(text), ENGINE_TERMS.search(text)
    plan = FakePlanner().plan_picture(_request())
    assert not ENGINE_TERMS.search(plan.model_dump_json())


def test_tier_lists_are_disjoint_and_complete() -> None:
    """4.1 as amended by 9.2: every listed kind is tier 1; only parallax and vector
    illustration are tier 2."""
    assert set(TIER1_KINDS) == {
        "photo", "card", "stamp", "lower_third", "hook_cards", "finale",
        "presenter_full", "presenter_pip", "list", "chart", "split", "wall", "map",
        "infographic", "pin_drop", "route_arrow", "label_flyin", "counter", "object_path",
    }  # fmt: skip
    assert set(TIER2_KINDS) == {"parallax", "vector_illustration"}
    assert not set(TIER1_KINDS) & set(TIER2_KINDS)


def test_span_and_beat_reject_backwards_times() -> None:
    with pytest.raises(ValidationError):
        Span(start=1.0, end=0.5)
    beat = FakePlanner().plan_picture(_request()).beats[2]
    with pytest.raises(ValidationError):
        Beat.model_validate({**beat.model_dump(), "end": beat.start - 0.1})


def test_full_beat_needs_a_reason_tag_and_others_must_not_carry_one() -> None:
    """3.2: every `full` beat carries one reason tag from the fixed set; the validator
    (009) rejects the rest, but the model already refuses a tag outside the set."""
    plan = FakePlanner().plan_picture(_request())
    full = next(b for b in plan.beats if b.mode == "full")
    with pytest.raises(ValidationError):
        Beat.model_validate({**full.model_dump(), "reason": "looked_nice"})


def test_caption_page_round_trips() -> None:
    page = CaptionPage(
        index=0, word_indices=[0, 1, 2], texts=["hello", "there", "this"],
        start=0.16, end=1.32, keyword=1,
    )  # fmt: skip
    assert CaptionPage.model_validate_json(page.model_dump_json()) == page
    with pytest.raises(ValidationError):
        CaptionPage.model_validate({**page.model_dump(), "font": "Poppins"})
