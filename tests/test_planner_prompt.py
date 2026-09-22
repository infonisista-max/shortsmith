"""planner.prompt: one builder renders a PlanRequest into the fixed sections (2.3:
spec numbers, spec prose, brief, style note, references, transcript; brief before
transcript) after the versioned instruction file, appends the JSON schema generated
from the model the parser validates (8.1), and on a retry the previous output and the
violation list (8.2). The recorded rendering is a snapshot under
`tests/fixtures/planner/`; set SHORTSMITH_UPDATE_SNAPSHOTS=1 to re-record it after a
deliberate prompt change (and bump the prompt version when the change is real)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from shortsmith import fixture
from shortsmith.contracts import (
    Constraints,
    PicturePlan,
    PlanFeedback,
    PlanReference,
    PlanRequest,
    PlanStyle,
    SoundStory,
)
from shortsmith.planner import FakePlanner, prompt
from shortsmith.transcriber import FakeTranscriber

SNAPSHOTS = Path(__file__).parent / "fixtures" / "planner"
SECTIONS = [
    "## 1. Style numbers",
    "## 2. Style prose",
    "## 3. Brief",
    "## 4. Style note",
    "## 5. References",
    "## 6. Transcript",
]


def _request() -> PlanRequest:
    """A fixed request that does not move when a real spec is edited."""
    return PlanRequest(
        brief="Topic: nothing. Must-say: twelve words. Hook wish: a number.",
        style=PlanStyle(
            name="explainer",
            numbers={
                "beats": {"min_s": 0.7, "max_s": 6.0},
                "presenter": {"full_reasons": ["cold_open", "emotional_line", "argument_turn"]},
                "broll": {"kinds": ["photo", "card", "stamp", "map"], "tier2_kinds": []},
            },
            prose="## Beat grammar\n- Beats 2-6 s.",
        ),
        style_note="explainer, energetic, in Hindi",
        transcript=FakeTranscriber().transcribe(Path("unused.mp4")),
        references=[
            PlanReference(id="ref1", kind="image", caption="my product", width=1200, height=1600),
            PlanReference(id="ref2", kind="clip_frame", caption="", width=1080, height=1920),
        ],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )


def _positions(text: str, needles: list[str]) -> list[int]:
    return [text.index(n) for n in needles]


def test_the_six_sections_render_in_the_fixed_order_brief_before_transcript() -> None:
    text = prompt.build_prompt(_request(), "picture")
    positions = _positions(text, SECTIONS)
    assert positions == sorted(positions)
    assert text.index("Must-say: twelve words") < text.index("## 6. Transcript")
    assert "explainer, energetic, in Hindi" in text
    assert "\n#### Beat grammar\n- Beats 2-6 s." in text  # nested under section 2


def test_references_are_a_captioned_list_never_pixels() -> None:
    text = prompt.build_prompt(_request(), "picture")
    assert "- ref1 (image, 1200x1600): my product" in text
    assert "- ref2 (clip_frame, 1080x1920): (no caption)" in text
    empty = _request().model_copy(update={"references": []})
    assert "(no references)" in prompt.build_prompt(empty, "picture")


def test_the_transcript_lists_every_word_with_its_index_and_times() -> None:
    request = _request()
    text = prompt.build_prompt(request, "picture")
    for i, word in enumerate(request.transcript.words):
        assert f"[{i}] {word.start:.2f}-{word.end:.2f} {word.text}" in text


@pytest.mark.parametrize(("call", "model"), [("picture", PicturePlan), ("sound", SoundStory)])
def test_the_schema_generated_from_the_model_is_appended(
    call: str, model: type[PicturePlan] | type[SoundStory]
) -> None:
    request = _request()
    picture = FakePlanner().plan_picture(request)
    text = prompt.build_prompt(request, call, picture=picture)  # pyright: ignore[reportArgumentType]
    schema = json.dumps(model.model_json_schema(), indent=2)
    assert schema in text
    assert text.index("## 6. Transcript") < text.index(schema)
    assert text.rstrip().endswith(prompt.REPLY_JSON_ONLY)


def test_the_picture_prompt_lists_the_tiers_from_the_spec() -> None:
    """4.1 / 9.2: tier 1 is the spec's `broll.kinds`; tier 2 is refused on a style
    whose `tier2_kinds` is empty, and the prompt says so."""
    text = prompt.build_prompt(_request(), "picture")
    assert "Tier 1 (allowed): photo, card, stamp, map" in text
    assert "Tier 2 (not allowed on this style): parallax, vector_illustration" in text
    assert "cold_open, emotional_line, argument_turn" in text


def test_a_style_with_tier2_kinds_lists_them_as_allowed() -> None:
    request = _request()
    numbers = {**request.style.numbers, "broll": {"kinds": ["photo"], "tier2_kinds": ["parallax"]}}
    style = request.style.model_copy(update={"numbers": numbers})
    text = prompt.build_prompt(request.model_copy(update={"style": style}), "picture")
    assert "Tier 2 (allowed): parallax" in text
    assert "Tier 2 (not allowed on this style): vector_illustration" in text


def test_the_picture_prompt_carries_the_planning_rules() -> None:
    """2.3 brief-fact stamping, 5.1 source_intent, 3.4 original_position, 6.1
    name_runs and keywords are asked for in words, not only by the schema."""
    text = prompt.build_prompt(_request(), "picture")
    for needle in (
        "stamp",
        "source_intent",
        "hook.original_position",
        "name_runs",
        "keywords",
        "must use",
    ):
        assert needle in text, needle


def test_the_sound_prompt_carries_the_snapped_picture_and_the_catalogue_tags() -> None:
    """8.1: the sound call gets the validated, snapped picture plan and the tags."""
    request = _request()
    picture = FakePlanner().plan_picture(request)
    text = prompt.build_prompt(
        request, "sound", picture=picture, catalogue_tags=["suspense", "money", "reveal_drop"]
    )
    assert picture.model_dump_json(indent=2) in text
    assert "suspense, money, reveal_drop" in text
    none = prompt.build_prompt(request, "sound", picture=picture)
    assert "(no catalogue yet" in none


def test_the_sound_prompt_needs_the_picture_plan() -> None:
    with pytest.raises(ValueError, match="picture"):
        prompt.build_prompt(_request(), "sound")


def test_a_retry_appends_the_previous_output_and_the_violations() -> None:
    feedback = PlanFeedback(previous='{"beats": []}', violations=["b03 (4.1): no motion"])
    text = prompt.build_prompt(_request(), "picture", feedback=feedback)
    first = prompt.build_prompt(_request(), "picture")
    assert text.startswith(first.rstrip().removesuffix(prompt.REPLY_JSON_ONLY).rstrip())
    assert '{"beats": []}' in text
    assert "- b03 (4.1): no motion" in text
    assert text.rstrip().endswith(prompt.REPLY_JSON_ONLY)


def test_the_prompt_files_are_versioned() -> None:
    assert (prompt.PROMPTS_DIR / f"picture_{prompt.PROMPT_VERSION}.md").is_file()
    assert (prompt.PROMPTS_DIR / f"sound_{prompt.PROMPT_VERSION}.md").is_file()
    assert f"Prompt version: {prompt.PROMPT_VERSION}" in prompt.build_prompt(_request(), "picture")


@pytest.mark.parametrize("call", ["picture", "sound"])
def test_the_rendering_matches_the_recorded_snapshot(call: str) -> None:
    request = _request()
    picture = FakePlanner().plan_picture(request)
    text = prompt.build_prompt(
        request, call, picture=picture, catalogue_tags=["suspense", "money"]  # pyright: ignore[reportArgumentType]
    )
    path = SNAPSHOTS / f"{call}_{prompt.PROMPT_VERSION}.snapshot.md"
    if os.environ.get("SHORTSMITH_UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.is_file(), f"no recorded rendering at {path}; record it deliberately"
    assert text == path.read_text(encoding="utf-8")
