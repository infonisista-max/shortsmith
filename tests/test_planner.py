"""planner: interface plus co-located FakePlanner returning a canned PicturePlan and
SoundStory shaped for the 6 s fixture (decisions 8.1, 12.1). The canned plan tiles
0-6 s with no gaps, opens with a `full` cold open, has an `off` hook-cards beat, at
least one `pip` beat, and names every tier-1 kind (4.1 as amended by 9.2) at least
once - kinds the renderer cannot draw yet are still valid plan data."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import fixture, jobs, planner
from shortsmith.config import Settings
from shortsmith.contracts import (
    TIER1_KINDS,
    Constraints,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    SoundStory,
)
from shortsmith.ledger import Caps, Ledger, Prices
from shortsmith.planner import FakePlanner, Planner
from shortsmith.transcriber import FakeTranscriber


@pytest.fixture
def request_() -> PlanRequest:
    return PlanRequest(
        brief="Topic: a six-second synthetic clip. Angle: prove the pipeline end to end.",
        style=PlanStyle(name="explainer", prose="- Beats 2-6 s."),
        style_note="explainer",
        transcript=FakeTranscriber().transcribe(Path("unused.mp4")),
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )


def test_fake_is_a_planner() -> None:
    assert isinstance(FakePlanner(), Planner)


def test_beats_tile_the_fixture_with_no_gaps(request_: PlanRequest) -> None:
    plan = FakePlanner().plan_picture(request_)
    assert plan.beats[0].start == 0.0
    assert plan.beats[-1].end == fixture.DURATION_S
    for a, b in zip(plan.beats, plan.beats[1:], strict=False):
        assert a.end == b.start, (a.id, b.id)
        assert a.end > a.start
    assert len({b.id for b in plan.beats}) == len(plan.beats)


def test_hook_shape_cold_open_then_hook_cards(request_: PlanRequest) -> None:
    """3.4: beat 1 is `full` with the `cold_open` tag, beat 2 is `off` hook cards."""
    plan = FakePlanner().plan_picture(request_)
    first, second = plan.beats[0], plan.beats[1]
    assert (first.mode, first.reason, first.kind) == ("full", "cold_open", "presenter_full")
    assert (second.mode, second.kind) == ("off", "hook_cards")
    assert 1 <= len(plan.hook.title.split()) <= 8
    assert plan.hook.cold_open_span.start == first.start
    assert plan.hook.cold_open_span.end == first.end
    assert plan.hook.original_position in ("keep", "drop")


def test_finale_is_the_last_beat_and_off(request_: PlanRequest) -> None:
    plan = FakePlanner().plan_picture(request_)
    last = plan.beats[-1]
    assert (last.mode, last.kind) == ("off", "finale")
    assert plan.finale.beat_id == last.id


def test_at_least_one_pip_beat_and_full_never_consecutive(request_: PlanRequest) -> None:
    plan = FakePlanner().plan_picture(request_)
    modes = [b.mode for b in plan.beats]
    assert "pip" in modes
    assert all(not (a == b == "full") for a, b in zip(modes, modes[1:], strict=False))


def test_every_tier1_kind_is_named_at_least_once(request_: PlanRequest) -> None:
    plan = FakePlanner().plan_picture(request_)
    named = planner.kinds_named(plan)
    missing = set(TIER1_KINDS) - named
    assert not missing, sorted(missing)


def test_non_presenter_beats_carry_exactly_one_motion_and_a_subject(
    request_: PlanRequest,
) -> None:
    """4.1: one motion per non-presenter beat; 4.2: subject_kind + query on each."""
    plan = FakePlanner().plan_picture(request_)
    for beat in plan.beats:
        if beat.kind in ("presenter_full", "hook_cards", "finale"):
            continue
        assert beat.motion is not None, beat.id
        assert beat.subject_kind is not None and beat.query, beat.id


def test_beat_boundaries_never_land_mid_word(request_: PlanRequest) -> None:
    """3.1: boundaries sit on word ends or in silence, never inside a word."""
    plan = FakePlanner().plan_picture(request_)
    words = request_.transcript.words
    for beat in plan.beats[1:]:
        inside = [w for w in words if w.start < beat.start < w.end]
        assert not inside, (beat.id, inside)


def test_sound_story_cues_point_at_real_beats(request_: PlanRequest) -> None:
    fake = FakePlanner()
    plan = fake.plan_picture(request_)
    story = fake.plan_sound(request_, plan)
    ids = {b.id for b in plan.beats}
    assert story.cues and all(c.beat_id in ids for c in story.cues)
    assert story.bed_query.energy in range(1, 6)
    assert [p.t for p in story.mood_curve] == sorted(p.t for p in story.mood_curve)
    assert story.mood_curve[0].t == 0.0 and story.mood_curve[-1].t <= fixture.DURATION_S


def test_fake_is_deterministic(request_: PlanRequest) -> None:
    a, b = FakePlanner(), FakePlanner()
    assert a.plan_picture(request_) == b.plan_picture(request_)
    plan = a.plan_picture(request_)
    assert a.plan_sound(request_, plan) == b.plan_sound(request_, plan)


def test_plans_carry_the_prompt_version(request_: PlanRequest) -> None:
    plan = FakePlanner().plan_picture(request_)
    assert plan.prompt_version == FakePlanner.PROMPT_VERSION
    assert isinstance(plan, PicturePlan)
    assert isinstance(FakePlanner().plan_sound(request_, plan), SoundStory)


def test_from_settings_selects_the_fake_only_for_planner_fake(
    request_: PlanRequest, tmp_path: Path
) -> None:
    """Selecting a paid planner must never silently fall back to the fake: `api` is
    015's adapter (test_planner_api), `claude_code` 014's (test_planner_claude_code),
    and an `api` planner with no key fails the job at `planning`."""
    book = Ledger(Prices({}), Caps(per_job=None, hard=None, per_day=500))
    settings = Settings(_env_file=None, planner="fake")  # pyright: ignore[reportCallIssue]
    assert isinstance(planner.from_settings(settings, ledger=lambda: book), FakePlanner)
    settings = Settings(_env_file=None, planner="api")  # pyright: ignore[reportCallIssue]
    chosen = planner.from_settings(settings, ledger=lambda: book)
    assert isinstance(chosen, Planner) and not isinstance(chosen, FakePlanner)
    with pytest.raises(planner.PlannerError, match="ANTHROPIC_API_KEY"):
        chosen.bind(jobs.create(tmp_path)).plan_picture(request_)
