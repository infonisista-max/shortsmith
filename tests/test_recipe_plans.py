"""The fake plan under the three recipe styles of ticket 059: it passes each style's
fixture-shaped grammar with zero violations and shows the recipe - a flash and a clip in
`footage`, text pops, a bubble pair and a sticker in `vishva`, the title strip in
`fastfacts` - and it is unchanged under the explainer."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import fixture, grammar, render, smoke, styles
from shortsmith.contracts import Constraints, PicturePlan, PlanRequest, PlanStyle, SoundStory
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber

SPECS = styles.load_all(render.registry())
TRANSCRIPT = FakeTranscriber().transcribe(Path("unused.mp4"))


def _request(name: str) -> PlanRequest:
    return PlanRequest(
        brief=smoke.SMOKE_BRIEF,
        style=PlanStyle(name=name, numbers=SPECS[name].numbers()),
        style_note=name,
        transcript=TRANSCRIPT,
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )


def _planned(name: str) -> tuple[PicturePlan, SoundStory]:
    fake = FakePlanner()
    request = _request(name)
    plan = fake.plan_picture(request)
    return plan, fake.plan_sound(request, plan)


@pytest.mark.parametrize("name", ["footage", "vishva", "fastfacts"])
def test_the_fake_plan_passes_each_recipes_fixture_rules(name: str) -> None:
    plan, story = _planned(name)
    judged = smoke.judged_specs(SPECS, name)[name]
    result = grammar.validate(plan, story, TRANSCRIPT, judged, brief=smoke.SMOKE_BRIEF)
    assert isinstance(result, grammar.ValidatedPlan), [str(v) for v in getattr(result, "items", [])]
    flashed = [b.id for b in plan.beats if b.enter == "flash"]
    assert flashed == ["b03"]
    assert any(c.intent == "whoosh" and c.beat_id == "b03" for c in result.sound.cues)


def test_footage_flashes_and_draws_a_clip() -> None:
    plan, _ = _planned("footage")
    assert [b.id for b in plan.beats if b.kind == "clip"] == ["b04"]
    assert any(b.text_pops for b in plan.beats) and any(b.stickers for b in plan.beats)
    assert not any(b.bubbles for b in plan.beats)
    assert plan.title_strip == ""


def test_vishva_carries_pops_a_bubble_pair_and_a_sticker() -> None:
    plan, _ = _planned("vishva")
    assert any(b.text_pops for b in plan.beats)
    assert sum(len(b.bubbles) for b in plan.beats) == 2
    assert sum(len(b.stickers) for b in plan.beats) == 1
    assert any(b.kind == "split" for b in plan.beats)


def test_fastfacts_writes_the_title_strip_in_at_most_five_words() -> None:
    plan, _ = _planned("fastfacts")
    row = SPECS["fastfacts"].broll.title_strip
    assert row is not None
    assert 1 <= len(plan.title_strip.split()) <= row.words_max
    beats = plan.beats
    assert sum(b.end - b.start for b in beats) / len(beats) <= 1.5


def test_the_explainer_plan_is_unchanged_by_the_recipes() -> None:
    plan, story = _planned("explainer")
    assert plan.title_strip == ""
    assert not any(b.text_pops or b.bubbles or b.stickers for b in plan.beats)
    assert "flash" not in {b.enter for b in plan.beats}
    assert not any(c.intent == "whoosh" for c in story.cues)
