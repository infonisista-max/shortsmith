"""grammar: the plan validator (ticket 009; decisions 3.1, 3.2, 3.4 as amended by 055,
4.1, 4.2, 4.3, 7.3, 8.2, 9.4). Pure code over PicturePlan / SoundStory, Transcript and
StyleSpec: clamps what 8.2 lets code fix (each logged), rejects the rest with beat id
and rule number on every message, and warns where 4.3 says warn. Every number comes
from the explainer front matter loaded from disk; the boundary pairs sit on both sides
of each threshold the decisions name.

Ticket 055: the speaker's order (a lifted or dropped line is rejected naming the span,
replayed from F1's plan), pause tightening as a clamp on the F1 transcript, beats
mapped from the recording onto the cut, and the opening (two pip beats over images,
the owner's reference first)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from shortsmith import fixture, grammar, presenter, render, smoke, styles
from shortsmith.contracts import (
    CATEGORIES,
    Beat,
    BedQuery,
    Bubble,
    Constraints,
    CounterPlan,
    Cue,
    CutPlan,
    Event,
    Finale,
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
    Sticker,
    TextPop,
    Transcript,
    Word,
)
from shortsmith.planner import FakePlanner
from shortsmith.styles import StyleSpec
from shortsmith.transcriber import FakeTranscriber
from tests.conftest import bubble_style, flash_whoosh_style, sticker_style, text_pop_style

BRIEF = "Topic: why the sky is blue. Angle: scattering in one breath. Hook wish: none."
# Each beat's one word starts this far into it (the first beat's at its start), so the
# 0.4 s silence between words is under `cut.max_pause_s` (0.6) and a boundary moved
# 0.16 s past a word end still lands in silence.
WORD_LEAD_S = 0.4
F1_TRANSCRIPT = Path(__file__).parent / "fixtures" / "f1" / "transcript.json"
# F1 (job 20260927-041728-656506): the line the old hook lifted from 22.74-24.1 s.
F1_LIFT = Span(start=22.74, end=24.1)
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
# A plan that passes every explainer rule: two 2.5 s `pip` opening beats over a photo
# and a card (055: the speaker's first words over the strongest images, ending exactly
# at `opening_max_s`), twenty 2.5 s body beats (pip x4, off x2 repeating; photo / card
# alternating, each with a stamp so nothing on screen sits still past 1.5 s; twelve
# assets cycling so some are reused) and a 1.0 s `off` finale. 56.0 s in all, mean
# 2.43 s. Beat times are recording seconds; with the whole recording kept they are the
# output's too.

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
    opening_s: float = 2.5,
    finale_s: float = 1.0,
    body_lengths: Sequence[float] = (2.5,) * 20,
    body_modes: Sequence[Mode] | None = None,
    assets: int = 12,
    keywords: Sequence[int] = (),
    hashtags: Sequence[str] = ("#shorts", "#sky"),
) -> PicturePlan:
    body: list[Mode] = (
        list(body_modes)
        if body_modes is not None
        else [BODY_MODES[i % len(BODY_MODES)] for i in range(len(body_lengths))]
    )
    # The opening: b01 a photo, b02 a card (body_beat's alternation from n = -2), both
    # pip, with their own assets so the body's reuse arithmetic is untouched.
    beats = [
        body_beat(-2, 0.0, opening_s, mode="pip", asset="o1"),
        body_beat(-1, opening_s, opening_s, mode="pip", asset="o2"),
    ]
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
        finale=Finale(beat_id=finale_id, text="That is why."),
        keywords=list(keywords),
        title="Why the sky is blue",
        description="One breath on scattering.",
        hashtags=list(hashtags),
    )


def transcript_for(plan: PicturePlan, *, gap_before: dict[str, float] | None = None) -> Transcript:
    """One word per beat, ending exactly at the beat's end and starting `WORD_LEAD_S`
    into it (the first at 0), so nothing snaps unless a test moves a boundary off a
    word end and no pause is over `cut.max_pause_s`. `gap_before` widens the silence
    before a beat's word (beat id -> lead), for the pause-tightening tests."""
    leads = gap_before or {}
    words: list[Word] = []
    for i, b in enumerate(plan.beats):
        lead = 0.0 if i == 0 else leads.get(b.id, WORD_LEAD_S)
        words.append(Word(text=f"w{i}", start=round(b.start + lead, 3), end=b.end, segment=i // 3))
    duration = plan.beats[-1].end
    segments = [
        Segment(start=words[i].start, end=words[min(i + 2, len(words) - 1)].end, avg_logprob=-0.1)
        for i in range(0, len(words), 3)
    ]
    return Transcript(language="en", duration_s=duration, segments=segments, words=words)


def f1_transcript() -> Transcript:
    return Transcript.model_validate_json(F1_TRANSCRIPT.read_text(encoding="utf-8"))


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
    brief: str = BRIEF, must_use: Sequence[str] = (), references: Sequence[str] = (),
    timeline: grammar.Timeline = "recording",
) -> grammar.PictureCheck | grammar.Violations:  # fmt: skip
    return grammar.validate_picture(
        plan, transcript or transcript_for(plan), spec, brief=brief, must_use=must_use,
        references=references, timeline=timeline,
    )  # fmt: skip


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
    length = round((total - 2 * 2.5 - 1.0) / body, 4)  # two opening beats and the finale
    plan = make_plan(body_lengths=[length] * body, assets=15)  # 73.8 s needs 14 assets
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


# --- 066: density counts each change at its own time ---------------------------------------
#
# b05 is a `photo`; with `body_lengths[2]` set it runs from 10.0 s for that long. Its one
# word is replaced by words starting at the given seconds, so a pop, bubble or sticker on
# word 4 + i lands at the i-th start.

RUN04 = Path(__file__).parent / "fixtures" / "run04"


def _words_on_b05(plan: PicturePlan, starts: Sequence[float]) -> Transcript:
    """The base transcript with b05's word replaced by one word per start, each ending
    0.1 s before the next (the last at the beat's end), so no pause is tightened."""
    base = transcript_for(plan)
    b05 = next(b for b in plan.beats if b.id == "b05")
    ends = [*(round(s - 0.1, 3) for s in starts[1:]), b05.end]
    seg = base.words[4].segment
    spoken = [Word(text=f"w4{i}", start=s, end=e, segment=seg)
              for i, (s, e) in enumerate(zip(starts, ends, strict=True))]  # fmt: skip
    words = [*base.words[:4], *spoken, *base.words[5:]]
    return base.model_copy(update={"words": words})


def _long_b05(length: float, **changes: Any) -> PicturePlan:
    lengths = [2.5] * 20
    lengths[2] = length
    return replace(make_plan(body_lengths=lengths), "b05", **changes)


def _density_lines(result: object, beat_id: str = "b05") -> list[str]:
    assert isinstance(result, grammar.Violations), result
    return [v.message for v in result.items if (v.beat_id, v.rule) == (beat_id, "3.1")]


def test_a_stamp_lands_mid_beat_and_pops_count_at_their_words(popped: StyleSpec) -> None:
    """066: the change times are the beat start, each pop at its word, the stamp at
    mid-beat and the beat end; the largest gap between them is at most
    `density_gap_max_s` (1.5 s, the vishva value too)."""
    gap_max = popped.beats.density_gap_max_s
    assert gap_max == 1.5
    stamped = _long_b05(4.0)  # 10.0, 12.0 (the stamp), 14.0: 2.0 s on each side
    (line,) = _density_lines(picture(stamped, popped, transcript=_words_on_b05(stamped, [10.4])))
    assert "from 10.00 s to 12.00 s (2 s)" in line and f"{gap_max:g} s" in line
    one = _with_pops(stamped, "b05", _pop(word=5))
    (line,) = _density_lines(picture(one, popped, transcript=_words_on_b05(one, [10.4, 13.0])))
    assert "from 10.00 s to 12.00 s (2 s)" in line  # 13.0 closes the far side only
    assert "add a pop on a word in that span or split the beat" in line
    two = _with_pops(stamped, "b05", _pop(word=4), _pop(word=5))
    checked(two, popped, transcript=_words_on_b05(two, [11.0, 13.0]))  # four 1.0 s gaps


def test_a_pop_alone_splits_a_beat_only_where_it_lands(popped: StyleSpec) -> None:
    """066: a 3.0 s beat with no stamp and one pop at +1.5 s passes; with the pop at
    +0.2 s the span from the pop to the beat end is named."""
    bare = _with_pops(_long_b05(3.0, event=Event()), "b05", _pop(word=4))
    checked(bare, popped, transcript=_words_on_b05(bare, [11.5]))
    (line,) = _density_lines(picture(bare, popped, transcript=_words_on_b05(bare, [10.2])))
    assert "from 10.20 s to 13.00 s (2.8 s)" in line


def test_bubbles_and_stickers_count_at_their_words_too(
    bubbled: StyleSpec, stuck: StyleSpec
) -> None:
    """066: a bubble or a sticker is a change at its resolved `at_s`, like a pop."""
    bare = _long_b05(3.0, event=Event())
    for style, plan in (
        (bubbled, _with_bubbles(bare, "b05", _bubble())),
        (stuck, _with_sticker(bare, "b05", _sticker())),
    ):
        checked(plan, style, transcript=_words_on_b05(plan, [11.5]))
        (line,) = _density_lines(picture(plan, style, transcript=_words_on_b05(plan, [10.2])))
        assert "from 10.20 s to 13.00 s (2.8 s)" in line


def test_set_pieces_and_overlay_beats_stay_unmeasured(spec: StyleSpec) -> None:
    """066 / 3.1: a set piece and a beat with an overlay change on their own."""
    as_list = _long_b05(4.0, event=Event(), **AS_LIST)
    assert "b05" not in {v.beat_id for v in grammar.density(as_list.beats, spec)}
    overlaid = _long_b05(4.0, event=Event(), overlays=["label_flyin"])
    assert grammar.density(overlaid.beats, spec) == []


def _old_verdict(b: Beat, gap_max: float) -> bool:
    """3.1 before 066: one landed event halves the beat, none leaves all of it."""
    length = round(b.end - b.start, 3)
    gap = round(length / 2, 3) if b.event.kind != "none" else length
    return gap > gap_max + grammar.EPS


def test_beats_with_nothing_popping_are_judged_as_before(spec: StyleSpec) -> None:
    """066: a beat with no pop, bubble or sticker gets the verdict it got before, over
    the base plan's variants and every smoke style's fake plan under `smoke_specs`."""
    specs = styles.load_all(render.registry())
    transcript = FakeTranscriber().transcribe(Path("unused.mp4"))
    cases: list[tuple[PicturePlan, StyleSpec]] = []
    for length in (1.5, 1.6, 2.5, 3.0, 3.1, 4.0):
        cases += [(_long_b05(length), spec), (_long_b05(length, event=Event()), spec)]
    for name in ("explainer", "hitech", "footage", "vishva", "fastfacts"):
        judged = fixture.smoke_specs(specs, name)[name]
        request = PlanRequest(
            brief=smoke.SMOKE_BRIEF, style=PlanStyle(name=name), style_note=name,
            transcript=transcript, references=[],
            constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
            asset_policy="any",
        )  # fmt: skip
        cases.append((FakePlanner().plan_picture(request), judged))
    for plan, style in cases:
        quiet = [b for b in plan.beats if not grammar.pops_in(b)
                 and b.kind not in grammar.DENSITY_EXEMPT_KINDS and not b.overlays]  # fmt: skip
        flagged = {v.beat_id for v in grammar.density(plan.beats, style)}
        gap_max = style.beats.density_gap_max_s
        assert {b.id for b in quiet if _old_verdict(b, gap_max)} == flagged & {b.id for b in quiet}


def test_run04s_run3_first_reply_names_the_span_of_each_flagged_beat() -> None:
    """066: run04's run-3 first picture reply (job 20260928-140620-f774e1, JSON only),
    under vishva: every 3.1 line names its still span."""
    specs = styles.load_all(render.registry())
    plan = PicturePlan.model_validate_json((RUN04 / "picture_run3_first.json").read_text("utf-8"))
    transcript = Transcript.model_validate_json((RUN04 / "transcript.json").read_text("utf-8"))
    result = grammar.validate_picture(
        plan, transcript, specs["vishva"], references=["ref1", "ref2", "ref3", "ref4"]
    )
    lines = [v for v in getattr(result, "items", []) if v.rule == "3.1"]
    for v in lines:
        assert v.beat_id is not None
        assert "nothing changes on screen from " in v.message and " s to " in v.message, v
        assert "landed event" not in v.message, v
    spans = {v.beat_id: v.message.split(" (")[0].removeprefix("nothing changes on screen ")
             for v in lines}  # fmt: skip
    # b20 carried a pop (47.90 s) and a lower-third (mid-beat, 48.23 s) in a 3.82 s
    # beat: both land in its first half, so the second half is what stays still.
    b20 = next(b for b in plan.beats if b.id == "b20")
    assert b20.text_pops and b20.event.kind == "lower_third"
    assert spans == {
        "b02": "from 1.90 s to 3.50 s",  # its one bubble lands at the beat start
        "b13": "from 23.56 s to 26.42 s",
        "b14": "from 29.28 s to 31.60 s",
        "b18": "from 38.38 s to 41.66 s",
        "b20": "from 48.23 s to 50.14 s",
        "b21": "from 50.14 s to 51.89 s",
    }


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
    """64 s plan (5 s opening, 29 x 2.0 s body, 1 s finale), eight 2.0 s full beats =
    16 s = 0.25 exactly; a ninth passes the cap."""
    body = [2.0] * 29
    full_at = [0, 4, 8, 12, 16, 20, 24, 28]
    pattern = modes("".join("f" if i in full_at else "p" for i in range(29)))
    plan = make_plan(body_lengths=body, body_modes=pattern, assets=16)
    for i in full_at:
        plan = replace(plan, f"b{i + 3:02d}", kind="presenter_full", reason="emotional_line",
                       motion=None, subject_kind=None, query="", asset_id=None)  # fmt: skip
    # pip runs of three between full beats, off nowhere: the modes stay legal.
    checked(plan, spec)
    over = replace(plan, "b17", mode="full", kind="presenter_full", reason="emotional_line",
                   motion=None, subject_kind=None, query="", asset_id=None)  # fmt: skip
    assert (None, "3.2") in rules(picture(over, spec))


def test_seventh_consecutive_pip_is_rejected(spec: StyleSpec) -> None:
    """The two opening beats are pip, so the body's first run counts from three."""
    six = modes("pppp o pppppp o pppppp o p")
    checked(make_plan(body_lengths=[2.5] * 20, body_modes=six), spec)
    seven = modes("ppppp o pppppp o pppppp o")
    result = picture(make_plan(body_lengths=[2.5] * 20, body_modes=seven), spec)
    assert ("b07", "3.2") in rules(result)  # the seventh pip beat is b07


def test_fourth_consecutive_off_is_rejected(spec: StyleSpec) -> None:
    three = modes("p ooo ppppo ppppo ppppo p")
    checked(make_plan(body_lengths=[2.5] * 20, body_modes=three), spec)
    four = modes("p oooo ppppo ppppo ppppo")
    plan = make_plan(body_lengths=[2.5] * 20, body_modes=four)
    assert ("b07", "3.2") in rules(picture(plan, spec))


def test_finale_not_off_is_rejected(spec: StyleSpec) -> None:
    pip_finale = replace(make_plan(), "b23", mode="pip")
    assert ("b23", "3.2") in rules(picture(pip_finale, spec))


# --- the speaker's order and the cut (3.4 as amended by 055) ------------------------------


def _f1_plan(cut: CutPlan) -> PicturePlan:
    """A plan over the F1 recording (59.93 s) with the given cut; only the cut rules are
    asserted on it, so its beats are the base plan's stretched to the recording."""
    base = make_plan(body_lengths=[2.5] * 20, finale_s=1.0)
    scale = 59.93 / base.beats[-1].end
    beats = [
        b.model_copy(update={"start": round(b.start * scale, 3), "end": round(b.end * scale, 3)})
        for b in base.beats
    ]
    return base.model_copy(update={"cut": cut, "beats": beats})


def test_f1s_lift_replayed_as_a_re_ordered_cut_is_rejected_naming_the_span(
    spec: StyleSpec,
) -> None:
    """F1 lifted 'आप यकीन नहीं मानोगे' (22.74-24.1 s) to the front and dropped it from
    its place. As a cut that plays that span first, the plan is rejected at plan level
    with the span named; nothing else is checked on a cut that is not the speech."""
    lifted = CutPlan(keep=[F1_LIFT, Span(start=0.0, end=F1_LIFT.start),
                           Span(start=F1_LIFT.end, end=59.93)])  # fmt: skip
    result = picture(_f1_plan(lifted), spec, transcript=f1_transcript())
    assert rules(result) == {(None, "3.4")}
    assert isinstance(result, grammar.Violations)
    (line,) = result.lines()
    assert "22.74-24.1 s" in line and "speaker's order" in line


def test_a_drop_that_removes_spoken_words_is_rejected_naming_the_words(
    spec: StyleSpec,
) -> None:
    """F1's other half: dropping the line at its original place removes four words."""
    dropped = CutPlan(keep=[Span(start=0.0, end=59.93)], drop=[F1_LIFT])
    result = picture(_f1_plan(dropped), spec, transcript=f1_transcript())
    assert rules(result) == {(None, "3.4")}
    assert isinstance(result, grammar.Violations)
    (line,) = result.lines()
    assert "आप यकीन नहीं मानोगे" in line and "22.74-24.1 s" in line and "silence" in line
    # A keep list that ends before the last word drops words too.
    early = CutPlan(keep=[Span(start=0.0, end=59.0)])
    result = picture(_f1_plan(early), spec, transcript=f1_transcript())
    assert isinstance(result, grammar.Violations)
    assert any("क्यूं" in v.message for v in result.items)


def test_a_cut_edge_inside_a_word_is_rejected_but_an_edge_in_silence_passes(
    spec: StyleSpec,
) -> None:
    base = make_plan()
    transcript = transcript_for(base)  # b04's word (w3) runs 7.9-10.0 s; silence 7.5-7.9 s
    into = base.model_copy(update={"cut": CutPlan(keep=[Span(start=0.0, end=56.0)],
                                                  drop=[Span(start=8.5, end=8.6)])})  # fmt: skip
    result = picture(into, spec, transcript=transcript)
    assert rules(result) == {(None, "3.4")}
    assert isinstance(result, grammar.Violations)
    (line,) = result.lines()
    assert "'w3'" in line and "7.9-10 s" in line
    silent = base.model_copy(update={"cut": CutPlan(keep=[Span(start=0.0, end=56.0)],
                                                    drop=[Span(start=7.6, end=7.8)])})  # fmt: skip
    checked(silent, spec, transcript=transcript)


def test_a_pause_over_max_pause_s_is_tightened_as_a_clamp_and_the_beats_follow(
    spec: StyleSpec,
) -> None:
    """055: b06's word starts 1.4 s into the beat (a 1.4 s pause after b05's word);
    code keeps 0.6 s of it, so the validated cut loses 0.8 s at 12.8-13.6 s, every beat
    from b06 on moves 0.8 s earlier on the output and the clamp names the pause."""
    plan = make_plan()
    transcript = transcript_for(plan, gap_before={"b06": 1.4})
    result = checked(plan, spec, transcript=transcript)
    assert [(c.rule, c.message.split(":")[0]) for c in result.clamps] == [("3.4", "cut")]
    assert "1.4 s pause after 'w4'" in result.clamps[0].message
    picture_ = result.picture
    assert [(s.start, s.end) for s in picture_.cut.keep] == [(0.0, 12.8), (13.6, 56.0)]
    assert picture_.cut.drop == []
    by_id = {b.id: b for b in picture_.beats}
    assert (by_id["b05"].start, by_id["b05"].end) == (10.0, 12.5)
    assert (by_id["b06"].start, by_id["b06"].end) == (12.5, 14.2)
    assert by_id["b23"].end == pytest.approx(55.2)
    spans = presenter.cut_list(picture_)
    placed = [w for _, w in presenter.words_on_cut(spans, transcript.words)]
    assert max(b.start - a.end for a, b in zip(placed, placed[1:], strict=False)) <= 0.6 + 1e-9
    assert len(placed) == len(transcript.words)


def test_the_f1_transcript_is_tightened_once_and_no_word_is_shortened(spec: StyleSpec) -> None:
    """The F1 recording has one pause over 0.6 s (0.74 s after 'खिलाओ' at 19.06 s)."""
    transcript = f1_transcript()
    plan = _f1_plan(CutPlan(keep=[Span(start=0.0, end=59.93)]))
    spans, cut, clamps = grammar.cut_spans(plan, transcript.words, spec)
    assert len(clamps) == 1 and "'खिलाओ'" in clamps[0].message and "0.74 s" in clamps[0].message
    assert presenter.total_duration(spans) == pytest.approx(59.93 - 0.14, abs=1e-3)
    assert cut.keep == spans and cut.drop == []
    placed = presenter.words_on_cut(spans, transcript.words)
    assert [i for i, _ in placed] == list(range(len(transcript.words)))
    for (_, on_cut), word in zip(placed, transcript.words, strict=True):
        assert on_cut.end - on_cut.start == pytest.approx(word.end - word.start, abs=1e-3)
    # Tightening a tightened cut changes nothing (T8 re-validates the validated plan).
    again, cut_again, none = grammar.cut_spans(plan.model_copy(update={"cut": cut}),
                                               transcript.words, spec)  # fmt: skip
    assert again == spans and cut_again == cut and none == []


def test_the_head_before_the_first_word_is_trimmed_to_the_snap_window(spec: StyleSpec) -> None:
    """055: the short starts with the first spoken word; the first beat starts at 0 on
    the output and the cut starts within `snap_window_s` of the word."""
    plan = make_plan()
    transcript = transcript_for(plan)
    late = [transcript.words[0].model_copy(update={"start": 0.9}), *transcript.words[1:]]
    result = checked(plan, spec, transcript=transcript.model_copy(update={"words": late}))
    assert result.picture.cut.keep[0].start == pytest.approx(0.9 - spec.beats.snap_window_s)
    assert result.picture.beats[0].start == 0.0
    assert result.picture.beats[0].end == pytest.approx(2.5 - 0.75)
    assert any("head" in c.message for c in result.clamps)


def test_beats_are_planned_on_the_recording_and_mapped_onto_the_cut(spec: StyleSpec) -> None:
    """055: the planner drops 0.8 s of silence at 12.6-13.4 s (inside the 1.4 s pause
    before b06's word); its beats still tile the recording and come out tiling the cut,
    b06 shortened by the drop. Re-validating the validated plan on the output timeline
    changes nothing."""
    plan = make_plan().model_copy(update={"cut": CutPlan(
        keep=[Span(start=0.0, end=56.0)], drop=[Span(start=12.6, end=13.4)],
    )})  # fmt: skip
    transcript = transcript_for(plan, gap_before={"b06": 1.4})
    result = checked(plan, spec, transcript=transcript)
    assert result.clamps == []  # the remaining pause is 0.6 s: nothing to tighten
    assert result.picture.cut == plan.cut
    by_id = {b.id: b for b in result.picture.beats}
    assert (by_id["b06"].start, by_id["b06"].end) == (12.5, 14.2)
    assert by_id["b23"].end == pytest.approx(55.2)
    again = checked(result.picture, spec, transcript=transcript, timeline="output")
    assert again.picture == result.picture and again.clamps == []
    # A beat lying wholly inside dropped audio has no length on the cut.
    inside = plan.model_copy(update={"cut": CutPlan(
        keep=[Span(start=0.0, end=56.0)], drop=[Span(start=12.6, end=15.0)],
    )})  # fmt: skip
    words = transcript_for(plan, gap_before={"b06": 2.5, "b07": 0.0}).words
    words = [w for w in words if w.text != "w5"]  # no word inside the drop
    silent = transcript.model_copy(update={"words": words})
    result2 = picture(inside, spec, transcript=silent)
    assert ("b06", "3.1") in rules(result2)


def test_beats_must_tile_the_cut_runtime(spec: StyleSpec) -> None:
    """3.1: a plan whose beats end before the cut list's runtime is rejected (the tail
    after the last word is the planner's to keep)."""
    base = make_plan()
    long_tail = base.model_copy(update={"cut": CutPlan(keep=[Span(start=0.0, end=57.0)])})
    transcript = transcript_for(base).model_copy(update={"duration_s": 57.0})
    assert (None, "3.1") in rules(picture(long_tail, spec, transcript=transcript))


# --- the opening (3.4 as amended by 055) -----------------------------------------------------


def test_the_base_opening_is_two_pip_beats_over_images_ending_at_opening_max_s(
    spec: StyleSpec,
) -> None:
    plan = make_plan()
    assert [(b.mode, b.kind) for b in plan.beats[:2]] == [("pip", "photo"), ("pip", "card")]
    assert plan.beats[1].end == spec.beats.opening_max_s == 5.0
    checked(plan, spec)
    late = make_plan(opening_s=2.51)  # b02 ends at 5.02 s
    assert ("b02", "3.4") in rules(picture(late, spec))


@pytest.mark.parametrize(
    ("beat_id", "changes"),
    [
        ("b01", {"mode": "full", "kind": "presenter_full", "reason": "emotional_line",
                 "motion": None, "subject_kind": None, "query": "", "asset_id": None,
                 "event": Event()}),
        ("b01", {"mode": "off"}),
        ("b02", {"mode": "pip", "kind": "presenter_pip", "motion": None, "subject_kind": None,
                 "query": "", "asset_id": None, "event": Event()}),
        ("b02", {"asset_id": None}),
        ("b01", {**AS_LIST}),
    ],
)  # fmt: skip
def test_an_opening_beat_that_is_not_pip_over_an_image_is_rejected(
    spec: StyleSpec, beat_id: str, changes: dict[str, Any]
) -> None:
    """No cold open, no hook cards, no presenter-only beat: the first two beats are pip
    over a photo or card with an asset."""
    result = picture(replace(make_plan(), beat_id, **changes), spec)
    assert (beat_id, "3.4") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("opening beat" in v.message for v in result.items if v.beat_id == beat_id)
    # The third beat is free: a full beat there is the body's business.
    third = replace(make_plan(), "b03", mode="full", kind="presenter_full",
                    reason="argument_turn", motion=None, subject_kind=None, query="",
                    asset_id=None)  # fmt: skip
    checked(third, spec)


def test_the_owner_reference_opens_the_short_when_the_job_has_one(spec: StyleSpec) -> None:
    plan = make_plan()
    result = picture(plan, spec, references=["ref1", "ref2"])
    assert ("b01", "3.4") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("owner's reference" in v.message and "ref1" in v.message for v in result.items)
    checked(replace(plan, "b01", asset_id="ref2"), spec, references=["ref1", "ref2"])
    checked(plan, spec)  # no references: any image opens


def test_the_first_beat_is_no_longer_exempt_from_the_density_rule(spec: StyleSpec) -> None:
    """The cold open carried its punch-in; a pip photo has to change on screen."""
    still = replace(make_plan(), "b01", event=Event())
    assert ("b01", "3.1") in rules(picture(still, spec))


def test_a_plan_with_a_hook_object_or_a_hook_cards_beat_does_not_parse(spec: StyleSpec) -> None:
    from pydantic import ValidationError

    data = make_plan().model_dump()
    with pytest.raises(ValidationError):
        PicturePlan.model_validate({**data, "hook": {"title": "t"}})
    beat = {**data["beats"][1], "kind": "hook_cards"}
    with pytest.raises(ValidationError):
        Beat.model_validate(beat)
    with pytest.raises(ValidationError):
        Beat.model_validate({**data["beats"][0], "mode": "full", "reason": "cold_open"})


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
    # the finale carries its fixed motion from the spec; presenter beats none.
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


# --- moving footage (ticket 058; 4.1 and 5.1 as amended) -----------------------------------
#
# The base plan's even body beats (b03, b05, ..., b21) are `photo` concept scenes, the odd
# ones `card` entities; the body is 50 s of the 56 s runtime.


def as_clip(plan: PicturePlan, *beat_ids: str) -> PicturePlan:
    """The beats as `clip` beats, each with its own asset (the base plan's stills cycle
    through twelve ids, and a clip's asset is never a still's)."""
    for beat_id in beat_ids:
        plan = replace(plan, beat_id, kind="clip", motion="push_in", asset_id=f"v_{beat_id}")
    return plan


def test_a_clip_passes_on_a_concept_beat_and_on_the_opening(spec: StyleSpec) -> None:
    """058 (1): a `clip` is a full-screen moving shot on a concept beat, the opening
    included when the topic is a concept; it needs its motion and asset like a photo."""
    checked(as_clip(make_plan(), "b05"), spec)
    checked(as_clip(make_plan(), "b01"), spec)
    assert ("b05", "4.1") in rules(picture(replace(as_clip(make_plan(), "b05"), "b05",
                                                     motion=None), spec))  # fmt: skip
    assert ("b01", "3.4") in rules(picture(replace(as_clip(make_plan(), "b01"), "b01",
                                                     asset_id=None), spec))  # fmt: skip


def test_a_clip_is_never_a_named_entity(spec: StyleSpec) -> None:
    """058 (2): a beat whose subject is a named person, place, product or event keeps
    the still ladder; a `clip` there is rejected naming the beat. An entity beat that
    depicts a scene (a kind of place) may take one."""
    result = picture(as_clip(make_plan(), "b06"), spec)  # b06: entity, depicts None
    assert ("b06", "4.1") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("named entity" in v.message and "058" in v.message for v in result.items)
    named = replace(as_clip(make_plan(), "b05"), "b05", depicts="named_entity")
    assert ("b05", "4.1") in rules(picture(named, spec))
    scene = replace(as_clip(make_plan(), "b06"), "b06", depicts="scene")
    checked(scene, spec)


def test_clip_beats_take_at_most_the_styles_share_of_the_runtime(spec: StyleSpec) -> None:
    """058 (6): `broll.clip_max_fraction` (0.35) caps the runtime clip beats cover:
    seven 2.5 s clips on the 56 s plan (17.5 s, 0.31) pass, eight (20 s, 0.36) fail
    naming the plan; a style with the share at 0 takes none."""
    concept = [f"b{n + 3:02d}" for n in range(0, 20, 2)]  # the ten photo beats
    checked(as_clip(make_plan(), *concept[:7]), spec)
    result = picture(as_clip(make_plan(), *concept[:8]), spec)
    assert (None, "4.1") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("clip_max_fraction" in v.message for v in result.items)
    off = spec.model_copy(deep=True)
    off.broll.clip_max_fraction = 0.0
    assert (None, "4.1") in rules(picture(as_clip(make_plan(), "b05"), off))
    assert grammar.clip_share(as_clip(make_plan(), *concept[:7]).beats) == pytest.approx(17.5)


def test_a_clip_beats_asset_is_moving_footage_and_never_a_still(spec: StyleSpec) -> None:
    """058 (7): a clip counts as an image for reuse, so another clip beat may name its
    asset; a still beat or a set-piece item (stills only) naming it is rejected, and a
    clip beat naming a still beat's asset is rejected too. A number beat carrying the
    clip on over its stamp is fine."""
    plan = as_clip(make_plan(), "b05")  # b05's asset is now v_b05
    checked(replace(as_clip(plan, "b07"), "b07", asset_id="v_b05"), spec)
    still_reuse = replace(plan, "b07", asset_id="v_b05")  # b07 is a photo
    assert ("b07", "4.1") in rules(picture(still_reuse, spec))
    items = [SetPieceItem(text="one", asset_id="v_b05"), SetPieceItem(text="two")]
    on_list = replace(plan, "b08", **{**AS_LIST, "items": items})
    result = picture(on_list, spec)
    assert ("b08", "4.1") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("clip" in v.message and "v_b05" in v.message for v in result.items)
    clip_of_still = replace(as_clip(make_plan(), "b07"), "b07", asset_id="a03")  # b05's still
    assert ("b07", "4.1") in rules(picture(clip_of_still, spec))
    number = replace(plan, "b06", subject_kind="number", depicts=None, asset_id="v_b05",
                     kind="photo", motion="ken_burns_in")  # fmt: skip
    checked(number, spec)


def test_a_clip_is_a_picture_beat_for_text_pops_and_bubbles(spec: StyleSpec) -> None:
    """061 / 063 as amended by 058: a pop or a bubble may sit on a moving clip."""
    plan = as_clip(make_plan(), "b05")
    popped = replace(plan, "b05", text_pops=[TextPop(text="1945", word=4, x=60.0, y=40.0)])
    checked(popped, text_pop_style(spec))
    bubbled = replace(plan, "b05", bubbles=[Bubble(text="Why?", first=4, last=4, x=19.4, y=50.0)])
    checked(bubbled, bubble_style(spec))
    assert "clip" in grammar.TEXT_POP_KINDS and "clip" in grammar.BUBBLE_KINDS
    assert "clip" in grammar.OPENING_KINDS


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
    """4.3: an item is a montage member, never a showing, so it neither adds a unique
    asset nor spends the asset's `reuse_max`."""
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
    ok = cued(plan, spec, Cue(beat_id="b05", intent="drum", at="event"))
    assert isinstance(ok, grammar.SoundCheck)


def test_label_flyin_rides_only_on_an_infographic(spec: StyleSpec) -> None:
    plan = replace(make_plan(), "b05", overlays=["label_flyin"])
    assert ("b05", "9.3") in rules(picture(plan, spec))


# --- text pops (ticket 061; 4.1 as amended) ------------------------------------------------
#
# The base plan's b05 is a `photo` beat (beats[4]) whose one word is w4; b06 a `card`.


@pytest.fixture(scope="module")
def popped(spec: StyleSpec) -> StyleSpec:
    """061's test style: the explainer with `text_pops_max_per_60s` 10."""
    return text_pop_style(spec)


def _pop(text: str = "1945", word: int = 4, **fields: Any) -> TextPop:
    return TextPop(text=text, word=word, x=60.0, y=40.0, **fields)


def _with_pops(plan: PicturePlan, beat_id: str, *pops: TextPop) -> PicturePlan:
    return replace(plan, beat_id, text_pops=list(pops))


def test_text_pops_pass_on_a_picture_beat_and_land_on_their_words_output_time(
    popped: StyleSpec,
) -> None:
    """061 (2, 3): one or two pops on a `photo` or `card` beat pass under a style with
    pops on; the validated plan's pop carries `at_s`, the named word's start on the
    output timeline; the plan's own `at_s` is never trusted."""
    plan = _with_pops(make_plan(), "b05", _pop(at_s=99.0))
    result = checked(plan, popped)
    (pop,) = next(b for b in result.picture.beats if b.id == "b05").text_pops
    assert pop.at_s == transcript_for(plan).words[4].start == 10.4
    two = _with_pops(make_plan(), "b06", _pop("DARA SINGH", 5), _pop("1947", 5, fill="accent"))
    assert [p.at_s for p in checked(two, popped).picture.beats[5].text_pops] == [12.9, 12.9]


def test_text_pops_map_onto_the_cut_like_beat_boundaries(popped: StyleSpec) -> None:
    """055 / 061: a pop's landing is written in output seconds. With 0.8 s tightened
    out of the pause before b06's word, a pop on b07 lands 0.8 s earlier than the
    word's recording time, inside the mapped beat."""
    plan = _with_pops(make_plan(), "b07", _pop("w6", 6))
    transcript = transcript_for(plan, gap_before={"b06": 1.4})
    result = checked(plan, popped, transcript=transcript)
    b07 = next(b for b in result.picture.beats if b.id == "b07")
    at = b07.text_pops[0].at_s
    assert at is not None and at == pytest.approx(transcript.words[6].start - 0.8)
    assert b07.start <= at < b07.end
    again = checked(result.picture, popped, transcript=transcript, timeline="output")
    assert again.picture == result.picture


def test_text_pops_are_rejected_where_the_style_caps_them_at_zero(spec: StyleSpec) -> None:
    """061 (4): the four existing styles set `broll.text_pops_max_per_60s` 0, so any
    pop fails validation naming the beat."""
    found = rules(picture(_with_pops(make_plan(), "b05", _pop()), spec))
    assert ("b05", "4.1") in found


def test_text_pops_are_capped_per_beat_and_per_60s_rounding_up(popped: StyleSpec) -> None:
    """061 (4): at most `broll.motion.text_pop.max_per_beat` (2) on one beat and
    ceil(`text_pops_max_per_60s` x runtime / 60) over the short: 10 on the 56 s plan,
    1 on the six-second fixture; the violation names the beat that crosses the cap."""
    three = _with_pops(make_plan(), "b05", _pop("a"), _pop("b"), _pop("c"))
    assert ("b05", "4.1") in rules(picture(three, popped))
    plan = make_plan()
    ids = [f"b{n:02d}" for n in range(3, 23)]  # the twenty body beats
    for beat_id, index in zip(ids[:10], range(2, 12), strict=True):
        plan = _with_pops(plan, beat_id, _pop(word=index))
    checked(plan, popped)
    eleventh = _with_pops(plan, ids[10], _pop(word=12))
    found = rules(picture(eleventh, popped))
    assert (ids[10], "4.1") in found and (ids[9], "4.1") not in found
    assert grammar.text_pop_cap(popped, runtime=6.0) == 1
    assert grammar.text_pop_cap(popped, runtime=56.0) == 10
    assert grammar.text_pop_cap(popped, runtime=60.0) == 10


def test_a_text_pop_names_a_word_spoken_inside_its_beat(popped: StyleSpec) -> None:
    """061 (3): the pop lands on the spoken word, so the word must be one the beat
    covers; a word of another beat or an index past the transcript is rejected naming
    the beat."""
    assert ("b05", "4.1") in rules(picture(_with_pops(make_plan(), "b05", _pop(word=5)), popped))
    assert ("b05", "4.1") in rules(picture(_with_pops(make_plan(), "b05", _pop(word=99)), popped))


def test_a_text_pop_is_one_to_four_words_on_a_picture_beat(popped: StyleSpec) -> None:
    """061 (1, 2): 1-4 words; on `photo`, `card` or the presenter full frame only, never
    on a set piece, a map or a chart."""
    five = _with_pops(make_plan(), "b05", _pop("one two three four five"))
    assert ("b05", "4.1") in rules(picture(five, popped))
    blank = _with_pops(make_plan(), "b05", _pop("   "))
    assert ("b05", "4.1") in rules(picture(blank, popped))
    on_list = _with_pops(replace(make_plan(), "b05", **AS_LIST), "b05", _pop())
    assert ("b05", "4.1") in rules(picture(on_list, popped))
    full = replace(
        make_plan(), "b05", mode="full", reason="emotional_line", kind="presenter_full",
        motion=None, event=Event(), asset_id=None, text_pops=[_pop("THIS IS IT")],
    )  # fmt: skip
    checked(full, popped, transcript=_words_on_b05(full, [11.0]))  # 066: 1.0 s + 1.5 s still


def test_an_event_cue_may_sit_on_a_text_pop_and_a_whoosh_rides_a_pop_in(
    popped: StyleSpec, spec: StyleSpec
) -> None:
    """061 (6): a pop is something to hit, so an `event` cue on a beat with no landed
    event but a text pop passes 9.4 (070: a `tick` marks it; a floor class on a bare beat
    is still refused by 9.4); under a style that allows whooshes with `pop` in
    `sound.whoosh.on`, a `whoosh` at the pop's landing (`at: event`) passes 7.3, while
    one at the beat's start (no flash there) or on a beat with no pop is refused."""
    bare = replace(make_plan(), "b05", event=Event())
    hit = Cue(beat_id="b05", intent="bass", at="event")
    assert ("b05", "9.4") in rules(cued(bare, popped, hit))
    with_pop = _with_pops(bare, "b05", _pop())
    ok = cued(with_pop, popped, Cue(beat_id="b05", intent="tick", at="event"))
    assert isinstance(ok, grammar.SoundCheck)
    both = text_pop_style(flash_whoosh_style(spec))
    whoosh = Cue(beat_id="b05", intent="whoosh", at="event")
    assert isinstance(cued(with_pop, both, whoosh), grammar.SoundCheck)
    at_start = Cue(beat_id="b05", intent="whoosh", at="start")
    assert ("b05", "7.3") in rules(cued(with_pop, both, at_start))
    assert ("b05", "7.3") in rules(cued(bare, both, whoosh))
    flash_only = both.model_copy(deep=True)
    assert flash_only.sound.whoosh is not None
    flash_only.sound.whoosh.on = ["flash"]
    assert ("b05", "7.3") in rules(cued(with_pop, flash_only, whoosh))


# --- bubbles (ticket 063; 4.1 as amended) ------------------------------------------------
#
# The base plan's b05 (10.0-12.5 s, a `photo`) speaks w4 at 10.4; b06 (a `card`) w5 at
# 12.9; w2 and w3 were said on b03 and b04.


@pytest.fixture(scope="module")
def bubbled(spec: StyleSpec) -> StyleSpec:
    """063's test style: the explainer with `bubbles_max_per_60s` 20."""
    return bubble_style(spec)


def _bubble(
    text: str = "Who asked?", first: int = 4, last: int | None = None, **fields: Any
) -> Bubble:
    return Bubble(text=text, first=first, last=first if last is None else last, x=60.0, y=40.0,
                  **fields)  # fmt: skip


def _with_bubbles(plan: PicturePlan, beat_id: str, *bubbles: Bubble) -> PicturePlan:
    return replace(plan, beat_id, bubbles=list(bubbles))


def test_bubbles_pass_on_a_picture_beat_and_land_on_their_first_source_word(
    bubbled: StyleSpec,
) -> None:
    """063 (1, 2): a bubble on a `photo` or `card` beat passes under a style with
    bubbles on; the validated plan's bubble carries `at_s`, its first source word's
    start on the output timeline (the plan's own `at_s` is never trusted); a bubble
    quoting words said before the beat lands at the beat's start."""
    plan = _with_bubbles(make_plan(), "b05", _bubble(at_s=99.0))
    (bubble,) = next(b for b in checked(plan, bubbled).picture.beats if b.id == "b05").bubbles
    assert bubble.at_s == transcript_for(plan).words[4].start == 10.4
    earlier = _with_bubbles(make_plan(), "b05", _bubble("They said so", 2, 3, shape="thought"))
    (quoted,) = checked(earlier, bubbled).picture.beats[4].bubbles
    assert quoted.at_s == 10.0 and quoted.shape == "thought"
    on_card = _with_bubbles(make_plan(), "b06", _bubble("Really?", 5))
    assert checked(on_card, bubbled).picture.beats[5].bubbles[0].at_s == 12.9


def _two_words_on_b05(plan: PicturePlan) -> Transcript:
    """The base transcript with b05 speaking two words: w4 at 10.4-10.8 and w4b at
    11.3-12.5 (index 5; the later indices shift by one)."""
    base = transcript_for(plan)
    words = list(base.words)
    words[4] = Word(text="w4", start=10.4, end=10.8, segment=words[4].segment)
    words.insert(5, Word(text="w4b", start=11.3, end=12.5, segment=words[4].segment))
    return base.model_copy(update={"words": words})


def test_a_dialogue_pairs_second_bubble_lands_inside_the_gap_window(bubbled: StyleSpec) -> None:
    """063 (3): the second bubble of a beat lands `motion.bubble.dialogue_gap_min_s`-
    `dialogue_gap_max_s` (0.6-1.2 s) after the first: its own word's time when that
    falls inside the window, else the nearer edge; a beat too short to hold the pair
    is rejected naming it."""
    plan = make_plan()
    two = _two_words_on_b05(plan)
    question, answer = _bubble("Who asked?", 4), _bubble("Nobody", 5, shape="thought")
    pair = checked(_with_bubbles(plan, "b05", question, answer), bubbled, transcript=two)
    first, second = pair.picture.beats[4].bubbles
    assert (first.at_s, second.at_s) == (10.4, 11.3)  # w4b at 11.3 is inside 11.0-11.6
    early = checked(_with_bubbles(plan, "b05", question, _bubble("Me", 3)), bubbled, transcript=two)
    assert [b.at_s for b in early.picture.beats[4].bubbles] == [10.4, 11.0]  # w3 came earlier
    quoted = _with_bubbles(plan, "b05", _bubble("They said", 2, 3), answer)
    late = checked(quoted, bubbled, transcript=two)
    assert [b.at_s for b in late.picture.beats[4].bubbles] == [10.0, 11.2]  # w4b past 11.2
    short = make_plan(body_lengths=[*([2.5] * 19), 0.8])
    (b22,) = [b for b in short.beats if b.id == "b22"]
    assert b22.end - b22.start == pytest.approx(0.8)
    cramped = _with_bubbles(short, "b22", _bubble("Who asked?", 21), _bubble("Nobody", 21))
    assert ("b22", "4.1") in rules(picture(cramped, bubbled))
    assert grammar.bubble_gap(bubbled) == (0.6, 1.2)


def test_bubbles_are_rejected_where_the_style_caps_them_at_zero(spec: StyleSpec) -> None:
    """063 (5): the four existing styles set `broll.bubbles_max_per_60s` 0, so any
    bubble fails validation naming the beat."""
    assert ("b05", "4.1") in rules(picture(_with_bubbles(make_plan(), "b05", _bubble()), spec))


def test_bubbles_are_capped_per_beat_and_per_60s_rounding_up(bubbled: StyleSpec) -> None:
    """063 (3, 5): at most `motion.bubble.max_per_beat` (2) on one beat and
    ceil(`bubbles_max_per_60s` x runtime / 60) over the short: 19 on the 56 s plan,
    2 on the six-second fixture; the violation names the beat that crosses the cap."""
    three = _with_bubbles(make_plan(), "b05", _bubble("a"), _bubble("b"), _bubble("c"))
    assert ("b05", "4.1") in rules(picture(three, bubbled))
    plan = make_plan()
    ids = [f"b{n:02d}" for n in range(3, 23)]  # the twenty body beats
    for beat_id, index in zip(ids[:19], range(2, 21), strict=True):
        plan = _with_bubbles(plan, beat_id, _bubble(first=index))
    checked(plan, bubbled)
    twentieth = _with_bubbles(plan, ids[19], _bubble(first=21))
    found = rules(picture(twentieth, bubbled))
    assert (ids[19], "4.1") in found and (ids[18], "4.1") not in found
    assert grammar.bubble_cap(bubbled, runtime=6.0) == 2
    assert grammar.bubble_cap(bubbled, runtime=56.0) == 19
    assert grammar.bubble_cap(bubbled, runtime=60.0) == 20


def test_a_bubble_is_one_to_seven_words_from_the_recording_on_a_picture_beat(
    bubbled: StyleSpec,
) -> None:
    """063 (1, 2, 4): 1-`motion.bubble.words_max` words; its source words exist in the
    transcript and are spoken before the beat ends; on `photo`, `card` or the presenter
    full frame only, never on a set piece."""
    eight = _with_bubbles(make_plan(), "b05", _bubble("one two three four five six seven eight"))
    assert ("b05", "4.1") in rules(picture(eight, bubbled))
    seven = _with_bubbles(make_plan(), "b05", _bubble("one two three four five six seven"))
    checked(seven, bubbled)
    blank = _with_bubbles(make_plan(), "b05", _bubble("   "))
    assert ("b05", "4.1") in rules(picture(blank, bubbled))
    past = _with_bubbles(make_plan(), "b05", _bubble("Later", 4, 99))
    assert ("b05", "4.1") in rules(picture(past, bubbled))
    not_yet = _with_bubbles(make_plan(), "b05", _bubble("Not yet said", 5))
    assert ("b05", "4.1") in rules(picture(not_yet, bubbled))
    on_list = _with_bubbles(replace(make_plan(), "b05", **AS_LIST), "b05", _bubble())
    assert ("b05", "4.1") in rules(picture(on_list, bubbled))
    full = replace(
        make_plan(), "b05", mode="full", reason="emotional_line", kind="presenter_full",
        motion=None, event=Event(), asset_id=None, bubbles=[_bubble("Is it?")],
    )  # fmt: skip
    checked(full, bubbled, transcript=_words_on_b05(full, [11.0]))  # 066: 1.0 s + 1.5 s still


def test_a_bubble_is_a_change_on_screen_and_something_a_cue_may_hit(
    bubbled: StyleSpec, spec: StyleSpec
) -> None:
    """063 (5): a bubble counts as a change for the 3.1 density rule and is something to
    hit: an `event` cue on a beat with no landed event but a bubble passes 9.4, and under
    a style allowing whooshes with `pop` in `sound.whoosh.on` a `whoosh` at its pop-in
    (`at: event`) passes 7.3, while one at the beat's start is refused."""
    bare = replace(make_plan(), "b05", event=Event())
    assert ("b05", "3.1") in rules(picture(bare, bubbled))
    with_bubble = _with_bubbles(bare, "b05", _bubble())
    checked(with_bubble, bubbled, transcript=_words_on_b05(with_bubble, [11.0]))  # 066: at its word
    hit = Cue(beat_id="b05", intent="bass", at="event")
    assert ("b05", "9.4") in rules(cued(bare, bubbled, hit))
    tick = Cue(beat_id="b05", intent="tick", at="event")  # 070: the pop-in's mark
    assert isinstance(cued(with_bubble, bubbled, tick), grammar.SoundCheck)
    both = bubble_style(flash_whoosh_style(spec))
    whoosh = Cue(beat_id="b05", intent="whoosh", at="event")
    assert isinstance(cued(with_bubble, both, whoosh), grammar.SoundCheck)
    at_start = Cue(beat_id="b05", intent="whoosh", at="start")
    assert ("b05", "7.3") in rules(cued(with_bubble, both, at_start))
    assert ("b05", "7.3") in rules(cued(bare, both, whoosh))


# --- stickers (ticket 062; 4.1 as amended) -----------------------------------------------
#
# The base plan's b05 (10.0-12.5 s, a `pip` photo) speaks w4 at 10.4; b06 (a card) w5 at 12.9.


@pytest.fixture(scope="module")
def stuck(spec: StyleSpec) -> StyleSpec:
    """062's test style: the explainer with `stickers_max_per_60s` 10."""
    return sticker_style(spec)


def _sticker(intent: str = "idea", word: int = 4, **fields: Any) -> Sticker:
    return Sticker(intent=intent, word=word, **fields)


def _with_sticker(plan: PicturePlan, beat_id: str, *on: Sticker) -> PicturePlan:
    return replace(plan, beat_id, stickers=list(on))


def test_a_sticker_passes_on_a_picture_beat_lands_on_its_word_and_gets_its_row(
    stuck: StyleSpec,
) -> None:
    """062 (3, 4): a sticker on a picture beat passes under a style with stickers on;
    the validated plan carries `at_s` (the word's start on the output timeline, never
    the planner's) and the catalogue row: the one named, or the tag's first row."""
    plan = _with_sticker(make_plan(), "b05", _sticker(at_s=99.0))
    (sticker,) = checked(plan, stuck).picture.beats[4].stickers
    assert sticker.at_s == 10.4
    assert sticker.name == "Light bulb", "the tag's first row"
    named = _with_sticker(make_plan(), "b06", _sticker("shock", 5, name="Astonished face"))
    (kept,) = checked(named, stuck).picture.beats[5].stickers
    assert (kept.name, kept.at_s) == ("Astonished face", 12.9)
    placed = _with_sticker(make_plan(), "b05", _sticker(x=70.0, y=35.0))
    checked(placed, stuck)


def test_stickers_are_rejected_where_the_style_caps_them_at_zero(spec: StyleSpec) -> None:
    """062 (4): the four existing styles set `broll.stickers_max_per_60s` 0."""
    assert ("b05", "4.1") in rules(picture(_with_sticker(make_plan(), "b05", _sticker()), spec))


def test_stickers_are_capped_one_per_beat_and_per_60s_rounding_up(stuck: StyleSpec) -> None:
    """062 (3, 4): at most one per beat (`motion.sticker.max_per_beat`) and
    ceil(`stickers_max_per_60s` x runtime / 60) over the short: 10 on the 56 s plan, 1
    on the six-second fixture; the violation names the beat that crosses the cap."""
    two = _with_sticker(make_plan(), "b05", _sticker(), _sticker("fire"))
    assert ("b05", "4.1") in rules(picture(two, stuck))
    plan = make_plan()
    ids = [f"b{n:02d}" for n in range(3, 23)]
    for beat_id, index in zip(ids[:10], range(2, 12), strict=True):
        plan = _with_sticker(plan, beat_id, _sticker(word=index, x=60.0, y=35.0))  # some are off
    checked(plan, stuck)
    eleventh = _with_sticker(plan, ids[10], _sticker(word=12, x=60.0, y=35.0))
    found = rules(picture(eleventh, stuck))
    assert (ids[10], "4.1") in found and (ids[9], "4.1") not in found
    assert grammar.sticker_cap(stuck, runtime=6.0) == 1
    assert grammar.sticker_cap(stuck, runtime=56.0) == 10


def test_a_sticker_is_picked_by_a_catalogue_tag_never_a_free_name(stuck: StyleSpec) -> None:
    """062 (4): the intent must be a catalogue tag, and a named row must carry it; a
    file name is not a row."""
    for bad in (_sticker("unicorn"), _sticker("idea", name="Skull"),
                _sticker("idea", name="light_bulb_3d.png")):  # fmt: skip
        found = rules(picture(_with_sticker(make_plan(), "b05", bad), stuck))
        assert ("b05", "4.1") in found, bad


def test_a_sticker_lands_on_a_word_its_picture_beat_covers(stuck: StyleSpec) -> None:
    """062 (3): on a photo, card, clip or the presenter full frame, landing on a word
    the beat covers; off the PIP (a full beat) it needs its `{x, y}`."""
    assert ("b05", "4.1") in rules(picture(_with_sticker(make_plan(), "b05", _sticker(word=5)),
                                           stuck))  # fmt: skip
    assert ("b05", "4.1") in rules(picture(_with_sticker(make_plan(), "b05", _sticker(word=99)),
                                           stuck))  # fmt: skip
    on_list = _with_sticker(replace(make_plan(), "b05", **AS_LIST), "b05", _sticker())
    assert ("b05", "4.1") in rules(picture(on_list, stuck))

    def full(*on: Sticker) -> PicturePlan:
        return replace(
            make_plan(), "b05", mode="full", reason="emotional_line", kind="presenter_full",
            motion=None, event=Event(), asset_id=None, stickers=list(on),
        )  # fmt: skip

    assert ("b05", "4.1") in rules(picture(full(_sticker()), stuck))
    placed = full(_sticker(x=50.0, y=30.0))
    checked(placed, stuck, transcript=_words_on_b05(placed, [11.0]))  # 066: 1.0 s + 1.5 s still


def test_a_sticker_is_a_change_on_screen_and_something_a_cue_may_hit(
    stuck: StyleSpec, spec: StyleSpec
) -> None:
    """062 (5): a sticker counts as a change for 3.1 and a tick may mark it (`at:
    event`; 070: a ding only where it is tagged `idea`); a whoosh may ride its pop-in
    where `pop` is in `sound.whoosh.on`."""
    bare = replace(make_plan(), "b05", event=Event())
    assert ("b05", "3.1") in rules(picture(bare, stuck))
    with_sticker = _with_sticker(bare, "b05", _sticker())
    checked(with_sticker, stuck, transcript=_words_on_b05(with_sticker, [11.0]))  # 066: at its word
    hit = Cue(beat_id="b05", intent="bass", at="event")
    assert ("b05", "9.4") in rules(cued(bare, stuck, hit))
    tick = Cue(beat_id="b05", intent="tick", at="event")
    assert isinstance(cued(with_sticker, stuck, tick), grammar.SoundCheck)
    both = sticker_style(flash_whoosh_style(spec))
    whoosh = Cue(beat_id="b05", intent="whoosh", at="event")
    assert isinstance(cued(with_sticker, both, whoosh), grammar.SoundCheck)
    assert ("b05", "7.3") in rules(cued(bare, both, whoosh))


# --- assets (4.3) ------------------------------------------------------------------------


def test_unique_asset_count_scales_with_runtime(spec: StyleSpec) -> None:
    """55.5 s: 12/60 s -> 11 needed, 24/60 s -> 23 allowed; the opening's two assets
    count with the body's."""
    # 056 (3): twenty body beats over `reuse_max` 2 showings need ten assets, so the
    # floor is met with room (10 + 2 = 12) and missed at 8 + 2 = 10.
    checked(make_plan(assets=10), spec)
    assert (None, "4.3") in rules(picture(make_plan(assets=8), spec))
    # 60.2 s of 2.0 s beats: 24/60 s -> 25 allowed; 27 fresh assets is a slideshow's
    # opposite, a blur (4.3).
    def tight(assets: int) -> PicturePlan:
        return make_plan(finale_s=1.2, body_lengths=[2.0] * 27, assets=assets)

    checked(tight(23), spec)
    assert (None, "4.3") in rules(picture(tight(25), spec))


def test_reuse_over_reuse_max_is_rejected(spec: StyleSpec) -> None:
    """4.3 as amended by 056 (3): `reuse_max` (2) showings per asset; the finale's cards
    are a set piece and do not count, so a01 on b03, b15 and the finale passes."""
    assert spec.broll.reuse_max == 2
    plan = make_plan(assets=12)  # a01: b03, b15, finale
    checked(plan, spec)
    three = replace(plan, "b04", asset_id="a01")
    result = picture(three, spec)
    assert (None, "4.3") in rules(result)
    assert isinstance(result, grammar.Violations)
    assert any("a01" in v.message and "3 times" in v.message for v in result.items)


def test_a_carry_on_beat_and_the_set_pieces_are_not_showings(spec: StyleSpec) -> None:
    """056 (3): a `number` or `quote` beat over the previous beat's asset carries that
    showing on, and a wall's base is a set piece; neither spends `reuse_max`."""
    plan = make_plan(assets=12)
    carried = replace(plan, "b04", subject_kind="number", asset_id="a01")  # b03 is a01
    checked(carried, spec)
    quoted = replace(carried, "b05", subject_kind="quote", asset_id="a01")
    checked(quoted, spec)
    walled = _piece(replace(plan, "b06", asset_id="a01"), "b06", "wall", _items(4, asset="a02"))
    checked(walled, spec)
    # A number beat over a *different* asset than the previous beat's is a showing.
    fresh = replace(plan, "b05", subject_kind="number", asset_id="a01")  # b04 is a02
    assert (None, "4.3") in rules(picture(fresh, spec))


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


@pytest.fixture(scope="module")
def flashy(spec: StyleSpec) -> StyleSpec:
    """060's test style: flash enabled, whooshes allowed."""
    return flash_whoosh_style(spec)


def _flashed(plan: PicturePlan, *beat_ids: str) -> PicturePlan:
    for beat_id in beat_ids:
        plan = replace(plan, beat_id, enter="flash")
    return plan


def test_flash_is_rejected_where_the_style_does_not_enable_it(spec: StyleSpec) -> None:
    assert ("b05", "9.4") in rules(picture(_flashed(make_plan(), "b05"), spec))


def test_flashes_are_capped_per_60s_and_never_consecutive(flashy: StyleSpec) -> None:
    """060 (2): at most `broll.flash_max_per_60s` (5) flashes per 60 s of runtime and
    never on two consecutive beats; the violation names the beat that breaks it."""
    plan = make_plan(body_lengths=[2.7] * 20)  # 5 + 54 + 1 = 60.0 s
    assert plan.beats[-1].end == 60.0
    five = _flashed(plan, "b04", "b06", "b08", "b10", "b12")
    checked(five, flashy)
    six = _flashed(five, "b14")
    found = rules(picture(six, flashy))
    assert ("b14", "9.4") in found and ("b12", "9.4") not in found
    in_a_row = _flashed(make_plan(), "b05", "b06")
    assert ("b06", "9.4") in rules(picture(in_a_row, flashy))
    assert ("b05", "9.4") not in rules(picture(in_a_row, flashy))


def test_the_flash_cap_scales_to_the_runtime_rounding_up(flashy: StyleSpec) -> None:
    """The cap is ceil(5 x runtime / 60): 56 s allows 5 and refuses 6; a six-second
    fixture still allows one flash (the fake planner's, under 059's styles)."""
    plan = make_plan()  # 56 s
    assert plan.beats[-1].end == 56.0
    checked(_flashed(plan, "b04", "b06", "b08", "b10", "b12"), flashy)
    assert ("b14", "9.4") in rules(
        picture(_flashed(plan, "b04", "b06", "b08", "b10", "b12", "b14"), flashy)
    )
    assert grammar.flash_cap(flashy, runtime=6.0) == 1
    assert grammar.flash_cap(flashy, runtime=60.0) == 5


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


def test_a_must_use_reference_may_ride_on_a_set_piece_item(spec: StyleSpec) -> None:
    plan = _piece(make_plan(), "b05", "wall", _items(4, asset="ref1"))
    checked(replace(plan, "b05", asset_id="ref1"), spec, must_use=["ref1"])


def test_a_hook_wish_in_the_brief_is_no_longer_a_warning(spec: StyleSpec) -> None:
    """055: the hook wish steers the opening images, never a title; there is no title."""
    brief = "Topic: sky. Hook wish: 3 reasons the sky is blue."
    assert checked(make_plan(), spec, brief=brief).warnings == []


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
    assert ("b05", "9.4") in rules(cued(bare, spec, Cue(beat_id="b05", intent="bass", at="event")))
    assert ("b05", "9.4") in rules(cued(bare, spec, Cue(beat_id="b05", intent="bass", at="start")))
    landed = replace(plan, "b05", enter="whip")  # keeps its stamp
    ok = cued(landed, spec, Cue(beat_id="b05", intent="bass", at="start"))
    assert isinstance(ok, grammar.SoundCheck)


def test_a_whoosh_is_allowed_only_on_a_flash_under_a_style_that_allows_it(
    spec: StyleSpec, flashy: StyleSpec
) -> None:
    """060 (3): a `whoosh` cue at the start of a bare `flash` beat passes the 9.4
    bare-transition rule under the test style; the same cue on a plain cut, at the
    beat's end, or on a whip is rejected naming the beat; under a style that forbids
    whooshes any whoosh is rejected as forbidden (7.3)."""
    plan = replace(make_plan(), "b05", event=Event())  # b05 bare: no landed event
    flashed = replace(plan, "b05", enter="flash")
    whoosh = Cue(beat_id="b05", intent="whoosh", at="start")
    ok = cued(flashed, flashy, whoosh)
    assert isinstance(ok, grammar.SoundCheck) and ok.sound.cues == [whoosh]
    # a floor class on the bare flash is still a cue on a bare transition (9.4)
    hit = Cue(beat_id="b05", intent="bass", at="start")
    assert ("b05", "9.4") in rules(cued(flashed, flashy, hit))
    # a whoosh anywhere else: plain cut, the beat's end, a whip with a stamp
    assert ("b05", "7.3") in rules(cued(plan, flashy, whoosh))
    at_end = Cue(beat_id="b05", intent="whoosh", at="end")
    assert ("b05", "7.3") in rules(cued(flashed, flashy, at_end))
    whipped = replace(make_plan(), "b05", enter="whip")
    assert ("b05", "7.3") in rules(cued(whipped, flashy, whoosh))
    # under a style that forbids whooshes a whoosh is refused outright, however the beat
    # enters (070 gives every shipped style the row; the rule stays for a style without)
    forbidding = flashy.model_copy(deep=True)
    forbidding.sound.forbidden = [*forbidding.sound.forbidden, "whoosh"]
    forbidding.sound.whoosh = None
    found = rules(cued(flashed, forbidding, whoosh))
    assert ("b05", "7.3") in found


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
    ids = [b.id for b in plan.beats if b.event.kind == "stamp"]  # opening + 22 body beats
    cues = [Cue(beat_id=i, intent="bass", at="event") for i in ids[:21]]
    result = sound(story_for(plan, cues=cues), plan, spec)
    assert isinstance(result, grammar.SoundCheck)
    assert len(result.sound.cues) == 20
    assert [c.beat_id for c in result.clamps] == [ids[20]]
    assert result.clamps[0].rule == "7.3"
    bass = Cue(beat_id=ids[0], intent="bass", at="event")
    drum = Cue(beat_id=ids[0], intent="drum", at="start")
    result = cued(plan, spec, bass, drum)
    assert isinstance(result, grammar.SoundCheck)
    assert [c.intent for c in result.sound.cues] == ["bass"]
    assert result.clamps[0].beat_id == ids[0] and result.clamps[0].rule == "7.3"


def test_mood_points_outside_the_runtime_are_rejected(spec: StyleSpec) -> None:
    plan = make_plan()
    curve = [MoodPoint(t=0.0, level=0.0), MoodPoint(t=plan.beats[-1].end + 5, level=0.0)]
    assert (None, "7.3") in rules(sound(story_for(plan, curve=curve), plan, spec))


# --- validate(): both halves, the fixture spec and the fake plan --------------------------


def test_validate_combines_picture_and_sound(spec: StyleSpec) -> None:
    plan = make_plan(keywords=list(range(12)))
    story = story_for(plan, cues=[Cue(beat_id="b05", intent="bass", at="event")])
    result = grammar.validate(plan, story, transcript_for(plan), spec, brief=BRIEF)
    assert isinstance(result, grammar.ValidatedPlan)
    assert result.picture.keywords == [0, 1, 2, 3, 4]
    assert result.sound == story
    assert [c.rule for c in result.clamps] == ["6.1"]
    ghost = story_for(plan, cues=[Cue(beat_id="b99", intent="bass", at="start")])
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
    assert result.picture.cut == plan.cut  # 055: the fixture's pauses are under the scaled maximum
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


# --- the title strip (ticket 059) ----------------------------------------------------------


def _stripped(spec: StyleSpec) -> StyleSpec:
    """The explainer with fastfacts' title strip row: a style that draws the strip."""
    styled = spec.model_copy(deep=True)
    styled.broll.title_strip = render.loaded_styles()["fastfacts"].broll.title_strip
    return styled


def test_a_style_with_a_title_strip_needs_the_topic_in_at_most_its_words(spec: StyleSpec) -> None:
    """059: under a strip style the plan writes `title_strip`, 1 to `words_max` words;
    missing or too long is a 4.1 violation on the plan."""
    stripped = _stripped(spec)
    ok = make_plan().model_copy(update={"title_strip": "Why cheese exists"})
    assert checked(ok, stripped).picture.title_strip == "Why cheese exists"
    assert (None, "4.1") in rules(picture(make_plan(), stripped))
    long = make_plan().model_copy(update={"title_strip": "one two three four five six"})
    result = picture(long, stripped)
    assert rules(result) == {(None, "4.1")}
    assert isinstance(result, grammar.Violations)
    (line,) = result.lines()
    assert "title_strip" in line and "6 words" in line and "5" in line


def test_a_style_without_a_title_strip_refuses_one(spec: StyleSpec) -> None:
    plan = make_plan().model_copy(update={"title_strip": "Why cheese exists"})
    assert rules(picture(plan, spec)) == {(None, "4.1")}
    checked(make_plan(), spec)
