"""grammar: the plan validator (ticket 009; decisions 3.1, 3.2, 3.4, 4.1, 4.2, 4.3,
7.3, 8.2, 9.4). Pure code over PicturePlan / SoundStory, Transcript and StyleSpec:
clamps what 8.2 lets code fix (each logged), rejects the rest with beat id and rule
number on every message, and warns where 3.4 / 4.3 say warn. Every number comes from
the explainer front matter loaded from disk; the boundary pairs sit on both sides of
each threshold the decisions name."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from shortsmith import fixture, grammar, render, smoke, styles
from shortsmith.contracts import (
    CATEGORIES,
    Beat,
    BedQuery,
    Constraints,
    CounterPlan,
    Cue,
    CutPlan,
    Event,
    Finale,
    Hook,
    MapMarker,
    MapPlan,
    Mode,
    MoodPoint,
    PicturePlan,
    PlanLabel,
    PlanReference,
    PlanRequest,
    PlanStyle,
    Segment,
    SeriesPoint,
    SetPieceItem,
    SoundStory,
    Span,
    Transcript,
    Word,
)
from shortsmith.planner import FakePlanner
from shortsmith.styles import StyleSpec
from shortsmith.transcriber import FakeTranscriber

BRIEF = "Topic: why the sky is blue. Angle: scattering in one breath. Hook wish: none."
WORD_LEN_S = 0.3
# 027: turning a body beat into a set piece means giving it the content a set piece
# carries, so the length and mean tests below still pass the item rules.
AS_LIST: dict[str, Any] = {
    "kind": "list",
    "motion": "reveal",
    "set_piece_title": "Three things",
    "items": [SetPieceItem(text="one"), SetPieceItem(text="two")],
}


@pytest.fixture(scope="module")
def spec() -> StyleSpec:
    return styles.load_all(render.registry())["explainer"]


# --- plan builders --------------------------------------------------------------------
#
# A plan that passes every explainer rule: a 1.5 s `full` cold open, 3.0 s `off` hook
# cards, twenty 2.5 s body beats (pip x4, off x2 repeating; photo / card alternating,
# each with a stamp so nothing on screen sits still past 1.5 s; twelve assets cycling
# so some are reused) and a 1.0 s `off` finale. 55.5 s in all, mean 2.41 s.

BODY_MODES: tuple[Mode, ...] = ("pip", "pip", "pip", "pip", "off", "off")
_MODE_LETTERS: dict[str, Mode] = {"p": "pip", "o": "off", "f": "full"}


def modes(pattern: str) -> list[Mode]:
    """'pppp oo' -> [pip, pip, pip, pip, off, off]; spaces are ignored."""
    return [_MODE_LETTERS[c] for c in pattern if c != " "]


def body_beat(n: int, start: float, length: float, *, mode: Mode, asset: str) -> Beat:
    photo = n % 2 == 0
    return Beat(
        id=f"b{n + 3:02d}",
        start=round(start, 3),
        end=round(start + length, 3),
        mode=mode,
        kind="photo" if photo else "card",
        motion="ken_burns_in" if photo else "push_in",
        subject_kind="concept" if photo else "entity",
        depicts="scene" if photo else None,
        query=f"query {n}",
        query_fallback=f"fallback {n}",
        source_intent="search",
        asset_id=asset,
        event=Event(kind="stamp", text=f"S{n}"),
    )


def make_plan(
    *,
    cold_open_s: float = 1.5,
    hook_cards_s: float = 3.0,
    finale_s: float = 1.0,
    body_lengths: Sequence[float] = (2.5,) * 20,
    body_modes: Sequence[Mode] | None = None,
    assets: int = 12,
    title: str = "Why the sky is blue",
    keywords: Sequence[int] = (),
    hashtags: Sequence[str] = ("#shorts", "#sky"),
) -> PicturePlan:
    body: list[Mode] = (
        list(body_modes)
        if body_modes is not None
        else [BODY_MODES[i % len(BODY_MODES)] for i in range(len(body_lengths))]
    )
    beats = [
        Beat(id="b01", start=0.0, end=cold_open_s, mode="full", reason="cold_open",
             kind="presenter_full"),
        Beat(id="b02", start=cold_open_s, end=round(cold_open_s + hook_cards_s, 3), mode="off",
             kind="hook_cards", asset_id="a01"),
    ]  # fmt: skip
    t = beats[-1].end
    for n, (length, mode) in enumerate(zip(body_lengths, body, strict=True)):
        beats.append(body_beat(n, t, length, mode=mode, asset=f"a{n % assets + 1:02d}"))
        t = beats[-1].end
    finale_id = f"b{len(beats) + 1:02d}"
    beats.append(
        Beat(id=finale_id, start=t, end=round(t + finale_s, 3), mode="off", kind="finale",
             asset_id="a01")
    )  # fmt: skip
    return PicturePlan(
        prompt_version="test-1",
        cut=CutPlan(keep=[Span(start=0.0, end=beats[-1].end)]),
        beats=beats,
        hook=Hook(
            title=title,
            cold_open_span=Span(start=0.0, end=cold_open_s),
            original_position="drop",
            card_asset_ids=["a01", "a02", "a03"],
        ),
        finale=Finale(beat_id=finale_id, text="That is why."),
        keywords=list(keywords),
        title="Why the sky is blue",
        description="One breath on scattering.",
        hashtags=list(hashtags),
    )


def transcript_for(plan: PicturePlan, *extra_ends: float) -> Transcript:
    """A word ending exactly at every beat boundary (and at `extra_ends`), so nothing
    snaps unless a test moves a boundary off a word end."""
    ends = sorted({round(b.end, 3) for b in plan.beats} | {round(e, 3) for e in extra_ends})
    words = [
        Word(text=f"w{i}", start=round(end - WORD_LEN_S, 3), end=end, segment=i // 3)
        for i, end in enumerate(ends)
    ]
    duration = max(plan.beats[-1].end, ends[-1])
    segments = [
        Segment(start=words[i].start, end=words[min(i + 2, len(words) - 1)].end, avg_logprob=-0.1)
        for i in range(0, len(words), 3)
    ]
    return Transcript(language="en", duration_s=duration, segments=segments, words=words)


def replace(plan: PicturePlan, beat_id: str, **changes: Any) -> PicturePlan:
    beats = [b.model_copy(update=changes) if b.id == beat_id else b for b in plan.beats]
    return plan.model_copy(update={"beats": beats})


def move_boundary(plan: PicturePlan, index: int, t: float) -> PicturePlan:
    """Move the boundary between beats[index] and beats[index + 1] to `t`."""
    beats = list(plan.beats)
    beats[index] = beats[index].model_copy(update={"end": t})
    beats[index + 1] = beats[index + 1].model_copy(update={"start": t})
    return plan.model_copy(update={"beats": beats})


def story_for(
    plan: PicturePlan, *, cues: Sequence[Cue] = (), curve: Sequence[MoodPoint] = ()
) -> SoundStory:
    end = plan.beats[-1].end
    return SoundStory(
        prompt_version="test-1",
        theme="curious",
        mood_curve=list(curve) or [MoodPoint(t=0.0, level=0.0), MoodPoint(t=end, level=0.0)],
        bed_query=BedQuery(theme="science", mood="curious", energy=3),
        cues=list(cues),
    )


def rules(result: object) -> set[tuple[str | None, str]]:
    assert isinstance(result, grammar.Violations), result
    return {(v.beat_id, v.rule) for v in result.items}


def picture(
    plan: PicturePlan, spec: StyleSpec, *, transcript: Transcript | None = None,
    brief: str = BRIEF, must_use: Sequence[str] = (),
) -> grammar.PictureCheck | grammar.Violations:  # fmt: skip
    return grammar.validate_picture(
        plan, transcript or transcript_for(plan), spec, brief=brief, must_use=must_use
    )


def checked(plan: PicturePlan, spec: StyleSpec, **kwargs: Any) -> grammar.PictureCheck:
    result = picture(plan, spec, **kwargs)
    assert isinstance(result, grammar.PictureCheck), [str(v) for v in getattr(result, "items", [])]
    return result


# --- the base plan and the clamps (8.2) ------------------------------------------------


def test_the_base_plan_passes_with_no_clamps_and_no_warnings(spec: StyleSpec) -> None:
    result = checked(make_plan(), spec)
    assert result.clamps == [] and result.warnings == []
    assert result.picture == make_plan()


def test_boundary_within_the_snap_window_snaps_to_the_word_end(spec: StyleSpec) -> None:
    """8.2 / 3.1: 0.14 s off a word end snaps; 0.16 s off stays (it is in silence)."""
    base = make_plan()
    shifted = move_boundary(base, 4, base.beats[4].end + 0.14)
    transcript = transcript_for(base)  # word ends where the base boundary was
    result = checked(shifted, spec, transcript=transcript)
    assert result.picture.beats[4].end == base.beats[4].end
    assert result.picture.beats[5].start == base.beats[4].end
    assert len(result.clamps) == 1
    clamp = result.clamps[0]
    assert clamp.rule == "3.1" and clamp.beat_id == "b06" and "0.14" in clamp.message

    kept = move_boundary(base, 4, base.beats[4].end + 0.16)
    result = checked(kept, spec, transcript=transcript)
    assert result.picture.beats[4].end == kept.beats[4].end
    assert result.clamps == []


def test_a_boundary_inside_a_word_beyond_the_window_is_rejected(spec: StyleSpec) -> None:
    """3.1: never a cut mid-word; a boundary 0.2 s before a word end cannot snap."""
    base = make_plan()
    transcript = transcript_for(base)
    inside = move_boundary(base, 4, base.beats[4].end - 0.2)  # words are 0.3 s long
    result = picture(inside, spec, transcript=transcript)
    assert ("b06", "3.1") in rules(result)
    assert any("mid-word" in v.message for v in result.items)  # type: ignore[union-attr]


def test_keywords_are_trimmed_to_the_emphasis_ratio(spec: StyleSpec) -> None:
    """8.2 / 6.1: at most `emphasis_max_ratio` of the words keep their priority order."""
    plan = make_plan(keywords=list(range(12)))
    transcript = transcript_for(plan)  # 23 words -> floor(23 x 0.25) = 5 keywords
    result = checked(plan, spec, transcript=transcript)
    assert result.picture.keywords == [0, 1, 2, 3, 4]
    assert [c.rule for c in result.clamps] == ["6.1"]
    assert result.clamps[0].message.startswith("keywords:")


def test_hashtags_and_title_are_clamped(spec: StyleSpec) -> None:
    plan = make_plan(hashtags=[f"#t{i}" for i in range(7)])
    plan = plan.model_copy(update={"title": "x" * 120})
    result = checked(plan, spec)
    assert result.picture.hashtags == [f"#t{i}" for i in range(5)]
    assert len(result.picture.title) == 100
    assert sorted(c.message.split(":")[0] for c in result.clamps) == ["hashtags", "title"]


# --- beat lengths, mean, density (3.1) ---------------------------------------------------


def test_beat_at_and_below_min_s(spec: StyleSpec) -> None:
    lengths = [2.5] * 20
    lengths[2] = 0.7
    assert isinstance(picture(make_plan(body_lengths=lengths), spec), grammar.PictureCheck)
    lengths[2] = 0.69
    result = picture(make_plan(body_lengths=lengths), spec)
    assert ("b05", "3.1") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("0.69" in v.message and "0.7" in v.message for v in result.items)


def test_set_pieces_get_the_set_piece_maximum_and_others_max_s(spec: StyleSpec) -> None:
    lengths = [2.5] * 20
    lengths[2] = 6.1
    plan = make_plan(body_lengths=lengths)
    assert ("b05", "3.1") in rules(picture(plan, spec))
    as_list = replace(plan, "b05", **AS_LIST)
    assert isinstance(picture(as_list, spec), grammar.PictureCheck)
    lengths[2] = 8.1
    too_long = replace(make_plan(body_lengths=lengths), "b05", **AS_LIST)
    assert ("b05", "3.1") in rules(picture(too_long, spec))


@pytest.mark.parametrize(
    ("mean", "ok"), [(1.99, False), (2.0, True), (3.2, True), (3.21, False)]
)
def test_plan_mean_boundaries(spec: StyleSpec, mean: float, ok: bool) -> None:
    """The body beats are lists (set pieces), so their length is free of the density
    gap and only the mean decides."""
    body = 20
    total = mean * (body + 3)
    length = round((total - 1.5 - 3.0 - 1.0) / body, 4)
    plan = make_plan(body_lengths=[length] * body, assets=15)  # 73.6 s needs 14 assets
    for b in plan.beats[2:-1]:
        plan = replace(plan, b.id, event=Event(), **AS_LIST)
    if ok:
        checked(plan, spec)
    else:
        assert (None, "3.1") in rules(picture(plan, spec))


def test_a_beat_with_nothing_changing_for_over_the_density_gap_is_rejected(
    spec: StyleSpec,
) -> None:
    """3.1: visual events are beat starts and landed events; a 2.5 s photo with no
    event leaves 2.5 s still, a 1.5 s one is exactly at the gap."""
    still = replace(make_plan(), "b05", event=Event())
    assert ("b05", "3.1") in rules(picture(still, spec))
    lengths = [2.5] * 20
    lengths[2] = 1.5
    short_still = replace(make_plan(body_lengths=lengths), "b05", event=Event())
    checked(short_still, spec)
    lengths[2] = 1.6
    long_still = replace(make_plan(body_lengths=lengths), "b05", event=Event())
    assert ("b05", "3.1") in rules(picture(long_still, spec))


def test_gaps_and_overlaps_between_beats_are_rejected(spec: StyleSpec) -> None:
    plan = make_plan()
    beats = list(plan.beats)
    beats[5] = beats[5].model_copy(update={"start": beats[5].start + 0.2})
    gappy = plan.model_copy(update={"beats": beats})
    assert ("b06", "3.1") in rules(picture(gappy, spec, transcript=transcript_for(plan)))


# --- presenter modes (3.2) ---------------------------------------------------------------


def test_full_beat_without_a_reason_is_rejected(spec: StyleSpec) -> None:
    plan = replace(make_plan(), "b05", mode="full", kind="presenter_full", reason=None,
                   motion=None, subject_kind=None, query="", asset_id=None)  # fmt: skip
    assert ("b05", "3.2") in rules(picture(plan, spec))


def test_consecutive_full_beats_are_rejected(spec: StyleSpec) -> None:
    plan = make_plan()
    for bid in ("b05", "b06"):
        plan = replace(plan, bid, mode="full", kind="presenter_full", reason="argument_turn",
                       motion=None, subject_kind=None, query="", asset_id=None)  # fmt: skip
    assert ("b06", "3.2") in rules(picture(plan, spec))


def test_full_fraction_exactly_at_the_cap_passes_and_above_fails(spec: StyleSpec) -> None:
    """64 s plan, 2.0 s cold open + seven 2.0 s full beats = 16 s = 0.25 exactly."""
    body = [2.0] * 29
    full_at = [0, 4, 8, 12, 16, 20, 24]
    pattern = modes("".join("f" if i in full_at else "p" for i in range(29)))
    plan = make_plan(cold_open_s=2.0, body_lengths=body, body_modes=pattern, assets=16)
    for i in full_at:
        plan = replace(plan, f"b{i + 3:02d}", kind="presenter_full", reason="emotional_line",
                       motion=None, subject_kind=None, query="", asset_id=None)  # fmt: skip
    # pip runs of three between full beats, off nowhere: the modes stay legal.
    checked(plan, spec)
    over = replace(plan, "b30", mode="full", kind="presenter_full", reason="emotional_line",
                   motion=None, subject_kind=None, query="", asset_id=None)  # fmt: skip
    assert (None, "3.2") in rules(picture(over, spec))


def test_seventh_consecutive_pip_is_rejected(spec: StyleSpec) -> None:
    six = modes("pppppp o pppppp o pppppp")
    checked(make_plan(body_lengths=[2.5] * 20, body_modes=six), spec)
    seven = modes("ppppppp o pppppp o ppppp")
    result = picture(make_plan(body_lengths=[2.5] * 20, body_modes=seven), spec)
    assert ("b09", "3.2") in rules(result)  # the seventh pip beat is b09


def test_fourth_consecutive_off_is_rejected(spec: StyleSpec) -> None:
    three = modes("p ooo ppppo ppppo ppppo p")
    checked(make_plan(body_lengths=[2.5] * 20, body_modes=three), spec)
    four = modes("p oooo ppppo ppppo ppppo")
    plan = make_plan(body_lengths=[2.5] * 20, body_modes=four)
    assert ("b07", "3.2") in rules(picture(plan, spec))


def test_hook_beat_in_pip_and_finale_not_off_are_rejected(spec: StyleSpec) -> None:
    plan = make_plan()
    pip_hook = replace(plan, "b01", mode="pip", kind="presenter_pip", reason=None)
    assert ("b01", "3.2") in rules(picture(pip_hook, spec))
    pip_finale = replace(plan, "b23", mode="pip")
    assert ("b23", "3.2") in rules(picture(pip_finale, spec))


# --- the hook (3.4) ----------------------------------------------------------------------


def test_hook_title_word_count(spec: StyleSpec) -> None:
    checked(make_plan(title="one two three four five six seven eight"), spec)
    result = picture(make_plan(title="one two three four five six seven eight nine"), spec)
    assert ("b02", "3.4") in rules(result)


@pytest.mark.parametrize(
    ("cold_open", "hook_cards"), [(0.6, 3.0), (2.1, 3.0), (1.5, 1.9), (1.5, 4.1)]
)
def test_hook_slot_lengths_are_enforced(
    spec: StyleSpec, cold_open: float, hook_cards: float
) -> None:
    result = picture(make_plan(cold_open_s=cold_open, hook_cards_s=hook_cards), spec)
    assert ("b01", "3.4") in rules(result) or ("b02", "3.4") in rules(result)


def with_hook(plan: PicturePlan, **changes: Any) -> PicturePlan:
    return plan.model_copy(update={"hook": plan.hook.model_copy(update=changes)})


def test_hook_cards_must_name_plan_assets(spec: StyleSpec) -> None:
    plan = with_hook(make_plan(), card_asset_ids=["a01", "zz"])
    assert ("b02", "3.4") in rules(picture(plan, spec))


def test_lifted_span_must_sit_on_word_boundaries(spec: StyleSpec) -> None:
    """A cold open lifted from 20.0-21.5 s and kept in place: the cut keeps 54 s of
    the body so the 55.5 s of beats still tile the output (3.1)."""
    base = make_plan()
    transcript = transcript_for(base, 20.0, 21.5)
    lifted = with_hook(
        base.model_copy(update={"cut": CutPlan(keep=[Span(start=0.0, end=54.0)])}),
        cold_open_span=Span(start=20.0, end=21.5),
        original_position="keep",
    )
    checked(lifted, spec, transcript=transcript)
    # 21.4 s is inside the word ending at 21.5 s.
    mid_word = with_hook(lifted, cold_open_span=Span(start=20.0, end=21.4))
    assert ("b01", "3.4") in rules(picture(mid_word, spec, transcript=transcript))


def test_duplicated_cold_open_span_needs_an_explicit_keep(spec: StyleSpec) -> None:
    """3.4: the cut list removes the lifted span from the body under `drop`, so the
    line repeats only under an explicit `keep`; a plan that says `keep` but planned
    its beats as if the span played once is caught by the runtime (3.1) with the
    repeat named, and `keep` on a span the cut drops is a contradiction (3.4)."""
    base = make_plan()
    transcript = transcript_for(base, 20.0, 21.5)
    span = Span(start=20.0, end=21.5)
    lifted = with_hook(base, cold_open_span=span, original_position="drop")
    checked(lifted, spec, transcript=transcript)  # 1.5 s lifted + 54 s of body = 55.5 s
    forgot = with_hook(lifted, original_position="keep")
    result = picture(forgot, spec, transcript=transcript)
    assert (None, "3.1") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("plays twice" in v.message and "keep" in v.message for v in result.items)
    cut = CutPlan(keep=[Span(start=0.0, end=55.5)], drop=[span])
    contradiction = forgot.model_copy(update={"cut": cut})
    assert ("b01", "3.4") in rules(picture(contradiction, spec, transcript=transcript))


def test_beats_must_tile_the_cut_runtime(spec: StyleSpec) -> None:
    """3.1: a plan whose beats end before (or after) the cut list's runtime is rejected."""
    base = make_plan()
    short_cut = base.model_copy(update={"cut": CutPlan(keep=[Span(start=0.0, end=50.0)])})
    assert (None, "3.1") in rules(picture(short_cut, spec))


# --- kinds, motion, subjects (4.1, 4.2) --------------------------------------------------


def test_tier_two_kind_is_rejected_naming_the_substitute(spec: StyleSpec) -> None:
    result = picture(replace(make_plan(), "b05", kind="parallax"), spec)
    assert ("b05", "4.1") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("parallax" in v.message and "photo" in v.message for v in result.items)
    result = picture(replace(make_plan(), "b05", kind="vector_illustration"), spec)
    assert isinstance(result, grammar.Violations)
    assert any("card" in v.message for v in result.items)


def test_a_kind_outside_the_style_list_is_rejected(spec: StyleSpec) -> None:
    narrow = spec.model_copy(deep=True)
    narrow.broll.kinds = [k for k in spec.broll.kinds if k != "card"]
    assert ("b04", "4.1") in rules(picture(make_plan(), narrow))


def test_non_presenter_beat_without_a_motion_is_rejected(spec: StyleSpec) -> None:
    assert ("b05", "4.1") in rules(picture(replace(make_plan(), "b05", motion=None), spec))
    # hook cards and the finale carry their fixed motion from the spec; presenter beats none.
    checked(make_plan(), spec)


def test_non_presenter_beat_needs_subject_kind_and_query(spec: StyleSpec) -> None:
    assert ("b05", "4.2") in rules(picture(replace(make_plan(), "b05", subject_kind=None), spec))
    assert ("b05", "4.2") in rules(picture(replace(make_plan(), "b05", query=""), spec))


def test_entity_beat_per_sixty_seconds_when_the_brief_names_something(spec: StyleSpec) -> None:
    plan = make_plan()
    no_entities = plan
    for b in plan.beats:
        if b.subject_kind == "entity":
            no_entities = replace(no_entities, b.id, subject_kind="concept")
    named = "Topic: how Rayleigh explained the sky. Angle: one breath."
    assert (None, "4.2") in rules(picture(no_entities, spec, brief=named))
    checked(no_entities, spec, brief="Topic: why the sky is blue. Angle: one breath.")
    checked(plan, spec, brief=named)


# --- set-piece items (ticket 027; decisions 4.1, 5.2) ------------------------------------


def _items(n: int, *, asset: str | None = "a01") -> list[SetPieceItem]:
    return [SetPieceItem(text=f"item {i}", asset_id=asset) for i in range(n)]


def _piece(
    plan: PicturePlan, beat_id: str, kind: str, items: Sequence[SetPieceItem]
) -> PicturePlan:
    return replace(
        plan, beat_id, kind=kind, motion="reveal", set_piece_title="One two", items=list(items)
    )


def test_a_list_split_or_wall_beat_passes_with_the_items_the_style_allows(
    spec: StyleSpec,
) -> None:
    plan = _piece(make_plan(), "b05", "list", _items(6))
    checked(plan, spec)
    checked(_piece(make_plan(), "b05", "split", _items(2)), spec)
    checked(_piece(make_plan(), "b05", "wall", _items(9)), spec)


def test_items_on_a_kind_that_is_not_a_set_piece_are_rejected(spec: StyleSpec) -> None:
    plan = replace(make_plan(), "b05", items=_items(2))
    assert ("b05", "4.1") in rules(picture(plan, spec))


def test_item_counts_outside_the_style_numbers_are_rejected(spec: StyleSpec) -> None:
    assert ("b05", "4.1") in rules(picture(_piece(make_plan(), "b05", "list", _items(7)), spec))
    assert ("b05", "4.1") in rules(picture(_piece(make_plan(), "b05", "list", []), spec))
    assert ("b05", "4.1") in rules(picture(_piece(make_plan(), "b05", "split", _items(3)), spec))
    assert ("b05", "4.1") in rules(picture(_piece(make_plan(), "b05", "wall", _items(3)), spec))
    assert ("b05", "4.1") in rules(picture(_piece(make_plan(), "b05", "wall", _items(10)), spec))


def test_a_split_or_wall_item_without_an_asset_is_rejected(spec: StyleSpec) -> None:
    plan = _piece(make_plan(), "b05", "split", _items(2, asset=None))
    assert ("b05", "5.2") in rules(picture(plan, spec))
    # a list row may be text only
    checked(_piece(make_plan(), "b05", "list", _items(3, asset=None)), spec)


def test_an_item_asset_id_that_is_not_a_plan_asset_is_rejected(spec: StyleSpec) -> None:
    plan = _piece(make_plan(), "b05", "wall", _items(4, asset="nope"))
    assert ("b05", "4.3") in rules(picture(plan, spec))


def test_a_set_piece_title_on_an_ordinary_beat_is_rejected(spec: StyleSpec) -> None:
    assert ("b05", "4.1") in rules(picture(replace(make_plan(), "b05", set_piece_title="x"), spec))


def test_a_list_or_split_without_a_title_is_rejected(spec: StyleSpec) -> None:
    plan = replace(
        make_plan(), "b05", kind="split", motion="reveal", set_piece_title="", items=_items(2)
    )
    assert ("b05", "4.1") in rules(picture(plan, spec))


def test_set_piece_items_are_not_asset_showings(spec: StyleSpec) -> None:
    """4.3: like the hook's cards, an item is a montage member, never a showing, so it
    neither adds a unique asset nor spends the asset's `reuse_max`."""
    plan = _piece(make_plan(assets=12), "b05", "wall", _items(9, asset="a01"))
    checked(plan, spec)


# --- charts and labelled diagrams (ticket 021; decisions 9.2, 9.3) -----------------------


def _points(n: int, *, value: float = 1.0) -> list[SeriesPoint]:
    return [SeriesPoint(label=f"p{i}", value=value + i) for i in range(n)]


def _chart(
    plan: PicturePlan, beat_id: str, form: str, points: Sequence[SeriesPoint]
) -> PicturePlan:
    return replace(
        plan, beat_id, kind="chart", motion="count_up", subject_kind="number",
        chart_form=form, series=list(points), set_piece_title="Where it went",
    )  # fmt: skip


def _diagram(plan: PicturePlan, beat_id: str, labels: Sequence[PlanLabel]) -> PicturePlan:
    return replace(
        plan, beat_id, kind="infographic", motion="fly_in", subject_kind="concept",
        labels=list(labels),
    )  # fmt: skip


def _labels(n: int) -> list[PlanLabel]:
    return [PlanLabel(text=f"L{i}", x=40.0, y=30.0 + i, anchor="center") for i in range(n)]


def test_a_chart_and_a_diagram_beat_pass_with_the_data_the_style_allows(
    spec: StyleSpec,
) -> None:
    checked(_chart(make_plan(), "b05", "bar", _points(6)), spec)
    checked(_chart(make_plan(), "b05", "comparison", _points(2)), spec)
    checked(_diagram(make_plan(), "b05", _labels(5)), spec)


def test_a_chart_beat_without_a_form_or_a_series_is_rejected(spec: StyleSpec) -> None:
    bare = replace(make_plan(), "b05", kind="chart", motion="count_up")
    assert ("b05", "9.2") in rules(picture(bare, spec))
    formless = replace(
        make_plan(), "b05", kind="chart", motion="count_up", series=_points(3)
    )
    assert ("b05", "9.2") in rules(picture(formless, spec))


def test_series_counts_outside_the_style_numbers_are_rejected(spec: StyleSpec) -> None:
    assert ("b05", "9.2") in rules(picture(_chart(make_plan(), "b05", "bar", _points(7)), spec))
    assert ("b05", "9.2") in rules(picture(_chart(make_plan(), "b05", "line", _points(1)), spec))
    assert (
        ("b05", "9.2") in rules(picture(_chart(make_plan(), "b05", "comparison", _points(3)), spec))
    )


def test_a_negative_or_unlabelled_series_value_is_rejected(spec: StyleSpec) -> None:
    negative = [SeriesPoint(label="a", value=4.0), SeriesPoint(label="b", value=-2.0)]
    assert ("b05", "9.2") in rules(picture(_chart(make_plan(), "b05", "bar", negative), spec))
    bare = [SeriesPoint(label="", value=4.0), SeriesPoint(label="b", value=2.0)]
    assert ("b05", "9.2") in rules(picture(_chart(make_plan(), "b05", "bar", bare), spec))


def test_chart_data_on_a_beat_that_is_not_a_chart_is_rejected(spec: StyleSpec) -> None:
    plan = replace(make_plan(), "b05", series=_points(2))
    assert ("b05", "9.2") in rules(picture(plan, spec))
    plan = replace(make_plan(), "b05", chart_form="bar")
    assert ("b05", "9.2") in rules(picture(plan, spec))
    plan = replace(make_plan(), "b05", value_unit="crore")
    assert ("b05", "9.2") in rules(picture(plan, spec))


def test_a_chart_may_carry_the_title_strip_an_ordinary_beat_may_not(spec: StyleSpec) -> None:
    checked(_chart(make_plan(), "b05", "bar", _points(2)), spec)
    assert ("b05", "4.1") in rules(picture(replace(make_plan(), "b05", set_piece_title="x"), spec))


def test_labels_on_a_beat_that_is_not_an_infographic_are_rejected(spec: StyleSpec) -> None:
    assert ("b05", "9.3") in rules(picture(replace(make_plan(), "b05", labels=_labels(2)), spec))


def test_an_infographic_needs_one_to_labels_max_labels_each_with_text(spec: StyleSpec) -> None:
    assert ("b05", "9.3") in rules(picture(_diagram(make_plan(), "b05", []), spec))
    assert ("b05", "9.3") in rules(picture(_diagram(make_plan(), "b05", _labels(6)), spec))
    blank = [PlanLabel(text="  ", x=40.0, y=40.0)]
    assert ("b05", "9.3") in rules(picture(_diagram(make_plan(), "b05", blank), spec))


# --- label fly-ins and counters (ticket 029; decisions 3.1, 4.2, 9.2, 9.3) ----------------


def _counter(plan: PicturePlan, beat_id: str, **updates: Any) -> PicturePlan:
    fields: dict[str, Any] = {
        "overlays": ["counter"], "subject_kind": "number", "event": Event(),
        "counter": CounterPlan(start=0, target=1250000, unit="crore"),
    }  # fmt: skip
    return replace(plan, beat_id, **{**fields, **updates})


def test_a_counter_on_a_number_beat_or_a_chart_passes(spec: StyleSpec) -> None:
    checked(_counter(make_plan(), "b05"), spec)
    on_chart = _chart(make_plan(), "b05", "bar", _points(3))
    checked(_counter(on_chart, "b05"), spec)
    checked(replace(_diagram(make_plan(), "b05", _labels(3)), "b05", overlays=["label_flyin"]),
            spec)  # fmt: skip


def test_a_counter_overlay_needs_its_numbers_and_the_numbers_need_the_overlay(
    spec: StyleSpec,
) -> None:
    assert ("b05", "9.2") in rules(picture(_counter(make_plan(), "b05", counter=None), spec))
    assert ("b05", "9.2") in rules(picture(_counter(make_plan(), "b05", overlays=[]), spec))
    same = CounterPlan(start=40, target=40)
    assert ("b05", "9.2") in rules(picture(_counter(make_plan(), "b05", counter=same), spec))


def test_the_counter_is_the_beats_one_landed_event(spec: StyleSpec) -> None:
    stamped = _counter(make_plan(), "b05", event=Event(kind="stamp", text="12 LAKH"))
    assert ("b05", "3.1") in rules(picture(stamped, spec))


def test_a_counter_counts_as_a_number_beat(spec: StyleSpec) -> None:
    concept = _counter(make_plan(), "b05", subject_kind="concept")
    assert ("b05", "4.2") in rules(picture(concept, spec))


def test_a_cue_may_sit_on_a_counters_landing(spec: StyleSpec) -> None:
    """9.4: the counter is a landed event, so an `event` cue has something to hit."""
    plan = _counter(make_plan(), "b05")
    ok = cued(plan, spec, Cue(beat_id="b05", intent="money", at="event"))
    assert isinstance(ok, grammar.SoundCheck)


def test_label_flyin_rides_only_on_an_infographic(spec: StyleSpec) -> None:
    plan = replace(make_plan(), "b05", overlays=["label_flyin"])
    assert ("b05", "9.3") in rules(picture(plan, spec))


# --- assets (4.3) ------------------------------------------------------------------------


def test_unique_asset_count_scales_with_runtime(spec: StyleSpec) -> None:
    """55.5 s: 12/60 s -> 11 needed, 24/60 s -> 23 allowed."""
    checked(make_plan(assets=11), spec)
    assert (None, "4.3") in rules(picture(make_plan(assets=10), spec))
    # 61.2 s of 2.0 s beats: 24/60 s -> 25 allowed; 27 fresh assets is a slideshow's
    # opposite, a blur (4.3).
    def tight(assets: int) -> PicturePlan:
        return make_plan(
            cold_open_s=2.0, hook_cards_s=4.0, finale_s=1.2, body_lengths=[2.0] * 27,
            assets=assets,
        )  # fmt: skip

    checked(tight(25), spec)
    assert (None, "4.3") in rules(picture(tight(27), spec))


def test_reuse_over_reuse_max_is_rejected(spec: StyleSpec) -> None:
    """4.3: `reuse_max` beats per asset; hook cards are a montage of plan assets and
    do not count as showings."""
    plan = make_plan(assets=12)
    four = replace(plan, "b04", asset_id="a01")  # a01: b03, b04, b15, finale
    checked(four, spec)
    five = replace(four, "b05", asset_id="a01")
    result = picture(five, spec)
    assert (None, "4.3") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("a01" in v.message for v in result.items)


def test_no_reuse_is_a_warning_not_a_rejection(spec: StyleSpec) -> None:
    plan = make_plan(body_lengths=[2.5] * 18, assets=18)
    plan = replace(plan, "b21", asset_id="a19")  # the finale had a01 too
    result = checked(plan, spec)
    assert any("4.3" in w and "reused" in w for w in result.warnings)


# --- transitions (9.4) -------------------------------------------------------------------


def test_transition_outside_the_style_list_is_rejected(spec: StyleSpec) -> None:
    assert ("b05", "9.4") in rules(picture(replace(make_plan(), "b05", enter="wipe"), spec))
    checked(replace(make_plan(), "b05", enter="zoom"), spec)


def test_whip_spacing(spec: StyleSpec) -> None:
    plan = replace(replace(make_plan(), "b05", enter="whip"), "b08", enter="whip")
    checked(plan, spec)  # three beats apart
    close = replace(replace(make_plan(), "b05", enter="whip"), "b07", enter="whip")
    assert ("b07", "9.4") in rules(picture(close, spec))
    in_a_row = replace(replace(make_plan(), "b05", enter="whip"), "b06", enter="whip")
    assert ("b06", "9.4") in rules(picture(in_a_row, spec))


# --- must-use references (2.3) -----------------------------------------------------------


def test_must_use_reference_ids_must_appear_in_the_plan(spec: StyleSpec) -> None:
    plan = make_plan()
    assert (None, "2.3") in rules(picture(plan, spec, must_use=["ref1"]))
    checked(replace(plan, "b05", asset_id="ref1"), spec, must_use=["ref1"])


def test_must_use_ids_are_read_from_the_brief() -> None:
    refs = [
        PlanReference(id="ref1", kind="image", caption="the chart", width=10, height=10),
        PlanReference(id="ref2", kind="image", caption="my face", width=10, height=10),
    ]
    brief = "Topic: x. References: the chart (must use). Angle: y."
    assert grammar.must_use_ids(brief, refs) == ["ref1"]
    assert grammar.must_use_ids("Topic: x. Must-use ref2.", refs) == ["ref2"]
    assert grammar.must_use_ids("Topic: x.", refs) == []


def test_title_ignoring_a_numeric_hook_wish_is_a_warning(spec: StyleSpec) -> None:
    brief = "Topic: sky. Hook wish: 3 reasons the sky is blue."
    result = checked(make_plan(title="Why the sky is blue"), spec, brief=brief)
    assert any("3.4" in w and "hook wish" in w for w in result.warnings)
    result = checked(make_plan(title="3 reasons the sky is blue"), spec, brief=brief)
    assert result.warnings == []


# --- the sound story (7.3, 8.2, 9.4) -----------------------------------------------------


def sound(
    story: SoundStory, plan: PicturePlan, spec: StyleSpec
) -> grammar.SoundCheck | grammar.Violations:
    return grammar.validate_sound(story, plan, spec)


def cued(plan: PicturePlan, spec: StyleSpec, *cues: Cue) -> grammar.SoundCheck | grammar.Violations:
    return sound(story_for(plan, cues=cues), plan, spec)


def test_cue_on_a_non_existent_beat_is_rejected(spec: StyleSpec) -> None:
    result = cued(make_plan(), spec, Cue(beat_id="b99", intent="hit", at="start"))
    assert ("b99", "8.2") in rules(result)


def test_cue_at_a_transition_or_a_missing_event_is_rejected(spec: StyleSpec) -> None:
    plan = make_plan()
    bare = replace(replace(plan, "b05", event=Event()), "b05", enter="whip")
    assert ("b05", "9.4") in rules(cued(bare, spec, Cue(beat_id="b05", intent="tick", at="event")))
    assert ("b05", "9.4") in rules(cued(bare, spec, Cue(beat_id="b05", intent="tick", at="start")))
    landed = replace(plan, "b05", enter="whip")  # keeps its stamp
    ok = cued(landed, spec, Cue(beat_id="b05", intent="tick", at="start"))
    assert isinstance(ok, grammar.SoundCheck)


def test_mood_curve_is_clipped_to_the_envelope(spec: StyleSpec) -> None:
    plan = make_plan()
    end = plan.beats[-1].end
    curve = [
        MoodPoint(t=0.0, level=6.0),
        MoodPoint(t=10.0, level=-12.0),
        MoodPoint(t=end, level=0.0),
    ]
    result = sound(story_for(plan, curve=curve), plan, spec)
    assert isinstance(result, grammar.SoundCheck)
    assert [p.level for p in result.sound.mood_curve] == [4.0, -8.0, 0.0]
    assert [c.rule for c in result.clamps] == ["7.3", "7.3"]


def test_ramp_under_the_minimum_is_rejected_but_a_drop_at_a_beat_boundary_is_a_step(
    spec: StyleSpec,
) -> None:
    plan = make_plan()
    end = plan.beats[-1].end
    fast = [MoodPoint(t=0.0, level=0.0), MoodPoint(t=1.4, level=3.0), MoodPoint(t=end, level=0.0)]
    result = sound(story_for(plan, curve=fast), plan, spec)
    assert (None, "7.3") in rules(result)
    slow = [MoodPoint(t=0.0, level=0.0), MoodPoint(t=1.5, level=3.0), MoodPoint(t=end, level=0.0)]
    assert isinstance(sound(story_for(plan, curve=slow), plan, spec), grammar.SoundCheck)
    boundary = plan.beats[4].end
    drop = [MoodPoint(t=0.0, level=2.0), MoodPoint(t=boundary - 0.01, level=2.0),
            MoodPoint(t=boundary, level=-6.0), MoodPoint(t=end, level=-6.0)]  # fmt: skip
    assert isinstance(sound(story_for(plan, curve=drop), plan, spec), grammar.SoundCheck)
    off_boundary = [
        MoodPoint(t=0.0, level=2.0),
        MoodPoint(t=boundary + 0.5, level=2.0),
        MoodPoint(t=boundary + 0.51, level=-6.0),
        MoodPoint(t=end, level=-6.0),
    ]
    assert (None, "7.3") in rules(sound(story_for(plan, curve=off_boundary), plan, spec))


def test_twenty_first_cue_is_dropped_and_one_cue_per_beat(spec: StyleSpec) -> None:
    """7.3: 20 cues per 60 s; the 55.5 s plan allows 18 (floor). The extras are
    planner cues dropped from the end, each a logged clamp."""
    plan = make_plan(body_lengths=[2.5] * 22)  # 60.5 s -> 20 cues
    ids = [b.id for b in plan.beats if b.event.kind == "stamp"]  # 22 body beats
    cues = [Cue(beat_id=i, intent="tick", at="event") for i in ids[:21]]
    result = sound(story_for(plan, cues=cues), plan, spec)
    assert isinstance(result, grammar.SoundCheck)
    assert len(result.sound.cues) == 20
    assert [c.beat_id for c in result.clamps] == [ids[20]]
    assert result.clamps[0].rule == "7.3"
    tick = Cue(beat_id=ids[0], intent="tick", at="event")
    ring = Cue(beat_id=ids[0], intent="ring", at="start")
    result = cued(plan, spec, tick, ring)
    assert isinstance(result, grammar.SoundCheck)
    assert [c.intent for c in result.sound.cues] == ["tick"]
    assert result.clamps[0].beat_id == ids[0] and result.clamps[0].rule == "7.3"


def test_mood_points_outside_the_runtime_are_rejected(spec: StyleSpec) -> None:
    plan = make_plan()
    curve = [MoodPoint(t=0.0, level=0.0), MoodPoint(t=plan.beats[-1].end + 5, level=0.0)]
    assert (None, "7.3") in rules(sound(story_for(plan, curve=curve), plan, spec))


# --- validate(): both halves, the fixture spec and the fake plan --------------------------


def test_validate_combines_picture_and_sound(spec: StyleSpec) -> None:
    plan = make_plan(keywords=list(range(12)))
    story = story_for(plan, cues=[Cue(beat_id="b05", intent="tick", at="event")])
    result = grammar.validate(plan, story, transcript_for(plan), spec, brief=BRIEF)
    assert isinstance(result, grammar.ValidatedPlan)
    assert result.picture.keywords == [0, 1, 2, 3, 4]
    assert result.sound == story
    assert [c.rule for c in result.clamps] == ["6.1"]
    ghost = story_for(plan, cues=[Cue(beat_id="b99", intent="x", at="start")])
    bad = grammar.validate(
        replace(plan, "b05", motion=None), ghost, transcript_for(plan), spec, brief=BRIEF
    )
    assert rules(bad) == {("b05", "4.1"), ("b99", "8.2")}


def test_violations_render_with_beat_id_and_rule(spec: StyleSpec) -> None:
    result = picture(replace(make_plan(), "b05", motion=None), spec)
    assert isinstance(result, grammar.Violations)
    (line,) = result.lines()
    assert line.startswith("b05 (4.1): ")


def test_the_fake_plan_passes_the_fixture_rules_with_zero_violations() -> None:
    """The fixture-shaped rule set (copy of explainer with the beat, asset and ramp
    numbers scaled to six seconds; everything else untouched) accepts the canned plan.
    Against the real explainer numbers the same plan is rejected, which is the point
    of keeping the override explicit and outside the pipeline."""
    specs = fixture.smoke_specs(styles.load_all(render.registry()))
    transcript = FakeTranscriber().transcribe(Path("unused.mp4"))
    request = PlanRequest(
        brief=smoke.SMOKE_BRIEF,
        style=PlanStyle(name="explainer"),
        style_note="explainer",
        transcript=transcript,
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )
    fake = FakePlanner()
    plan = fake.plan_picture(request)
    story = fake.plan_sound(request, plan)
    result = grammar.validate(plan, story, transcript, specs["explainer"], brief=request.brief)
    assert isinstance(result, grammar.ValidatedPlan), [str(v) for v in getattr(result, "items", [])]
    assert result.picture.beats == plan.beats  # every boundary already on a word end or in silence
    assert [c.message.split(":")[0] for c in result.clamps] == ["keywords"]
    explainer = styles.load_all(render.registry())["explainer"]
    real = grammar.validate(plan, story, transcript, explainer)
    assert isinstance(real, grammar.Violations)
    # The fixture spec changes only the numbers the six-second clip cannot meet.
    scaled = specs["explainer"]
    assert scaled.captions == explainer.captions and scaled.pip == explainer.pip
    assert scaled.finale == explainer.finale and scaled.palette == explainer.palette
    assert scaled.name == "explainer" and scaled.status == "shipped"
    assert specs["hitech"] is not None


# --- maps (ticket 020; decisions 9.2, 9.3) ---------------------------------------------------


def _map(plan: PicturePlan, beat_id: str, **updates: Any) -> PicturePlan:
    fields: dict[str, Any] = {
        "kind": "map", "motion": "travel", "subject_kind": "entity", "asset_id": None,
        "map": MapPlan(region="India", markers=[MapMarker(name="Delhi"), MapMarker(name="Mumbai")]),
    }  # fmt: skip
    return replace(plan, beat_id, **{**fields, **updates})


def test_a_map_beat_passes_with_a_region_and_markers_and_needs_no_asset(spec: StyleSpec) -> None:
    checked(_map(make_plan(), "b05"), spec)
    boxed = MapPlan(bbox=(68.0, 6.0, 98.0, 36.0), markers=[MapMarker(name="Delhi")])
    checked(_map(make_plan(), "b05", map=boxed), spec)
    routed = MapPlan(region="India", markers=[MapMarker(name="Delhi"), MapMarker(name="Mumbai")],
                     route=["Delhi", "Mumbai"], object="plane")  # fmt: skip
    checked(_map(make_plan(), "b05", map=routed,
                 overlays=["pin_drop", "route_arrow", "object_path"]), spec)  # fmt: skip


def test_a_map_beat_without_its_recipe_or_without_a_region_or_bbox_is_rejected(
    spec: StyleSpec,
) -> None:
    assert ("b05", "9.3") in rules(picture(_map(make_plan(), "b05", map=None), spec))
    bare = MapPlan(markers=[MapMarker(name="Delhi")])
    assert ("b05", "9.3") in rules(picture(_map(make_plan(), "b05", map=bare), spec))


def test_a_map_recipe_on_a_beat_that_is_not_a_map_is_rejected(spec: StyleSpec) -> None:
    plan = replace(make_plan(), "b05", map=MapPlan(region="India", markers=[MapMarker(name="x")]))
    assert ("b05", "9.3") in rules(picture(plan, spec))


@pytest.mark.parametrize("bbox", [(98.0, 6.0, 68.0, 36.0), (68.0, 36.0, 98.0, 6.0),
                                  (68.0, 6.0, 190.0, 36.0), (68.0, -90.0, 98.0, 36.0)])  # fmt: skip
def test_a_bbox_must_be_west_south_east_north_on_the_earth(
    spec: StyleSpec, bbox: tuple[float, float, float, float]
) -> None:
    boxed = MapPlan(bbox=bbox, markers=[MapMarker(name="Delhi")])
    assert ("b05", "9.3") in rules(picture(_map(make_plan(), "b05", map=boxed), spec))


def test_marker_counts_come_from_the_style_and_every_marker_has_a_name(spec: StyleSpec) -> None:
    top = int(spec.broll.motion["map"]["markers_max"])
    many = MapPlan(region="India", markers=[MapMarker(name=f"m{i}") for i in range(top + 1)])
    assert ("b05", "9.3") in rules(picture(_map(make_plan(), "b05", map=many), spec))
    enough = MapPlan(region="India", markers=[MapMarker(name=f"m{i}") for i in range(top)])
    checked(_map(make_plan(), "b05", map=enough), spec)
    none = MapPlan(region="India")
    assert ("b05", "9.3") in rules(picture(_map(make_plan(), "b05", map=none), spec))
    blank = MapPlan(region="India", markers=[MapMarker(name="  ")])
    assert ("b05", "9.3") in rules(picture(_map(make_plan(), "b05", map=blank), spec))


def test_a_route_is_two_or_more_named_places(spec: StyleSpec) -> None:
    one = MapPlan(region="India", markers=[MapMarker(name="Delhi")], route=["Delhi"])
    assert ("b05", "9.3") in rules(picture(_map(make_plan(), "b05", map=one), spec))
    blank = MapPlan(region="India", markers=[MapMarker(name="Delhi")], route=["Delhi", " "])
    assert ("b05", "9.3") in rules(picture(_map(make_plan(), "b05", map=blank), spec))


def test_the_map_overlays_ride_on_a_map_with_what_they_animate(spec: StyleSpec) -> None:
    # pin drops, route arrows and moving objects live on a map, nowhere else
    for overlay in ("pin_drop", "route_arrow", "object_path"):
        plan = replace(make_plan(), "b05", overlays=[overlay])
        assert ("b05", "9.3") in rules(picture(plan, spec)), overlay
    # a route arrow and a moving object need a route; the object needs its sprite
    no_route = _map(make_plan(), "b05", overlays=["route_arrow"])
    assert ("b05", "9.3") in rules(picture(no_route, spec))
    routed = MapPlan(region="India", markers=[MapMarker(name="Delhi"), MapMarker(name="Mumbai")],
                     route=["Delhi", "Mumbai"])  # fmt: skip
    checked(_map(make_plan(), "b05", map=routed, overlays=["route_arrow"]), spec)
    no_object = _map(make_plan(), "b05", map=routed, overlays=["object_path"])
    assert ("b05", "9.3") in rules(picture(no_object, spec))


def test_planner_coordinates_on_a_marker_are_carried_not_rejected(spec: StyleSpec) -> None:
    """9.3: the plan may write lat/lon; code ignores them (test in test_infographics)."""
    wrong = MapPlan(region="India", markers=[MapMarker(name="Delhi", lat=0.0, lon=0.0)])
    checked(_map(make_plan(), "b05", map=wrong), spec)


# --- the category (10.3; ticket 033) ------------------------------------------------------


def test_the_category_must_come_from_the_fixed_list(spec: StyleSpec) -> None:
    """10.3: the planner names the short's category from `CATEGORIES`; anything else is
    rejected at plan level with the list in the message, and `other` is allowed."""
    for name in CATEGORIES:
        checked(make_plan().model_copy(update={"category": name}), spec)
    result = picture(make_plan().model_copy(update={"category": "cooking"}), spec)
    assert rules(result) == {(None, "10.3")}
    assert isinstance(result, grammar.Violations)
    (line,) = result.lines()
    assert line.startswith("plan (10.3): category 'cooking' is not one of ")
    assert "history" in line and "other" in line
