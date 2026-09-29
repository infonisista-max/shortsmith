"""The sound director (ticket 022; decisions 7.1, 7.2, 7.3, 5.4).

The pure half - catalogue, bed selection, floor hits, cue matching, envelope and the
filter strings - is tested on the synthesised catalogue from `conftest.library`; the
mix half runs ffmpeg on that catalogue and the fixture's voice.
"""

from __future__ import annotations

import json
import math
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from shortsmith import ffmpeg, fixture, grammar, render, sound, styles
from shortsmith.contracts import (
    AudioEntry,
    AudioTags,
    BedQuery,
    Cue,
    CueSheet,
    Event,
    MoodPoint,
    PicturePlan,
    SoundStory,
)
from shortsmith.planner import FakePlanner
from tests.conftest import flash_whoosh_style


@pytest.fixture(scope="session")
def nums() -> styles.Sound:
    return render.loaded_styles()[styles.DEFAULT].sound


@pytest.fixture(scope="session")
def plan() -> PicturePlan:
    return FakePlanner().plan_picture(_request())


@pytest.fixture(scope="session")
def story(plan: PicturePlan) -> SoundStory:
    return FakePlanner().plan_sound(_request(), plan)


def _request():  # noqa: ANN202 - only `transcript.duration_s` is read by the fake
    from shortsmith.contracts import Constraints, PlanRequest, PlanStyle, Transcript

    return PlanRequest(
        brief="",
        style=PlanStyle(name="explainer", status="shipped", numbers={}, prose=""),
        style_note="",
        transcript=Transcript(duration_s=fixture.DURATION_S, segments=[], words=[]),
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=6.0),
        asset_policy="any",
    )


# --- the catalogue (7.2) ----------------------------------------------------------------


def test_catalogue_loads_every_field(library: sound.Library) -> None:
    ids = [e.id for e in library.entries]
    assert ids == [b[0] for b in fixture.CATALOGUE_BEDS] + [s[0] for s in fixture.CATALOGUE_SFX]
    bed = library.entry("bed_tech_curious")
    assert bed is not None
    assert bed.kind == "bed"
    assert bed.tags.theme == ["tech", "science"]
    assert bed.tags.mood == ["curious", "bright", "mysterious_curiosity"]  # 076: a closed mood
    assert bed.energy == 3
    assert bed.drop_points_s == [1.0, 3.5]
    assert bed.loop_ok is True
    assert bed.licence == fixture.CATALOGUE_LICENCE
    assert library.file(bed).is_file()


def test_catalogue_tags_are_the_planner_facing_text(library: sound.Library) -> None:
    tags = library.tags()
    assert "tech" in tags and "curious" in tags and "tick" in tags
    assert tags == tuple(sorted(set(tags))), "tags are sorted and unique for the prompt"


def test_the_shipped_catalogue_loads(tmp_path: Path) -> None:
    """`assets/audio/catalog.yaml` is in the repo and parses; it is empty until 025."""
    shipped = sound.load_catalogue()
    assert isinstance(shipped, sound.Library)
    empty = tmp_path / "catalog.yaml"
    empty.write_text("entries: []\n", encoding="utf-8")
    assert sound.load_catalogue(empty).entries == ()


def test_a_missing_catalogue_is_an_empty_library(tmp_path: Path) -> None:
    assert sound.load_catalogue(tmp_path / "nope.yaml").entries == ()


def test_a_broken_catalogue_names_the_problem(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text("entries:\n  - id: x\n    kind: bed\n", encoding="utf-8")
    with pytest.raises(sound.SoundError, match="catalog.yaml"):
        sound.load_catalogue(path)


# --- bed selection (7.2) ----------------------------------------------------------------


def test_bed_selected_by_tag_overlap_then_energy(
    library: sound.Library, nums: styles.Sound
) -> None:
    threshold = nums.bed_score_threshold
    query = BedQuery(theme="tech", mood="curious", energy=3)
    chosen = sound.select_bed(library, query, first_stamp_s=1.0, threshold=threshold)
    assert chosen is not None and chosen.id == "bed_tech_curious"
    # One tag less, and the energy pulls the choice to the other tech bed.
    other = sound.select_bed(library, BedQuery(theme="tech", mood="tense", energy=4),
                             first_stamp_s=1.0, threshold=threshold)  # fmt: skip
    assert other is not None and other.id == "bed_tech_tense"


def test_bed_tie_is_broken_by_drop_point_fit(library: sound.Library, nums: styles.Sound) -> None:
    """Same tags and the same energy: the bed whose drop lands nearest the first stamp."""
    near = library.entry("bed_tech_curious")
    assert near is not None
    far = near.model_copy(update={"id": "bed_tech_far", "drop_points_s": [7.5]})
    tied = sound.Library(root=library.root, entries=(near, far))
    query = BedQuery(theme="tech", mood="curious", energy=3)
    threshold = nums.bed_score_threshold
    assert sound.select_bed(tied, query, first_stamp_s=3.4, threshold=threshold) is near
    assert sound.select_bed(tied, query, first_stamp_s=7.4, threshold=threshold) is far


def test_no_tag_hit_is_below_the_threshold(library: sound.Library, nums: styles.Sound) -> None:
    query = BedQuery(theme="cooking", mood="nostalgic", energy=3)
    assert (
        sound.select_bed(library, query, first_stamp_s=1.0, threshold=nums.bed_score_threshold)
        is None
    )


def test_the_threshold_is_the_styles_number(library: sound.Library, nums: styles.Sound) -> None:
    """024: `sound.bed_score_threshold` comes from the front matter, never from code. A tag
    hit scores 1 and the energy distance at most 0.4, so the shipped 0.5 reads "at least
    one tag matched"; a style that asks for both tags (1.5) sends a one-tag bed to the
    search, and a style asking for none (0) keeps it."""
    assert nums.bed_score_threshold == 0.5
    one_tag = BedQuery(theme="tech", mood="nostalgic", energy=3)
    assert sound.select_bed(library, one_tag, first_stamp_s=1.0, threshold=0.5) is not None
    assert sound.select_bed(library, one_tag, first_stamp_s=1.0, threshold=1.5) is None
    none = BedQuery(theme="cooking", mood="nostalgic", energy=3)
    assert sound.select_bed(library, none, first_stamp_s=1.0, threshold=0.0) is not None


def test_below_the_threshold_the_search_adapter_is_asked(
    library: sound.Library, nums: styles.Sound
) -> None:
    """7.2: below the score threshold the audio search runs with the query's keywords;
    the fake returns seeded catalogue entries only and records that it was asked."""
    search = sound.FakeAudioSearch()
    query = BedQuery(theme="cooking", mood="nostalgic", energy=1)
    chosen, lines = sound.choose_bed(
        library, query, first_stamp_s=1.0, threshold=nums.bed_score_threshold, search=search,
        default_query=nums.default_bed_query,
    )  # fmt: skip
    assert chosen is not None and chosen.id in {e.id for e in library.beds()}
    assert any("from the audio search" in line for line in lines)
    assert search.calls == ["cooking nostalgic"], "the first rung adopted, so the ladder stopped"


# --- 054: the bed search ladder, specific to broad -----------------------------------------

F1_QUERY = BedQuery(
    theme="Himalayan spiritual documentary, tanpura drone with soft tabla pulse and low synth",
    mood="mysterious, contemplative, quietly insistent, investigative",
    energy=3,
)
DEFAULT_BED = "cinematic ambient documentary"


def test_bed_queries_run_specific_to_broad_and_end_with_the_style_default() -> None:
    """054 (2): plain keywords from the theme and the mood, then the mood alone, then
    the style's default words; every rung at most six words, never the full sentence."""
    rungs = sound.bed_queries(F1_QUERY, DEFAULT_BED)
    assert len(rungs) >= 3 and len(set(rungs)) == len(rungs)
    assert all(1 <= len(r.split()) <= sound.QUERY_MAX_WORDS for r in rungs), rungs
    assert rungs[0] == "himalayan spiritual documentary mysterious contemplative quietly"
    assert "mysterious contemplative quietly" in rungs, "a mood-only rung"
    assert rungs[-1] == DEFAULT_BED, "the style default is the last try"
    assert rungs.index("mysterious contemplative quietly") < rungs.index(DEFAULT_BED)
    lengths = [len(r.split()) for r in rungs[:-1]]  # the default is last whatever its length
    assert lengths == sorted(lengths, reverse=True), "specific to broad: never longer again"
    assert F1_QUERY.theme not in rungs and F1_QUERY.mood not in rungs
    assert all("," not in r and r == r.lower() for r in rungs)


def test_keywords_drop_stopwords_punctuation_and_repeats() -> None:
    assert sound.keywords("The drone, with a Drone and the tabla!") == ["drone", "tabla"]
    assert sound.keywords("") == []


def test_choose_bed_walks_the_whole_ladder_when_nothing_is_adopted(
    library: sound.Library, nums: styles.Sound
) -> None:
    """054 (1, 2): with an empty shelf the fake adopts nothing, so every rung is tried in
    order and every search is one log line with its status and hit count."""
    no_beds = sound.Library(root=library.root, entries=tuple(library.sfx()))
    search = sound.FakeAudioSearch()
    chosen, lines = sound.choose_bed(
        no_beds, F1_QUERY, first_stamp_s=1.0, threshold=nums.bed_score_threshold,
        search=search, default_query=DEFAULT_BED,
    )  # fmt: skip
    assert chosen is None
    assert search.calls == list(sound.bed_queries(F1_QUERY, DEFAULT_BED))
    searched = [line for line in lines if line.startswith("audio search ")]
    assert len(searched) == len(search.calls)
    for line, words in zip(searched, search.calls, strict=True):
        assert repr(words) in line and "status 200" in line and "0 hits" in line
    assert "every audio search came back empty" in lines[-1]


def test_choose_bed_stops_at_the_first_adoption(
    library: sound.Library, nums: styles.Sound
) -> None:
    search = sound.FakeAudioSearch(shelf=library)
    no_beds = sound.Library(root=library.root, entries=tuple(library.sfx()))
    chosen, lines = sound.choose_bed(
        no_beds, F1_QUERY, first_stamp_s=1.0, threshold=nums.bed_score_threshold,
        search=search, default_query=DEFAULT_BED,
    )  # fmt: skip
    assert chosen is not None and chosen.id in {e.id for e in library.beds()}
    assert search.calls == [sound.bed_queries(F1_QUERY, DEFAULT_BED)[0]]
    assert any(f"bed {chosen.id} from the audio search" in line for line in lines)


def test_without_a_search_the_bed_note_says_no_audio_search_configured(
    library: sound.Library, nums: styles.Sound
) -> None:
    chosen, lines = sound.choose_bed(
        library, F1_QUERY, first_stamp_s=1.0, threshold=nums.bed_score_threshold,
        default_query=DEFAULT_BED,
    )  # fmt: skip
    assert chosen is None and any("no audio search configured" in line for line in lines)


# --- 054 (3): SFX from the search when the catalogue has no match --------------------------


def test_sfx_queries_are_the_intent_words_and_a_floor_class_tries_hit_first() -> None:
    assert sound.sfx_queries("reveal_drop") == ("reveal drop",)
    assert sound.sfx_queries("bass") == ("bass hit", "bass")
    assert sound.sfx_queries("drum") == ("drum hit", "drum")
    assert sound.sfx_queries("thump") == ("thump hit", "thump")
    assert sound.sfx_queries("") == ()
    long = sound.sfx_queries("a_b_c_d_e_f_g_h")
    assert long and all(len(r.split()) <= sound.QUERY_MAX_WORDS for r in long)


def test_every_placed_cue_has_its_line(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    placed = sound.place_cues(plan, story, library, nums, runtime_s=60.0)
    assert placed.cues
    placed_lines = [n for n in placed.notes if "placed at" in n]
    assert len(placed_lines) == len(placed.cues), "one line per placed cue (054 (1))"


def test_an_empty_approved_library_places_nothing_and_says_so(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    """070: effects come only from the approved library; with none there is no cue, and
    nothing is searched for (`place_cues` takes no search at all)."""
    empty = sound.Library(root=library.root, entries=())
    placed = sound.place_cues(plan, story, empty, nums, runtime_s=60.0)
    assert placed.cues == ()
    assert any(sound.NO_APPROVED_LINE in n for n in placed.notes)


def test_above_the_threshold_the_search_adapter_is_never_asked(
    library: sound.Library, nums: styles.Sound
) -> None:
    """024: the search is the fallback, not a second opinion; a library bed over the
    threshold is taken without a call."""
    search = sound.FakeAudioSearch()
    query = BedQuery(theme="tech", mood="curious", energy=3)
    chosen, _ = sound.choose_bed(
        library, query, first_stamp_s=1.0, threshold=nums.bed_score_threshold, search=search
    )
    assert chosen is not None and chosen.id == "bed_tech_curious"
    assert search.calls == []


def test_without_a_search_adapter_there_is_simply_no_bed(
    library: sound.Library, nums: styles.Sound
) -> None:
    chosen, lines = sound.choose_bed(
        library, BedQuery(theme="cooking", mood="nostalgic", energy=1), first_stamp_s=1.0,
        threshold=nums.bed_score_threshold,
    )  # fmt: skip
    assert chosen is None and any("no bed" in line for line in lines)


# --- the floor hits (7.1) ---------------------------------------------------------------


def test_floor_hits_from_the_plan_events(plan: PicturePlan, nums: styles.Sound) -> None:
    hits = {h.beat_id: h for h in sound.floor_hits(plan, nums)}
    # 058: b02 is the plan's card (on a whip with a lower-third, neither of which earns a
    # hit); the card flies in, so it earns the thump.
    assert hits["b02"].hit == "thump" and hits["b02"].trigger == "card_fly_in"
    assert "b03" not in hits  # 055: the full beat has no landed event
    # 058: b04 is the clip beat; a clip covers the frame like a photo and flies nothing
    # in, so its stamp is its one trigger.
    assert hits["b04"].hit == "bass" and hits["b04"].trigger == "stamp"
    assert sound.beat_triggers(plan)["b04"] == ("stamp",)
    assert hits["b06"].hit == "drum" and hits["b06"].trigger == "money_reveal"
    assert hits["b08"].hit == "bass" and hits["b08"].trigger in ("header", "reveal")
    assert hits["b10"].hit == "thump"
    assert hits["b11"].hit == "drum" and hits["b11"].trigger == "finale_word"
    assert all(h.at_s == next(b.start for b in plan.beats if b.id == h.beat_id) for h in
               sound.floor_hits(plan, nums))  # fmt: skip


def test_nothing_on_whips_punch_ins_rings_or_lower_thirds(
    plan: PicturePlan, nums: styles.Sound
) -> None:
    """7.1: the four events that never earn a hit. b03 is a `full` punch-in, b05 a map
    with no event; b02 enters on a whip and carries a lower-third (as a `photo` there is
    nothing to earn a hit from; 058 plans it as a card, whose fly-in is the one thing that
    does); a card that enters on a whip with a ring earns its thump from the card it
    flies in, never from either of those."""
    as_photo = plan.model_copy(
        update={
            "beats": [
                b.model_copy(update={"kind": "photo", "motion": "ken_burns_in"})
                if b.id == "b02"
                else b
                for b in plan.beats
            ]
        }
    )
    hit_ids = {h.beat_id for h in sound.floor_hits(as_photo, nums)}
    assert "b02" not in hit_ids and "b03" not in hit_ids and "b05" not in hit_ids
    ringed = plan.model_copy(
        update={
            "beats": [
                b.model_copy(update={"kind": "card", "motion": "push_in", "enter": "whip",
                                     "event": Event(kind="ring")})  # fmt: skip
                if b.id == "b02"
                else b
                for b in plan.beats
            ]
        }
    )
    hits = {h.beat_id: h for h in sound.floor_hits(ringed, nums)}
    assert hits["b02"].hit == "thump" and hits["b02"].trigger == "card_fly_in"
    bare = ringed.model_copy(
        update={
            "beats": [
                b.model_copy(update={"kind": "photo", "motion": "ken_burns_in"})
                if b.id == "b02"
                else b
                for b in ringed.beats
            ]
        }
    )
    assert "b02" not in {h.beat_id for h in sound.floor_hits(bare, nums)}


def test_a_transition_earns_only_a_whoosh(
    plan: PicturePlan, library: sound.Library, nums: styles.Sound
) -> None:
    """9.4 / 7.1 (030) as amended by 070: a whip on every beat, no events, no planner
    cues and a flat mood curve place the floor and, beyond it, only the whooshes the
    style's row allows on those enters (at most `max_per_60s`, `min_gap_s` apart); the
    same plan entering on cuts places the floor alone."""

    def entering(enter: str) -> PicturePlan:
        return plan.model_copy(
            update={
                "beats": [
                    b.model_copy(update={"enter": enter, "event": Event(kind="none"),
                                         "counter": None})  # fmt: skip
                    for b in plan.beats
                ]
            }
        )

    whipped, cut = entering("whip"), entering("cut")
    assert all(b.enter == "whip" for b in whipped.beats)
    silent = SoundStory(
        prompt_version="t", theme="t",
        mood_curve=[MoodPoint(t=0.0, level=0.0), MoodPoint(t=6.0, level=0.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3), cues=[],
    )  # fmt: skip
    placed = sound.place_cues(whipped, silent, library, nums, runtime_s=60.0)
    floor = {h.beat_id for h in sound.floor_hits(whipped, nums)}
    assert {c.beat_id for c in placed.cues if c.hit != "whoosh"} == floor
    assert all(c.source == "floor" for c in placed.cues)
    whooshes = [c for c in placed.cues if c.hit == "whoosh"]
    assert whooshes and all(c.beat_id not in floor for c in whooshes)
    assert nums.whoosh is not None
    gaps = [b.at_s - a.at_s for a, b in zip(whooshes, whooshes[1:], strict=False)]
    assert all(g >= nums.whoosh.min_gap_s - 1e-9 for g in gaps)
    on_cuts = sound.place_cues(cut, silent, library, nums, runtime_s=60.0)
    assert {c.beat_id for c in on_cuts.cues} == floor and on_cuts.cues == tuple(
        c for c in placed.cues if c.hit != "whoosh"
    )


def test_the_floor_classes_come_from_the_style(plan: PicturePlan, nums: styles.Sound) -> None:
    """The hit class per event is the style's `sound.floor_hits`, never code."""
    swapped = nums.model_copy(
        update={"floor_hits": {"drum": ["stamp"], "bass": ["money_reveal"], "thump": []}}
    )
    hits = {h.beat_id: h.hit for h in sound.floor_hits(plan, swapped)}
    assert hits["b04"] == "drum" and hits["b06"] == "bass"
    assert "b10" not in hits, "card_fly_in (the wall) earns nothing when the style drops it"


LAND_S = 0.16  # the stamp's land time, which the counter lands in (029)


def test_a_counter_lands_with_the_stamps_bass_at_its_landing(
    plan: PicturePlan, nums: styles.Sound
) -> None:
    """029: the counter is a stamp-style landing, so it earns the stamp's floor class,
    and the hit fires where the digits land - the last `LAND_S` of the beat - not at
    the beat's start."""
    plain = plan.model_copy(
        update={"beats": [b.model_copy(update={"money_reveal": False}) if b.id == "b06" else b
                          for b in plan.beats]}  # fmt: skip
    )
    b06 = next(b for b in plain.beats if b.id == "b06")
    assert b06.counter is not None and b06.event.kind == "none"
    hits = {h.beat_id: h for h in sound.floor_hits(plain, nums, counter_land_s=LAND_S)}
    assert hits["b06"].hit == "bass" and hits["b06"].trigger == "stamp"
    assert hits["b06"].at_s == pytest.approx(b06.end - LAND_S)
    # the money reveal outranks it (7.1) and still lands on the counter's landing
    money = {h.beat_id: h for h in sound.floor_hits(plan, nums, counter_land_s=LAND_S)}
    assert money["b06"].hit == "drum" and money["b06"].at_s == pytest.approx(b06.end - LAND_S)


def test_an_event_cue_on_a_text_pop_fires_where_the_pop_lands(
    plan: PicturePlan, library: sound.Library, nums: styles.Sound
) -> None:
    """061 (6): on a beat with no landed event that carries text pops, an `event` cue
    fires at the first pop's `at_s` (the validated plan's output time), not at the
    beat's start; a pop earns no floor hit of its own (7.1's floor is unchanged)."""
    from shortsmith.contracts import TextPop

    pops = [TextPop(text="THIS", word=2, x=50.0, y=42.0, at_s=1.2)]
    popped = plan.model_copy(update={"beats": [
        b.model_copy(update={"text_pops": pops}) if b.id == "b03" else b for b in plan.beats
    ]})  # fmt: skip
    b03 = next(b for b in popped.beats if b.id == "b03")
    assert sound.landing_s(b03, None) == 1.2 and b03.start == 1.0
    assert "b03" not in {h.beat_id for h in sound.floor_hits(popped, nums)}
    story = SoundStory(
        prompt_version="t", theme="t", mood_curve=[MoodPoint(t=0.0, level=0.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3),
        cues=[Cue(beat_id="b03", intent="tick", at="event")],
    )  # fmt: skip
    # the fixture-shaped cap (nine cues in 6 s): under the shipped 20 per 60 s only two
    # survive, the classed floor hits, so the soft tick would be cut for cost
    judged = fixture.smoke_specs(render.loaded_styles())[styles.DEFAULT].sound
    placed = sound.place_cues(popped, story, library, judged, runtime_s=6.0)
    cue = next(c for c in placed.cues if c.beat_id == "b03")
    assert (cue.at_s, cue.entry_id, cue.source) == (1.2, "sfx_tick", "planner")
    # a pop whose landing the grammar never wrote (an unvalidated plan) fires at the start
    unwritten = b03.model_copy(update={"text_pops": [pops[0].model_copy(update={"at_s": None})]})
    assert sound.landing_s(unwritten, None) == 1.0


def test_an_event_cue_on_a_bubble_fires_where_the_first_bubble_lands(
    plan: PicturePlan, library: sound.Library, nums: styles.Sound
) -> None:
    """063 (5): on a beat with no landed event that carries bubbles, an `event` cue
    fires at the first bubble's `at_s` (the validated plan's output time), not at the
    beat's start; a bubble earns no floor hit of its own; a beat carrying both text
    pops and bubbles lands on its first pop."""
    from shortsmith.contracts import Bubble, TextPop

    bubbles = [
        Bubble(text="Hello there?", first=0, last=1, x=19.4, y=50.0, at_s=1.15),
        Bubble(shape="thought", text="This is", first=2, last=3, x=62.0, y=30.0, at_s=1.35),
    ]
    bubbled = plan.model_copy(update={"beats": [
        b.model_copy(update={"bubbles": bubbles}) if b.id == "b03" else b for b in plan.beats
    ]})  # fmt: skip
    b03 = next(b for b in bubbled.beats if b.id == "b03")
    assert sound.landing_s(b03, None) == 1.15 and b03.start == 1.0
    assert "b03" not in {h.beat_id for h in sound.floor_hits(bubbled, nums)}
    story = SoundStory(
        prompt_version="t", theme="t", mood_curve=[MoodPoint(t=0.0, level=0.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3),
        cues=[Cue(beat_id="b03", intent="tick", at="event")],
    )  # fmt: skip
    judged = fixture.smoke_specs(render.loaded_styles())[styles.DEFAULT].sound
    placed = sound.place_cues(bubbled, story, library, judged, runtime_s=6.0)
    cue = next(c for c in placed.cues if c.beat_id == "b03")
    assert (cue.at_s, cue.entry_id, cue.source) == (1.15, "sfx_tick", "planner")
    unwritten = b03.model_copy(update={"bubbles": [bubbles[0].model_copy(update={"at_s": None})]})
    assert sound.landing_s(unwritten, None) == 1.0
    pop = TextPop(text="THIS", word=2, x=50.0, y=42.0, at_s=1.2)
    assert sound.landing_s(b03.model_copy(update={"text_pops": [pop]}), None) == 1.2


def test_an_event_cue_on_a_sticker_fires_where_it_lands(plan: PicturePlan) -> None:
    """062 (5): a ding or pop cue at the `event` of a beat with no landed event that
    carries a sticker fires at the sticker's `at_s`; a text pop or a bubble on the same
    beat lands first; an unwritten `at_s` is the beat's start."""
    from shortsmith.contracts import Bubble, Sticker

    sticker = Sticker(intent="idea", name="Light bulb", word=2, at_s=1.3)
    b03 = next(b for b in plan.beats if b.id == "b03").model_copy(update={"stickers": [sticker]})
    assert sound.landing_s(b03, None) == 1.3 and b03.start == 1.0
    bubble = Bubble(text="Hello?", first=0, last=1, x=19.4, y=50.0, at_s=1.1)
    assert sound.landing_s(b03.model_copy(update={"bubbles": [bubble]}), None) == 1.1
    unwritten = b03.model_copy(update={"stickers": [sticker.model_copy(update={"at_s": None})]})
    assert sound.landing_s(unwritten, None) == 1.0


def test_an_event_cue_on_a_counter_fires_at_its_landing(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    placed = sound.place_cues(plan, story, library, nums, runtime_s=6.0, counter_land_s=LAND_S)
    cue = next(c for c in placed.cues if c.beat_id == "b06")
    b06 = next(b for b in plan.beats if b.id == "b06")
    assert cue.source == "planner" and cue.at_s == pytest.approx(b06.end - LAND_S)


# --- cues (7.1, 7.3) --------------------------------------------------------------------


def test_cue_intents_match_sfx_by_tag(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    placed = sound.place_cues(plan, story, library, nums, runtime_s=6.0)
    by_beat = {c.beat_id: c for c in placed.cues}
    assert by_beat["b06"].entry_id == "sfx_drum_hit", "the money intent matched its tag"
    assert by_beat["b06"].source == "planner"
    assert by_beat["b11"].entry_id == "sfx_drum_hit"


def test_an_intent_outside_the_palette_is_dropped_and_the_floor_still_lands(
    plan: PicturePlan, library: sound.Library, nums: styles.Sound
) -> None:
    """070: a name outside the palette (the grammar refuses it first) is never matched;
    the beat's own floor hit still lands."""
    story = SoundStory(
        prompt_version="t", theme="t", mood_curve=[MoodPoint(t=0.0, level=0.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3),
        cues=[Cue(beat_id="b06", intent="nothing_matches_this", at="event")],
    )  # fmt: skip
    placed = sound.place_cues(plan, story, library, nums, runtime_s=6.0)
    cue = next(c for c in placed.cues if c.beat_id == "b06")
    assert (cue.hit, cue.entry_id, cue.source) == ("drum", "sfx_drum_hit", "floor")
    assert any("nothing_matches_this" in n and "outside the sound palette" in n
               for n in placed.notes)  # fmt: skip


# --- whooshes (ticket 060; 7.3 as amended) -------------------------------------------------


def _flashed(plan: PicturePlan, beat_id: str = "b03") -> PicturePlan:
    return plan.model_copy(
        update={
            "beats": [
                b.model_copy(update={"enter": "flash"}) if b.id == beat_id else b
                for b in plan.beats
            ]
        }
    )


def _whoosh_story(beat_id: str = "b03") -> SoundStory:
    return SoundStory(
        prompt_version="t", theme="t", mood_curve=[MoodPoint(t=0.0, level=0.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3),
        cues=[Cue(beat_id=beat_id, intent="whoosh", at="start")],
    )  # fmt: skip


@pytest.fixture(scope="session")
def whooshy() -> styles.Sound:
    return flash_whoosh_style(render.loaded_styles()[styles.DEFAULT]).sound


def test_the_fixture_catalogue_carries_a_short_whoosh(library: sound.Library) -> None:
    """The synthesised catalogue has one SFX tagged `whoosh` under 060's `max_len_s`,
    so the fake planner's whoosh resolves; `match_sfx` can refuse a longer file."""
    entry = sound.match_sfx("whoosh", library)
    assert entry is not None and entry.id == "sfx_whoosh" and entry.duration_s <= 0.8
    assert sound.match_sfx("whoosh", library, max_duration_s=0.8) == entry
    assert sound.match_sfx("whoosh", library, max_duration_s=0.3) is None


def test_a_whoosh_cue_is_placed_on_a_flash_under_a_style_that_allows_it(
    plan: PicturePlan, library: sound.Library, nums: styles.Sound, whooshy: styles.Sound
) -> None:
    """060 (3, 5) as amended by 070: under the test style the planner's whoosh on the
    flash beat is placed from the library's `whoosh` tag at the whoosh level; under a
    style that forbids whooshes the same cue is dropped with a note, never resolved."""
    flashed = _flashed(plan)
    placed = sound.place_cues(flashed, _whoosh_story(), library, whooshy, runtime_s=60.0)
    whooshes = [c for c in placed.cues if c.intent == "whoosh" and c.source == "planner"]
    assert len(whooshes) == 1
    cue = whooshes[0]
    assert (cue.beat_id, cue.entry_id, cue.hit) == ("b03", "sfx_whoosh", "whoosh")
    assert cue.gain_db == sound.cue_level_db("whoosh", whooshy)
    assert cue.at_s == next(b.start for b in flashed.beats if b.id == "b03")
    forbidding = nums.model_copy(update={"forbidden": [*nums.forbidden, "whoosh"], "whoosh": None})
    kept = sound.place_cues(flashed, _whoosh_story(), library, forbidding, runtime_s=60.0)
    assert not [c for c in kept.cues if c.intent == "whoosh"]
    assert any("b03" in n and "whoosh" in n and "forbidden" in n for n in kept.notes)


def test_a_library_whoosh_over_the_allowance_length_is_not_taken(
    plan: PicturePlan, library: sound.Library, whooshy: styles.Sound
) -> None:
    short = library.entry("sfx_whoosh")
    assert short is not None
    long = short.model_copy(update={"id": "sfx_whoosh_long", "duration_s": 1.5})
    only_long = sound.Library(
        root=library.root,
        entries=(*(e for e in library.entries if e.id != "sfx_whoosh"), long),
    )
    placed = sound.place_cues(_flashed(plan), _whoosh_story(), only_long, whooshy, runtime_s=60.0)
    assert not [c for c in placed.cues if c.intent == "whoosh"]
    assert any("no approved sfx for 'whoosh' no longer than 0.8 s" in n for n in placed.notes)


def test_one_cue_per_beat_and_the_planner_wins_the_slot(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    placed = sound.place_cues(plan, story, library, nums, runtime_s=60.0)
    ids = [c.beat_id for c in placed.cues]
    assert len(ids) == len(set(ids)), "sound.cues_per_beat_max is 1"
    assert [c.at_s for c in placed.cues] == sorted(c.at_s for c in placed.cues)
    by_beat = {c.beat_id: c for c in placed.cues}
    # The five beats the fake story cues are the planner's; the rest come from the floor
    # and (070) the whooshes the director derives: b03's fade, then b09's zoom 3 s on
    # (b05's fade and b08's spring fall inside `sound.whoosh.min_gap_s`).
    assert {b: (c.source, c.hit) for b, c in by_beat.items()} == {
        "b01": ("planner", "bass"), "b02": ("planner", "thump"), "b03": ("floor", "whoosh"),
        "b04": ("planner", "bass"), "b06": ("planner", "drum"), "b08": ("floor", "bass"),
        "b09": ("floor", "whoosh"), "b10": ("floor", "thump"), "b11": ("planner", "drum"),
    }  # fmt: skip
    assert by_beat["b10"].entry_id == "sfx_thump", "a floor cue plays its class's sample"


def test_the_twenty_first_cue_is_dropped(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    """7.3: `cues_max_per_60s` counts the floor hits too; the floor is kept first, drum
    before bass before thump, and the planner's extras fill what is left."""
    cap = sound.cue_cap(nums, runtime_s=60.0)
    assert cap == nums.cues_max_per_60s
    wide = sound.place_cues(plan, story, library, nums, runtime_s=60.0)
    tight = sound.place_cues(plan, story, library, nums, runtime_s=6.0)
    assert sound.cue_cap(nums, runtime_s=6.0) == 2
    assert len(tight.cues) == 2 < len(wide.cues)
    assert [c.hit for c in tight.cues] == ["drum", "drum"], "the drums outrank the rest"
    assert any("dropped" in n for n in tight.notes)


def test_a_drop_places_its_changeover_cue(
    plan: PicturePlan, library: sound.Library, nums: styles.Sound
) -> None:
    """7.3: a drop is a step at a beat boundary followed by a changeover cue, so the
    director places one on the beat the step lands on; 070: it plays the approved bass."""
    boundary = plan.beats[6].start
    story = SoundStory(
        prompt_version="t", theme="t",
        mood_curve=[MoodPoint(t=0.0, level=2.0), MoodPoint(t=boundary - 0.1, level=2.0),
                    MoodPoint(t=boundary, level=-8.0), MoodPoint(t=6.0, level=-8.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3), cues=[],
    )  # fmt: skip
    placed = sound.place_cues(plan, story, library, nums, runtime_s=60.0)
    cue = next(c for c in placed.cues if c.beat_id == plan.beats[6].id)
    assert (cue.intent, cue.hit, cue.source) == ("changeover", "changeover", "floor")
    assert cue.entry_id == "sfx_bass_hit" and sound.cue_kind(cue) == "bass"
    assert cue.gain_db == sound.cue_level_db("bass", nums), "a changeover sits with the bass"


def test_every_cue_sits_in_the_style_band(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    placed = sound.place_cues(plan, story, library, nums, runtime_s=60.0)
    assert placed.cues
    for cue in placed.cues:
        assert nums.cue_db_min <= cue.gain_db <= nums.cue_db_max
    classes = {c.hit: c.gain_db for c in placed.cues if c.hit}
    assert classes["drum"] == nums.cue_db_max, "the drum is the loudest class"
    assert classes["drum"] > classes["bass"] > classes["thump"]


def test_a_catalogue_with_no_sfx_places_no_cue(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    beds_only = sound.Library(root=library.root, entries=tuple(library.beds()))
    placed = sound.place_cues(plan, story, beds_only, nums, runtime_s=60.0)
    assert placed.cues == ()
    assert any(sound.NO_APPROVED_LINE in n for n in placed.notes)


# --- the mood envelope (7.3) ------------------------------------------------------------


def test_the_envelope_follows_the_clamped_curve(story: SoundStory, nums: styles.Sound) -> None:
    points = sound.envelope(story, nums, runtime_s=6.0)
    assert points[0].t == 0.0 and points[-1].t == pytest.approx(6.0)
    assert all(nums.drop_min_db <= p.level_db <= nums.swell_max_db for p in points)


def test_the_envelope_is_clipped_at_the_style_bounds(nums: styles.Sound) -> None:
    """The grammar clips the planner's curve; the director clips again so a story that
    never met the validator (a hand-written one) cannot push the bed past the bounds."""
    story = SoundStory(
        prompt_version="t", theme="t",
        mood_curve=[MoodPoint(t=0.0, level=99.0), MoodPoint(t=6.0, level=-99.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3), cues=[],
    )  # fmt: skip
    points = sound.envelope(story, nums, runtime_s=6.0)
    assert points[0].level_db == nums.swell_max_db
    assert points[-1].level_db == nums.drop_min_db


def test_a_drop_is_a_step_at_the_beat_boundary(nums: styles.Sound) -> None:
    """7.3: a fall faster than `ramp_min_s` holds its level until the boundary and steps
    there, and the step schedules a changeover cue."""
    story = SoundStory(
        prompt_version="t", theme="t",
        mood_curve=[MoodPoint(t=0.0, level=2.0), MoodPoint(t=3.0, level=2.0),
                    MoodPoint(t=3.2, level=-8.0), MoodPoint(t=6.0, level=-8.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3), cues=[],
    )  # fmt: skip
    points = sound.envelope(story, nums, runtime_s=6.0)
    held = [p for p in points if p.t < 3.2 - 1e-9]
    assert held[-1].level_db == 2.0, "the level holds until the step"
    assert max(p.t for p in points if p.level_db == 2.0) == pytest.approx(3.2 - sound.STEP_S)
    assert sound.changeover_times(story, nums, runtime_s=6.0) == (3.2,)


def test_a_ramp_under_ramp_min_s_never_reaches_the_director(
    plan: PicturePlan, nums: styles.Sound
) -> None:
    """7.3 / 8.2: the validator rejects a rise faster than `ramp_min_s`, so the envelope
    the director builds only ever holds legal ramps and drops at boundaries."""
    spec = render.loaded_styles()[styles.DEFAULT]
    story = SoundStory(
        prompt_version="t", theme="t",
        mood_curve=[MoodPoint(t=0.0, level=-8.0), MoodPoint(t=0.4, level=4.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3), cues=[],
    )  # fmt: skip
    rejected = grammar.validate_sound(story, plan, spec)
    assert isinstance(rejected, grammar.Violations)
    assert any(f"ramp_min_s {nums.ramp_min_s:g}" in line for line in rejected.lines())


def test_a_ramp_is_left_alone(nums: styles.Sound) -> None:
    story = SoundStory(
        prompt_version="t", theme="t",
        mood_curve=[MoodPoint(t=0.0, level=2.0), MoodPoint(t=4.0, level=-8.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3), cues=[],
    )  # fmt: skip
    points = sound.envelope(story, nums, runtime_s=6.0)
    assert [(p.t, p.level_db) for p in points[:2]] == [(0.0, 2.0), (4.0, -8.0)]
    assert sound.changeover_times(story, nums, runtime_s=6.0) == ()


def test_the_volume_expression_reads_the_envelope(nums: styles.Sound) -> None:
    points = (sound.EnvelopePoint(t=0.0, level_db=0.0), sound.EnvelopePoint(t=2.0, level_db=-6.0))
    expr = sound.volume_expr(points)
    assert expr.startswith("exp(")
    # The dB expression evaluated in Python is the piecewise line the filter draws.
    for t, want in ((0.0, 0.0), (1.0, -3.0), (2.0, -6.0), (5.0, -6.0)):
        assert sound.eval_db(points, t) == pytest.approx(want)
    assert "lt(t,2)" in expr


# --- the mix graph (7.3, research S5) ---------------------------------------------------


def test_the_duck_filter_is_the_research_graph(nums: styles.Sound) -> None:
    assert sound.duck_filter() == (
        "sidechaincompress=threshold=0.06:ratio=2:attack=20:release=400"
    )


def test_the_master_targets_are_unchanged() -> None:
    assert (render.MASTER_LUFS, render.MASTER_TP) == (-14.0, -1.5)
    assert render.LIMITER == 0.891


def test_the_sfx_graph_delays_every_cue(library: sound.Library) -> None:
    cues = (
        sound.PlacedCue(beat_id="b1", at_s=0.5, intent="i", hit="bass",
                        entry_id="sfx_bass_hit", gain_db=-4.0, source="floor"),
        sound.PlacedCue(beat_id="b2", at_s=2.25, intent="i", hit="drum",
                        entry_id="sfx_drum_hit", gain_db=-2.0, source="planner"),
    )  # fmt: skip
    graph = sound.sfx_graph(cues, gains_db=(3.0, 4.0), runtime_s=6.0)
    assert "adelay=delays=500:all=1" in graph
    assert "adelay=delays=2250:all=1" in graph
    assert "amix=inputs=2" in graph
    assert "atrim=0:6" in graph


# --- the mix, measured (7.3) ------------------------------------------------------------


# `voice` (the fixture's tone bursts as the renderer's voice stem) lives in conftest (076).


def test_build_mix_writes_the_three_stems_and_the_balance(
    tmp_path: Path, voice: Path, plan: PicturePlan, story: SoundStory,
    library: sound.Library, nums: styles.Sound,
) -> None:  # fmt: skip
    stems = tmp_path / "stems"
    stems.mkdir()
    shutil.copy(voice, stems / "voice.wav")  # what `render.voice_stem` leaves (005)
    result = sound.build_mix(
        stems=stems, voice=stems / "voice.wav", plan=plan, story=story, nums=nums,
        library=library, runtime_s=fixture.DURATION_S,
    )  # fmt: skip
    for name in ("voice.wav", "music.wav", "sfx.wav"):
        assert (stems / name).is_file(), f"{name} was not written"
    assert result.bed is not None and result.bed.id == "bed_tech_curious"
    assert result.cues, "the fixture short has at least one cue"
    sheet = sound.cue_sheet(stems)  # 023: what T6 names a sweep hit by
    assert sheet is not None
    assert [(c.beat_id, c.entry_id, c.start_s) for c in sheet.cues] == [
        (c.beat_id, c.entry_id, c.at_s) for c in result.cues
    ]
    for record in sheet.cues:
        entry = library.entry(record.entry_id)
        assert entry is not None
        assert record.end_s == pytest.approx(
            min(record.start_s + entry.duration_s, fixture.DURATION_S)
        )
    balance = json.loads((stems / "balance.json").read_text(encoding="utf-8"))
    assert balance["problems"] == [], balance
    low, high = nums.bed_accept_db
    assert low <= balance["bed_under_voice_db"] <= high
    assert balance["speech_band_margin_db"] >= nums.speech_band_margin_db
    assert 0.0 <= balance["duck_db"] <= nums.duck_max_db
    assert math.isclose(ffmpeg.duration_s(result.premix), fixture.DURATION_S, abs_tol=0.15)


def test_a_bed_outside_the_acceptance_band_is_repaired_not_failed(
    tmp_path: Path, voice: Path, plan: PicturePlan, story: SoundStory,
    library: sound.Library, nums: styles.Sound,
) -> None:  # fmt: skip
    """7.3 as amended by 056 (1): the acceptance is in code, and a miss is repaired. A
    bed asked for 3 dB under the voice is far above the band; the mix logs the miss,
    lowers the bed to the window's floor and ships that, with the measured numbers."""
    stems = tmp_path / "stems"
    stems.mkdir()
    loud = nums.model_copy(update={"bed_db_under_voice": -3.0})
    lines: list[str] = []
    result = sound.build_mix(
        stems=stems, voice=voice, plan=plan, story=story, nums=loud,
        library=library, runtime_s=fixture.DURATION_S, log=lines.append,
    )  # fmt: skip
    assert result.bed is not None and result.balance.problems == []
    low, high = loud.bed_accept_db
    assert result.balance.bed_under_voice_db is not None
    assert low - 0.5 <= result.balance.bed_under_voice_db <= high
    assert any("misses the 7.3 band" in line and "bed sits" in line for line in lines)
    assert any("lowered to" in r for r in result.balance.repairs)
    written = json.loads((stems / "balance.json").read_text(encoding="utf-8"))
    assert written["problems"] == [] and written["repairs"] == list(result.balance.repairs)


# --- 056 (1): a music check never fails the job -----------------------------------------
#
# run03 died at the end of a 20-minute job because its Freesound bed ("middle eastern
# mysterious") was melodic inside the 250 Hz-4 kHz speech band: the margin measured
# 9.4 dB under the 20 dB line and `build_mix` raised. The beds below reproduce that
# shape on the fixture voice: a bed with a partial inside the band that a dip can save,
# and an in-band tone that nothing can.
#
# 064 moved the line to 12 dB. A steady tone, levelled on its median, clears 12 dB on the
# fixture voice whatever its spectrum (~14 dB), so both beds swell inside the band one
# second in three: the median (1 s windows, 7.3) stays on the quiet part while the
# band's mean carries the swell.


def _tone_bed(path: Path, expr: str) -> Path:
    return fixture.make_wav(path, expr=f"({expr})", duration_s=fixture.CATALOGUE_BED_S)


def _bed(entry_id: str, file: str, *, drops: Sequence[float] = (1.5,)) -> AudioEntry:
    return AudioEntry(
        id=entry_id, kind="bed", file=file, source="synthetic",
        source_url=f"https://example.invalid/{entry_id}", licence="CC0-1.0",
        author="test", duration_s=fixture.CATALOGUE_BED_S,
        tags=AudioTags(theme=["tech"], mood=["curious", "mysterious_curiosity"], intent=[]),
        drop_points_s=list(drops), loop_ok=True, energy=3,
    )  # fmt: skip  (076: an approved bed of the fake story's mood)


def _with_beds(
    library: sound.Library, root: Path, *beds: tuple[str, str]
) -> sound.Library:
    """The fixture catalogue's SFX plus the given beds, files written under `root`."""
    (root / "beds").mkdir(parents=True, exist_ok=True)
    entries: list[AudioEntry] = []
    for entry_id, expr in beds:
        _tone_bed(root / "beds" / f"{entry_id}.wav", expr)
        entries.append(_bed(entry_id, f"beds/{entry_id}.wav"))
    for sfx in library.sfx():
        entries.append(sfx.model_copy(update={"file": str(library.file(sfx))}))
    return sound.Library(root=root, entries=tuple(entries))


# A steady 110 Hz bass under an in-band swell: the plain mix misses the 12 dB margin by
# a few dB (8.5 measured) and a dip on the band recovers it (one 5 dB dip, 12.7 dB).
MELODIC = "0.2*sin(2*PI*110*t)+0.6*sin(2*PI*1000*t)*lt(mod(t,3),1)"
# A bed entirely inside the band: a dip is undone by the level match, so nothing saves it
# (1.1 dB plain, 2.3 dB after the dips and the lower bed).
PURE = "sin(2*PI*1000*t)*(0.1+0.6*lt(mod(t,3),1))"


def test_a_bed_inside_the_speech_band_is_dipped_until_the_margin_clears(
    tmp_path: Path, voice: Path, plan: PicturePlan, story: SoundStory,
    library: sound.Library, nums: styles.Sound,
) -> None:  # fmt: skip
    """056 (1), first rung: an EQ dip on the bed in 250 Hz-4 kHz, deep enough to reach
    the line, logged with its depth; the job goes on with the same bed."""
    melodic = _with_beds(library, tmp_path / "audio", ("bed_melodic", MELODIC))
    stems = tmp_path / "stems"
    stems.mkdir()
    lines: list[str] = []
    result = sound.build_mix(
        stems=stems, voice=voice, plan=plan, story=story, nums=nums,
        library=melodic, runtime_s=fixture.DURATION_S, log=lines.append,
    )  # fmt: skip
    assert result.bed is not None and result.bed.id == "bed_melodic"
    assert result.music is not None and result.music.is_file()
    assert result.balance.problems == []
    assert result.balance.speech_band_margin_db is not None
    assert result.balance.speech_band_margin_db >= nums.speech_band_margin_db
    low, high = nums.bed_accept_db
    assert result.balance.bed_under_voice_db is not None
    assert low <= result.balance.bed_under_voice_db <= high
    dips = [line for line in lines if "dip" in line and "dB" in line]
    assert dips, lines
    assert result.balance.repairs and any("dip" in r for r in result.balance.repairs)
    assert result.balance.dip_db is not None and result.balance.dip_db > 0
    assert any("under sound.speech_band_margin_db" in line for line in lines), "the miss is logged"


def test_the_next_bed_candidate_is_tried_when_no_repair_saves_the_first(
    tmp_path: Path, voice: Path, plan: PicturePlan, story: SoundStory,
    library: sound.Library, nums: styles.Sound,
) -> None:  # fmt: skip
    """056 (1), third rung: the pure in-band bed scores first (its drop point sits on
    the first stamp); the dip and the lower bed cannot save it, so the next library
    candidate is mixed and passes."""
    root = tmp_path / "audio"
    both = _with_beds(library, root, ("bed_pure", PURE))
    curious = library.entry("bed_tech_curious")
    assert curious is not None
    both = sound.Library(
        root=root,
        entries=(*both.entries, curious.model_copy(update={"file": str(library.file(curious))})),
    )
    first = sound.select_bed(both, story.bed_query, first_stamp_s=sound.first_stamp_s(plan),
                             threshold=nums.bed_score_threshold)  # fmt: skip
    assert first == both.entry("bed_pure")
    stems = tmp_path / "stems"
    stems.mkdir()
    lines: list[str] = []
    result = sound.build_mix(
        stems=stems, voice=voice, plan=plan, story=story, nums=nums,
        library=both, runtime_s=fixture.DURATION_S, log=lines.append,
    )  # fmt: skip
    assert result.bed is not None and result.bed.id == "bed_tech_curious"
    assert result.balance.problems == []
    assert any("bed_pure" in line and "next bed" in line for line in lines), lines
    assert any("lower" in r for r in result.balance.repairs), result.balance.repairs


# 069: run04's bed was a car's exhaust, -14.9 dB full-band but ~30 dB down in the band a
# phone speaker plays. A sub-200 Hz tone levelled on its median reproduces that shape; the
# mid-band bed carries a partial inside the band, as any bed with a melody does.
BASS_ONLY = "0.5*sin(2*PI*55*t)*(0.8+0.2*sin(2*PI*0.5*t))"
MID_BAND = "(0.25*sin(2*PI*110*t)+0.25*sin(2*PI*550*t))*(0.7+0.3*sin(2*PI*0.5*t))"
AUDIBLE_PAIR = (("bed_a_bass", BASS_ONLY), ("bed_b_mid", MID_BAND))


def test_a_bass_only_bed_fails_the_ceiling_and_a_mid_band_bed_is_mixed(
    tmp_path: Path, voice: Path, plan: PicturePlan, story: SoundStory,
    library: sound.Library, nums: styles.Sound,
) -> None:  # fmt: skip
    """069: at run04's level (`bed_db_under_voice` under the voice, inside
    `bed_accept_db`) the bass-only bed clears the speech band by more than
    `speech_band_margin_max_db`; the message names the margin, the director logs the
    walk, and the mid-band bed passes both bounds."""
    both = _with_beds(library, tmp_path / "audio", *AUDIBLE_PAIR)
    stems = tmp_path / "stems"
    stems.mkdir()
    lines: list[str] = []
    result = sound.build_mix(
        stems=stems, voice=voice, plan=plan, story=story, nums=nums,
        library=both, runtime_s=fixture.DURATION_S, log=lines.append,
    )  # fmt: skip
    missed = [line for line in lines if "bed_a_bass" in line and "misses the 7.3 band" in line]
    assert missed and "over sound.speech_band_margin_max_db 20 dB" in missed[0], lines
    assert any("bed bed_a_bass dropped after every repair; trying the next bed" in line
               for line in lines), lines  # fmt: skip
    assert result.bed is not None and result.bed.id == "bed_b_mid"
    assert result.balance.problems == []
    margin = result.balance.speech_band_margin_db
    assert margin is not None
    assert nums.speech_band_margin_db <= margin <= nums.speech_band_margin_max_db
    assert result.balance.speech_band_margin_max_db == nums.speech_band_margin_max_db


def test_the_audibility_check_runs_on_two_files(
    tmp_path: Path, voice: Path, library: sound.Library, nums: styles.Sound
) -> None:
    """069 / 075: the bound is a function of a voice and a levelled bed, so the shortlist
    tool can run it on every bed candidate before the operator hears it."""
    both = _with_beds(library, tmp_path / "audio", *AUDIBLE_PAIR)
    voice_db = ffmpeg.mean_volume_db(voice)
    assert voice_db is not None
    verdicts: dict[str, str | None] = {}
    for entry in both.beds():
        levelled = tmp_path / f"{entry.id}.levelled.wav"
        source = both.file(entry)
        bed_db = ffmpeg.mean_volume_db(source)
        assert bed_db is not None
        gain = voice_db + nums.bed_db_under_voice - bed_db
        ffmpeg.run(
            [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(source), "-af", f"volume={gain:.2f}dB",
             "-c:a", "pcm_f32le", str(levelled)],
            timeout_s=ffmpeg.MEASURE_TIMEOUT_S,
        )  # fmt: skip
        margin, problem = sound.audibility(voice, levelled, nums)
        assert margin is not None
        verdicts[entry.id] = problem
    assert verdicts["bed_b_mid"] is None
    bass = verdicts["bed_a_bass"]
    assert bass is not None and "over sound.speech_band_margin_max_db" in bass


def test_a_bed_no_repair_can_save_yields_a_voice_and_hits_master(
    tmp_path: Path, voice: Path, plan: PicturePlan, story: SoundStory,
    library: sound.Library, nums: styles.Sound,
) -> None:  # fmt: skip
    """056 (1), last rung: with no other candidate the short goes out with the voice
    and the hits alone - no exception, one `sound:` line saying so, the balance report
    naming the dropped bed - and the cues are still there."""
    pure = _with_beds(library, tmp_path / "audio", ("bed_pure", PURE))
    stems = tmp_path / "stems"
    stems.mkdir()
    lines: list[str] = []
    result = sound.build_mix(
        stems=stems, voice=voice, plan=plan, story=story, nums=nums,
        library=pure, runtime_s=fixture.DURATION_S, log=lines.append,
    )  # fmt: skip
    assert result.bed is None and result.music is None
    assert result.cues and result.sfx is not None and result.sfx.is_file()
    assert result.premix != voice and result.premix.is_file()
    assert not (stems / "music.wav").exists() and not (stems / "music.ducked.wav").exists()
    written = sound.balance_report(stems)
    assert written is not None
    assert written.problems == [] and written.bed_under_voice_db is None
    assert written.bed_dropped is not None and "bed_pure" in written.bed_dropped
    assert [line for line in lines if sound.VOICE_AND_HITS_LINE in line]
    assert any("dip" in r for r in written.repairs) and any("lower" in r for r in written.repairs)
    assert result.summary().startswith("sound: no bed")


def test_the_search_is_asked_for_the_next_bed_when_the_library_runs_out(
    tmp_path: Path, voice: Path, plan: PicturePlan, story: SoundStory,
    library: sound.Library, nums: styles.Sound,
) -> None:  # fmt: skip
    """056 (1): after the library's candidates the search ladder supplies the next bed."""
    pure = _with_beds(library, tmp_path / "audio", ("bed_pure", PURE))
    shelf = sound.Library(
        root=pure.root,
        entries=tuple(e.model_copy(update={"file": str(library.file(e))}) for e in library.beds()),
    )
    search = sound.FakeAudioSearch(shelf=shelf)
    stems = tmp_path / "stems"
    stems.mkdir()
    result = sound.build_mix(
        stems=stems, voice=voice, plan=plan, story=story, nums=nums,
        library=pure, runtime_s=fixture.DURATION_S, search=search,
    )  # fmt: skip
    assert search.calls, "the search was asked for the next candidate"
    assert result.bed is not None and result.bed.id != "bed_pure"
    assert result.balance.problems == []


def test_an_empty_library_leaves_the_voice_alone(
    tmp_path: Path, voice: Path, plan: PicturePlan, story: SoundStory, nums: styles.Sound
) -> None:
    stems = tmp_path / "stems"
    stems.mkdir()
    empty = sound.Library(root=tmp_path, entries=())
    result = sound.build_mix(
        stems=stems, voice=voice, plan=plan, story=story, nums=nums,
        library=empty, runtime_s=fixture.DURATION_S,
    )  # fmt: skip
    assert result.bed is None and result.cues == ()
    assert result.premix == voice, "with nothing to mix the voice is the premix"
    assert (stems / "balance.json").is_file()
    assert not (stems / "sfx.wav").exists()
    assert sound.cue_sheet(stems) == CueSheet(cues=[])


def test_the_rights_rows_name_the_files_the_mix_used(
    tmp_path: Path, voice: Path, plan: PicturePlan, story: SoundStory,
    library: sound.Library, nums: styles.Sound,
) -> None:  # fmt: skip
    """5.4: every music and SFX file gets a row with its source URL and origin
    `library`, the bed as `music` and the cues as `sfx`."""
    stems = tmp_path / "stems"
    stems.mkdir()
    result = sound.build_mix(
        stems=stems, voice=voice, plan=plan, story=story, nums=nums,
        library=library, runtime_s=fixture.DURATION_S,
    )  # fmt: skip
    rows = sound.rights_rows(result)
    kinds = {r.kind for r in rows}
    assert kinds == {"music", "sfx"}
    assert all(r.origin == "library" and r.source_url and r.sha256 for r in rows)
    music = next(r for r in rows if r.kind == "music")
    assert music.id == "bed_tech_curious" and music.licence == fixture.CATALOGUE_LICENCE
    sfx = next(r for r in rows if r.kind == "sfx")
    assert sfx.beat_ids, "an SFX row names the beats it fired on"
