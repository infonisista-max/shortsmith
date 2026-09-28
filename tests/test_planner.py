"""planner: interface plus co-located FakePlanner returning a canned PicturePlan and
SoundStory shaped for the 6 s fixture (decisions 8.1, 12.1). The canned plan tiles
0-6 s with no gaps, opens with two `pip` beats over images (055: the speaker's first
words, nothing lifted), has one `full` beat, and names every tier-1 kind (4.1 as
amended by 9.2) at least once - kinds the renderer cannot draw yet are still valid
plan data."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import fixture, jobs, planner
from shortsmith.config import Settings
from shortsmith.contracts import (
    TIER1_KINDS,
    Constraints,
    PicturePlan,
    PlanReference,
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


def test_the_opening_is_two_pip_beats_over_images_and_nothing_is_lifted(
    request_: PlanRequest,
) -> None:
    """3.4 as amended by 055 and 057 (4): the first two beats are `pip` over two `photo`
    beats with assets (full-screen whenever the image allows; the smoke's second image
    is a landscape, so code draws it as a card), the plan has no hook object, and the
    cut keeps the whole recording in order (nothing lifted, nothing dropped)."""
    plan = FakePlanner().plan_picture(request_)
    first, second = plan.beats[0], plan.beats[1]
    assert (first.mode, first.kind, first.asset_id) == ("pip", "photo", "a1")
    assert (second.mode, second.kind, second.asset_id) == ("pip", "photo", "a2")
    assert second.event.kind == "lower_third"  # drawn on the card strip when downgraded
    assert first.reason is None and not hasattr(plan, "hook")
    assert [(s.start, s.end) for s in plan.cut.keep] == [(0.0, fixture.DURATION_S)]
    assert plan.cut.drop == []
    assert "hook_cards" not in {b.kind for b in plan.beats}


def test_the_first_opening_beat_shows_the_owners_reference_when_there_is_one(
    request_: PlanRequest,
) -> None:
    """055: the owner's reference image comes first in the opening."""
    with_ref = request_.model_copy(update={"references": [
        PlanReference(id="ref1", kind="image", caption="my product", width=1200, height=1600),
    ]})  # fmt: skip
    plan = FakePlanner().plan_picture(with_ref)
    assert plan.beats[0].asset_id == "ref1"
    assert FakePlanner().plan_picture(request_).beats[0].asset_id == "a1"


def test_the_one_full_beat_carries_a_reason_that_is_not_cold_open(request_: PlanRequest) -> None:
    plan = FakePlanner().plan_picture(request_)
    full = [b for b in plan.beats if b.mode == "full"]
    assert [(b.id, b.kind, b.reason) for b in full] == [("b03", "presenter_full", "emotional_line")]


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
        if beat.kind in ("presenter_full", "finale"):
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


def test_fake_enters_are_the_explainer_five_when_the_style_carries_no_numbers(
    request_: PlanRequest,
) -> None:
    """The canned enters (030, 055): whip, fade, fade, spring, zoom on b02, b03, b05,
    b08, b09."""
    plan = FakePlanner().plan_picture(request_)
    enters = {b.id: b.enter for b in plan.beats}
    assert (enters["b02"], enters["b03"], enters["b05"]) == ("whip", "fade", "fade")
    assert (enters["b08"], enters["b09"]) == ("spring", "zoom")
    assert {enters[b] for b in ("b01", "b04", "b06", "b07", "b10", "b11")} == {"cut"}


def test_fake_enters_stay_inside_the_requested_style_and_cover_it(
    request_: PlanRequest,
) -> None:
    """048 (9.4): under the `hitech` draft (cut, fade, wipe, zoom) the fake swaps the
    whip for a wipe and the spring for a zoom, so the plan uses every enabled
    transition at least once and nothing outside the list; the rest is unchanged."""
    from shortsmith import render, styles

    hitech = styles.load_all(render.registry())["hitech"]
    styled = request_.model_copy(
        update={
            "style": PlanStyle(
                name="hitech", status="draft", numbers=hitech.numbers(), prose=hitech.prose
            )
        }
    )
    plan = FakePlanner().plan_picture(styled)
    enters = {b.id: b.enter for b in plan.beats}
    enabled = set(hitech.broll.enter_transitions)
    assert set(enters.values()) == enabled == {"cut", "fade", "wipe", "zoom"}
    assert (enters["b02"], enters["b08"]) == ("wipe", "zoom")
    plain = FakePlanner().plan_picture(request_)
    assert [b.model_copy(update={"enter": "cut"}) for b in plan.beats] == [
        b.model_copy(update={"enter": "cut"}) for b in plain.beats
    ]


def test_under_a_style_that_flashes_the_fake_flashes_back_to_the_presenter_with_a_whoosh(
    request_: PlanRequest,
) -> None:
    """060: b03 (the one `full` beat, the turn back to the presenter) enters with
    `flash` where the style enables it, and the sound story carries one `whoosh` at its
    start where the style allows whooshes; under explainer b03 fades and nothing
    whooshes. The pair passes the grammar under the fixture-shaped copy of that style."""
    from shortsmith import grammar, render, styles
    from shortsmith.contracts import Cue, ValidatedPlan
    from tests.conftest import flash_whoosh_style

    flashy = flash_whoosh_style(styles.load_all(render.registry())["explainer"])
    styled = request_.model_copy(
        update={
            "style": PlanStyle(
                name="explainer", status="shipped", numbers=flashy.numbers(), prose=flashy.prose
            )
        }
    )
    plan = FakePlanner().plan_picture(styled)
    assert [b.id for b in plan.beats if b.enter == "flash"] == ["b03"]
    story = FakePlanner().plan_sound(styled, plan)
    assert [c for c in story.cues if c.intent == "whoosh"] == [
        Cue(beat_id="b03", intent="whoosh", at="start")
    ]
    plain = FakePlanner().plan_picture(request_)
    assert {b.id: b.enter for b in plain.beats}["b03"] == "fade"
    assert not [c for c in FakePlanner().plan_sound(request_, plain).cues if c.intent == "whoosh"]
    judged = fixture.smoke_specs({"explainer": flashy})["explainer"]
    result = grammar.validate(plan, story, request_.transcript, judged)
    assert isinstance(result, ValidatedPlan), getattr(result, "items", result)


def test_under_a_style_with_text_pops_on_the_fake_pops_one_word_on_the_full_beat(
    request_: PlanRequest,
) -> None:
    """061: where the style's `broll.text_pops_max_per_60s` is over 0, b03 (the presenter
    full beat, 1.0-1.5 s) carries one text pop, "THIS", landing on word 2 ("this" at
    1.2 s), and the sound story cues a `popup_tick` at its event; under explainer (cap
    0) no beat carries a pop and no such cue exists. The pair passes the grammar under
    the fixture-shaped copy of the pops style, which writes the pop's `at_s`."""
    from shortsmith import grammar, render, styles
    from shortsmith.contracts import Cue, ValidatedPlan
    from tests.conftest import text_pop_style

    popped = text_pop_style(styles.load_all(render.registry())["explainer"])
    styled = request_.model_copy(
        update={
            "style": PlanStyle(
                name="explainer", status="shipped", numbers=popped.numbers(), prose=popped.prose
            )
        }
    )
    plan = FakePlanner().plan_picture(styled)
    with_pops = {b.id: b.text_pops for b in plan.beats if b.text_pops}
    assert list(with_pops) == ["b03"]
    (pop,) = with_pops["b03"]
    assert (pop.text, pop.word, pop.at_s) == ("THIS", 2, None)
    assert request_.transcript.words[2].text == "this"
    story = FakePlanner().plan_sound(styled, plan)
    assert Cue(beat_id="b03", intent="popup_tick", at="event") in story.cues
    plain = FakePlanner().plan_picture(request_)
    assert all(not b.text_pops for b in plain.beats)
    assert all(c.beat_id != "b03" for c in FakePlanner().plan_sound(request_, plain).cues)
    judged = fixture.smoke_specs({"explainer": popped})["explainer"]
    result = grammar.validate(plan, story, request_.transcript, judged)
    assert isinstance(result, ValidatedPlan), getattr(result, "items", result)
    landed = next(b for b in result.picture.beats if b.id == "b03").text_pops[0]
    assert landed.at_s == request_.transcript.words[2].start == 1.2


def test_under_a_style_with_bubbles_on_the_fake_puts_a_dialogue_pair_on_the_card_beat(
    request_: PlanRequest,
) -> None:
    """063: where the style's `broll.bubbles_max_per_60s` is over 0, b04 (the card beat,
    1.5-2.0 s) carries a dialogue pair - a speech bubble of words 0-1 ("hello there")
    pointing at the PIP circle and a thought bubble of words 2-3 ("this is") over the
    card - and the sound story cues nothing extra (the stamp is the beat's event);
    under explainer (cap 0) no beat carries a bubble. The pair passes the grammar under
    the fixture-shaped copy of the bubbles style, which writes both landings."""
    from shortsmith import grammar, render, styles
    from shortsmith.contracts import ValidatedPlan
    from tests.conftest import bubble_style

    bubbled = bubble_style(styles.load_all(render.registry())["explainer"])
    styled = request_.model_copy(
        update={
            "style": PlanStyle(
                name="explainer", status="shipped", numbers=bubbled.numbers(), prose=bubbled.prose
            )
        }
    )
    plan = FakePlanner().plan_picture(styled)
    with_bubbles = {b.id: b.bubbles for b in plan.beats if b.bubbles}
    assert list(with_bubbles) == ["b04"]
    speech, thought = with_bubbles["b04"]
    assert (speech.shape, speech.first, speech.last, speech.at_s) == ("speech", 0, 1, None)
    assert (thought.shape, thought.first, thought.last, thought.at_s) == ("thought", 2, 3, None)
    words = [w.text for w in request_.transcript.words]
    assert words[0:2] == ["hello", "there"] and words[2:4] == ["this", "is"]
    assert speech.text.lower().split()[0].strip("?!.,") == "hello"
    story = FakePlanner().plan_sound(styled, plan)
    plain = FakePlanner().plan_picture(request_)
    assert story.cues == FakePlanner().plan_sound(request_, plain).cues
    assert all(not b.bubbles for b in plain.beats)
    judged = fixture.smoke_specs({"explainer": bubbled})["explainer"]
    result = grammar.validate(plan, story, request_.transcript, judged)
    assert isinstance(result, ValidatedPlan), getattr(result, "items", result)
    landed = next(b for b in result.picture.beats if b.id == "b04").bubbles
    assert [b.at_s for b in landed] == [1.5, 1.5 + fixture.SMOKE_BUBBLE["dialogue_gap_min_s"]]


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
