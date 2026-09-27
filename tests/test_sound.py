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
    assert bed.tags.mood == ["curious", "bright"]
    assert bed.energy == 3
    assert bed.drop_points_s == [1.0, 3.5]
    assert bed.loop_ok is True
    assert bed.licence == fixture.CATALOGUE_LICENCE
    assert library.file(bed).is_file()


def test_catalogue_tags_are_the_planner_facing_text(library: sound.Library) -> None:
    tags = library.tags()
    assert "tech" in tags and "curious" in tags and "popup_tick" in tags
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


def test_an_empty_sfx_catalogue_with_a_search_still_places_the_floor_and_the_cues(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    """054 (3): the floor classes are searched first (drum, bass, thump), then the
    planner's intents; what the search adopts is placed, and the grown library comes
    back with the cues so the stem and the rights rows can find the files."""
    empty = sound.Library(root=library.root, entries=())
    search = sound.FakeAudioSearch(shelf=library)
    placed = sound.place_cues(plan, story, empty, nums, runtime_s=60.0, search=search)
    assert placed.cues, "the search filled the empty catalogue"
    with_search = sound.place_cues(plan, story, library, nums, runtime_s=60.0)
    assert [(c.beat_id, c.entry_id, c.hit) for c in placed.cues] == [
        (c.beat_id, c.entry_id, c.hit) for c in with_search.cues
    ], "the same cues as a seeded catalogue places"
    assert search.sfx_calls[:3] == ["drum hit", "bass hit", "thump hit"], "the floor first"
    assert all(placed.library.entry(c.entry_id) is not None for c in placed.cues)
    assert any("adopted" in n for n in placed.notes)
    placed_lines = [n for n in placed.notes if "placed at" in n]
    assert len(placed_lines) == len(placed.cues), "one line per placed cue (054 (1))"


def test_an_empty_sfx_catalogue_and_no_search_places_nothing_and_says_so(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    empty = sound.Library(root=library.root, entries=())
    placed = sound.place_cues(plan, story, empty, nums, runtime_s=60.0)
    assert placed.cues == ()
    assert any(
        "no sfx in the audio catalogue" in n and "no audio search" in n for n in placed.notes
    )


def test_a_search_that_finds_no_sfx_leaves_a_line_per_miss(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    empty = sound.Library(root=library.root, entries=())
    search = sound.FakeAudioSearch()  # an empty shelf: every search is a miss
    placed = sound.place_cues(plan, story, empty, nums, runtime_s=60.0, search=search)
    assert placed.cues == ()
    assert "bass" in search.sfx_calls and "drum" in search.sfx_calls
    assert any("no sfx for 'bass'" in n for n in placed.notes)


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
    assert hits["b02"].hit == "thump" and hits["b02"].trigger == "card_fly_in"
    assert "b03" not in hits  # 055: the full beat has no landed event
    assert hits["b04"].hit == "bass" and hits["b04"].trigger == "stamp"
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
    with no event; b02 enters on a whip and carries a lower-third, and earns its thump
    from the card it flies in, never from either of those."""
    hit_ids = {h.beat_id for h in sound.floor_hits(plan, nums)}
    assert "b03" not in hit_ids and "b05" not in hit_ids
    bare = plan.model_copy(
        update={
            "beats": [
                b.model_copy(update={"kind": "photo", "enter": "whip",
                                     "event": Event(kind="ring")})  # fmt: skip
                if b.id == "b02"
                else b
                for b in plan.beats
            ]
        }
    )
    assert "b02" not in {h.beat_id for h in sound.floor_hits(bare, nums)}


def test_no_transition_triggers_a_cue(
    plan: PicturePlan, library: sound.Library, nums: styles.Sound
) -> None:
    """9.4 / 7.1 (030): a whip on every beat, no events, no planner cues and a flat mood
    curve place nothing beyond the floor - the director never reads `enter`, so the
    cues are exactly those of the same plan entering on cuts. (The grammar would reject
    this plan; the director is tested past it.)"""

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
    assert {c.beat_id for c in placed.cues} == floor
    assert all(c.source == "floor" for c in placed.cues)
    assert placed == sound.place_cues(cut, silent, library, nums, runtime_s=60.0)


def test_the_floor_classes_come_from_the_style(plan: PicturePlan, nums: styles.Sound) -> None:
    """The hit class per event is the style's `sound.floor_hits`, never code."""
    swapped = nums.model_copy(
        update={"floor_hits": {"drum": ["stamp"], "bass": ["money_reveal"], "thump": []}}
    )
    hits = {h.beat_id: h.hit for h in sound.floor_hits(plan, swapped)}
    assert hits["b04"] == "drum" and hits["b06"] == "bass"
    assert "b02" not in hits, "card_fly_in earns nothing when the style drops it"


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


def test_an_unmatched_intent_falls_back_to_the_floor_hit(
    plan: PicturePlan, library: sound.Library, nums: styles.Sound
) -> None:
    story = SoundStory(
        prompt_version="t", theme="t", mood_curve=[MoodPoint(t=0.0, level=0.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3),
        cues=[Cue(beat_id="b06", intent="nothing_matches_this", at="event")],
    )  # fmt: skip
    placed = sound.place_cues(plan, story, library, nums, runtime_s=6.0)
    cue = next(c for c in placed.cues if c.beat_id == "b06")
    assert cue.hit == "drum" and cue.entry_id == "sfx_drum_hit"
    assert any("nothing_matches_this" in n for n in placed.notes)


def test_one_cue_per_beat_and_the_planner_wins_the_slot(
    plan: PicturePlan, story: SoundStory, library: sound.Library, nums: styles.Sound
) -> None:
    placed = sound.place_cues(plan, story, library, nums, runtime_s=60.0)
    ids = [c.beat_id for c in placed.cues]
    assert len(ids) == len(set(ids)), "sound.cues_per_beat_max is 1"
    assert [c.at_s for c in placed.cues] == sorted(c.at_s for c in placed.cues)
    by_beat = {c.beat_id: c for c in placed.cues}
    # The five beats the fake story cues are the planner's; the rest come from the floor.
    assert {b: c.source for b, c in by_beat.items()} == {
        "b01": "planner", "b02": "planner", "b04": "planner",
        "b06": "planner", "b08": "floor", "b10": "floor", "b11": "planner",
    }  # fmt: skip
    assert by_beat["b10"].entry_id == "sfx_thump", "a floor cue plays its class's sample"
    assert by_beat["b01"].hit == "", "a planner cue on a beat the floor never claims"


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
    director places one on the beat the step lands on."""
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
    assert cue.entry_id == "sfx_changeover"
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
    assert any("no sfx" in n for n in placed.notes)


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


@pytest.fixture(scope="session")
def voice(tmp_path_factory: pytest.TempPathFactory, fixture_clip: Path) -> Path:
    """A voice stem shaped like the renderer's: the fixture's tone bursts through the
    7.3 voice chain to -19 LUFS."""
    out = tmp_path_factory.mktemp("voice") / "voice.wav"
    measured = ffmpeg.measure_loudness(
        fixture_clip, prefilter=render.voice_chain(), target_lufs=render.VOICE_LUFS,
        target_tp=render.VOICE_TP,
    )  # fmt: skip
    second = render.loudnorm_second_pass(
        measured, target_lufs=render.VOICE_LUFS, target_tp=render.VOICE_TP
    )
    ffmpeg.run(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(fixture_clip),
            "-map", "0:a:0", "-af", f"{render.voice_chain()},{second},aresample=48000",
            "-c:a", "pcm_s16le", str(out),
        ],  # fmt: skip
        timeout_s=ffmpeg.MEASURE_TIMEOUT_S,
    )
    return out


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
# and a pure in-band tone that nothing can.


def _tone_bed(path: Path, parts: Sequence[tuple[int, float]]) -> Path:
    expr = "+".join(f"{amp}*sin(2*PI*{hz}*t)" for hz, amp in parts)
    return fixture.make_wav(path, expr=f"({expr})", duration_s=fixture.CATALOGUE_BED_S)


def _bed(entry_id: str, file: str, *, drops: Sequence[float] = (1.5,)) -> AudioEntry:
    return AudioEntry(
        id=entry_id, kind="bed", file=file, source="synthetic",
        source_url=f"https://example.invalid/{entry_id}", licence="CC0-1.0",
        author="test", duration_s=fixture.CATALOGUE_BED_S,
        tags=AudioTags(theme=["tech"], mood=["curious"], intent=[]),
        drop_points_s=list(drops), loop_ok=True, energy=3,
    )  # fmt: skip


def _with_beds(
    library: sound.Library, root: Path, *beds: tuple[str, Sequence[tuple[int, float]]]
) -> sound.Library:
    """The fixture catalogue's SFX plus the given beds, files written under `root`."""
    (root / "beds").mkdir(parents=True, exist_ok=True)
    entries: list[AudioEntry] = []
    for entry_id, parts in beds:
        _tone_bed(root / "beds" / f"{entry_id}.wav", parts)
        entries.append(_bed(entry_id, f"beds/{entry_id}.wav"))
    for sfx in library.sfx():
        entries.append(sfx.model_copy(update={"file": str(library.file(sfx))}))
    return sound.Library(root=root, entries=tuple(entries))


# A bed with half its power inside the speech band: the plain mix misses the 20 dB
# margin by a few dB and a dip on the band recovers it.
MELODIC: tuple[tuple[int, float], ...] = ((110, 0.2), (1000, 0.2))
# A bed entirely inside the band: a dip is undone by the level match, so nothing saves it.
PURE: tuple[tuple[int, float], ...] = ((1000, 0.25),)


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
