"""076: music from the learned pairings - a mood per story part, at most one bed change.

The sound story names its story `parts` (hook / build_up / reveal / ending, as beat
ranges) and a `bed` of one or two segments `{part_from, mood, flavour?}` from the closed
list of `assets/audio/moods.yaml`, with `change: {at_beat, how}` when there are two. The
grammar refuses a mood off the list or not active, more segments than
`sound.bed_changes_max` allows, and a change off a story-part boundary, naming it."""

from __future__ import annotations

import math
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from shortsmith import ffmpeg, fixture, grammar, pipeline, render, smoke, sound, styles, vocab
from shortsmith.contracts import (
    AudioEntry,
    AudioTags,
    BedChange,
    BedHow,
    BedSegment,
    Constraints,
    MoodPoint,
    PartSpan,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    SoundStory,
)
from shortsmith.planner import FakePlanner, prompt
from shortsmith.reference import music
from shortsmith.transcriber import FakeTranscriber
from tests.test_worked_examples import (  # pyright: ignore[reportPrivateUsage]
    _answer_text,  # pyright: ignore[reportPrivateUsage]
    _card,  # pyright: ignore[reportPrivateUsage]
    _run,  # pyright: ignore[reportPrivateUsage]
)

SPECS = styles.load_all(render.registry())
TRANSCRIPT = FakeTranscriber().transcribe(Path("unused.mp4"))
PARTS = [
    PartSpan(part="hook", first_beat="b01", last_beat="b02"),
    PartSpan(part="build_up", first_beat="b03", last_beat="b06"),
    PartSpan(part="reveal", first_beat="b07", last_beat="b10"),
    PartSpan(part="ending", first_beat="b11", last_beat="b11"),
]


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


@pytest.fixture(scope="module")
def planned() -> tuple[PicturePlan, SoundStory]:
    return _planned("vishva")


def _judge(story: SoundStory, plan: PicturePlan, name: str = "vishva") -> object:
    judged = smoke.judged_specs(SPECS, name)[name]
    return grammar.validate_sound(story, plan, judged)


def _messages(result: object) -> list[str]:
    assert isinstance(result, grammar.Violations), result
    return [v.message for v in result.items]


def _two(
    first: str = "mysterious_curiosity", second: str = "tense_dramatic", at: str = "b07"
) -> dict[str, object]:
    return {
        "parts": PARTS,
        "bed": [BedSegment(part_from="hook", mood=first),
                BedSegment(part_from="reveal", mood=second)],
        "change": BedChange(at_beat=at, how="crossfade"),
    }  # fmt: skip


# --- the grammar ---------------------------------------------------------------------------


def test_the_fake_story_under_vishva_crossfades_at_the_reveal(
    planned: tuple[PicturePlan, SoundStory],
) -> None:
    plan, story = planned
    result = _judge(story, plan)
    assert isinstance(result, grammar.SoundCheck), _messages(result)
    assert [s.part_from for s in story.bed] == ["hook", "reveal"]
    assert story.change == BedChange(at_beat="b07", how="crossfade")
    assert [p.part for p in story.parts] == ["hook", "build_up", "reveal", "ending"]


@pytest.mark.parametrize("name", ["explainer", "fastfacts", "footage"])
def test_the_fake_story_elsewhere_is_one_bed(name: str) -> None:
    plan, story = _planned(name)
    result = _judge(story, plan, name)
    assert isinstance(result, grammar.SoundCheck), _messages(result)
    assert len(story.bed) == 1 and story.change is None


def test_a_mood_off_the_list_fails_naming_it(planned: tuple[PicturePlan, SoundStory]) -> None:
    plan, story = planned
    bad = story.model_copy(update=_two(second="spooky vibes"))
    messages = _messages(_judge(bad, plan))
    assert any("'spooky vibes'" in m and "moods.yaml" in m for m in messages), messages


def test_an_inactive_mood_or_flavour_fails_naming_it(
    planned: tuple[PicturePlan, SoundStory],
) -> None:
    plan, story = planned
    bad = story.model_copy(update=_two(second="eerie_scifi"))
    messages = _messages(_judge(bad, plan))
    assert any("'eerie_scifi'" in m and "not active" in m for m in messages), messages
    flavoured = story.model_copy(
        update={"bed": [BedSegment(part_from="hook", mood="calm_ambient", flavour="european")],
                "change": None, "parts": PARTS}  # fmt: skip
    )
    messages = _messages(_judge(flavoured, plan))
    assert any("'european'" in m and "not active" in m for m in messages), messages


def test_two_changes_fail_on_bed_changes_max(planned: tuple[PicturePlan, SoundStory]) -> None:
    plan, story = planned
    three = story.model_copy(
        update={
            **_two(),
            "bed": [BedSegment(part_from="hook", mood="mysterious_curiosity"),
                    BedSegment(part_from="build_up", mood="investigative_pulse"),
                    BedSegment(part_from="reveal", mood="tense_dramatic")],
        }  # fmt: skip
    )
    messages = _messages(_judge(three, plan))
    assert any("sound.bed_changes_max 1" in m for m in messages), messages


def test_a_change_off_a_part_boundary_fails_naming_it(
    planned: tuple[PicturePlan, SoundStory],
) -> None:
    plan, story = planned
    off = story.model_copy(update=_two(at="b08"))
    messages = _messages(_judge(off, plan))
    assert any("b08" in m and "story-part boundary" in m for m in messages), messages


def test_two_segments_need_a_change_and_one_segment_none(
    planned: tuple[PicturePlan, SoundStory],
) -> None:
    plan, story = planned
    missing = story.model_copy(update={**_two(), "change": None})
    assert any("change" in m for m in _messages(_judge(missing, plan)))
    single = story.model_copy(
        update={"parts": PARTS, "bed": [BedSegment(part_from="hook", mood="calm_ambient")],
                "change": BedChange(at_beat="b07", how="hard_cut")}  # fmt: skip
    )
    assert any("change" in m for m in _messages(_judge(single, plan)))


def test_no_bed_and_broken_parts_fail(planned: tuple[PicturePlan, SoundStory]) -> None:
    plan, story = planned
    empty = story.model_copy(update={"bed": [], "change": None})
    assert any("bed" in m for m in _messages(_judge(empty, plan)))
    gap = [PARTS[0], PARTS[2], PARTS[3]]  # build_up missing: b03-b06 belong to no part
    holed = story.model_copy(update={**_two(), "parts": gap})
    assert any("part" in m for m in _messages(_judge(holed, plan)))


def test_a_violation_takes_the_one_retry() -> None:
    """The retry is the planner's usual one (8.2): a Violations result, not an exception."""
    plan, story = _planned("vishva")
    bad = story.model_copy(update=_two(second="spooky vibes"))
    assert isinstance(_judge(bad, plan), grammar.Violations)


# --- the prompt: music in top shorts ---------------------------------------------------------


def test_a_card_is_one_line_of_topic_tone_moods_per_part_and_its_changes() -> None:
    card = _card("S5j-2CWYYwM", tier="A")
    assert music.pairing(card) == (
        "- S5j-2CWYYwM (Tier A; topic science; tone urgent, curious): "
        "hook mysterious_curiosity, build_up eerie_scifi, reveal tense_dramatic, "
        "ending calm_ambient; changes: hook -> build_up crossfade, "
        "build_up -> reveal hard_cut, reveal -> ending drop_to_silence"
    )
    quiet = card.model_copy(update={"music_changes": []})
    assert music.pairing(quiet).endswith("ending calm_ambient; no change")


def test_the_pairings_come_from_every_reference_card_tier_b_first(tmp_path: Path) -> None:
    for vid, tier, styles_ in (("aaaaaaaaaaa", "A", ("vishva",)), ("bbbbbbbbbbb", "B", ()),
                               ("ooooooooooo", "own", ("explainer",))):  # fmt: skip
        card = _card(vid, tier=tier, styles=styles_)
        (tmp_path / f"{vid}.json").write_text(card.model_dump_json(), encoding="utf-8")
    lines = music.for_job(tmp_path)
    assert [line.split(" ")[1] for line in lines] == ["bbbbbbbbbbb", "aaaaaaaaaaa"]
    assert music.for_job(tmp_path / "none") == []


def test_the_section_lists_the_active_moods_and_the_pairings() -> None:
    text = music.section(["- x (Tier A; topic war; tone grim): hook tense_dramatic; no change"])
    moods = vocab.load_moods()
    for name in (*moods.active_moods(), *moods.active_flavours()):
        assert f"`{name}`" in text, name
    assert "`eerie_scifi`" not in text, "an inactive mood is never offered"
    assert "hook tense_dramatic; no change" in text
    assert "topic, place, period and tone" in text
    assert music.NO_PAIRINGS in music.section([])


def test_the_sound_prompt_carries_music_in_top_shorts() -> None:
    request = _request("vishva").model_copy(update={"music": ["- x (Tier A): hook calm_ambient"]})
    picture = FakePlanner().plan_picture(request)
    text = prompt.build_prompt(request, "sound", picture=picture)
    assert prompt.MUSIC_HEADING in text and "- x (Tier A): hook calm_ambient" in text
    assert prompt.MUSIC_HEADING not in prompt.build_prompt(request, "picture")
    schema = SoundStory.model_json_schema()
    assert {"parts", "bed", "change"} <= set(schema["properties"])


def test_the_job_request_and_the_self_inventory_carry_the_music(
    tmp_path: Path, fixture_clip: Path
) -> None:
    from shortsmith.reference import own
    from shortsmith.reference.gemini import FakeAnalyser

    done = _run(tmp_path, fixture_clip, "A short about nothing.")
    notes: list[str] = []
    request = pipeline.build_plan_request(done, SPECS, tmp_path / "inventory", note=notes.append)
    assert [line.split(" ")[1] for line in request.music] == [
        "bbbbbbbbbbb", "ccccccccccc", "aaaaaaaaaaa"
    ]
    assert "music pairings: 3 reference cards" in notes
    bare: list[str] = []
    empty = pipeline.build_plan_request(done, SPECS, tmp_path / "none", note=bare.append)
    assert empty.music == []
    assert f"music pairings: none ({music.NO_PAIRINGS[1:-1]})" in bare
    own.SelfInventory(FakeAnalyser([_answer_text()])).run(done)
    table = own.summary(done, tmp_path / "inventory")
    assert table is not None and table.comparison is not None
    plan = {r.name: r.plan for r in table.comparison.rows if r.name.startswith("mood: ")}
    assert plan == {"mood: hook": "mysterious_curiosity", "mood: build_up": "mysterious_curiosity",
                    "mood: reveal": "mysterious_curiosity", "mood: ending": "mysterious_curiosity"}


# --- the director: which bed (7.2 as amended) ----------------------------------------------


def _bed(entry_id: str, mood: str, *, flavour: str | None = None, energy: int = 3,
         drops: tuple[float, ...] = ()) -> AudioEntry:  # fmt: skip
    return AudioEntry(
        id=entry_id, kind="bed", file=f"files/{entry_id}.wav", source="test",
        source_url=f"https://example.org/{entry_id}", licence="CC0-1.0", duration_s=8.0,
        tags=AudioTags(mood=[mood], flavour=[flavour] if flavour else []),
        drop_points_s=list(drops), energy=energy,
    )  # fmt: skip


def _picked(library: sound.Library, segment: BedSegment, energy: int) -> str | None:
    found = sound.select_mood_bed(library, segment, energy=energy, first_stamp_s=1.0)
    return None if found is None else found.id


def test_a_bed_is_picked_by_mood_then_flavour_then_energy_then_drop_fit() -> None:
    library = sound.Library(
        root=Path("unused"),
        entries=(
            _bed("calm_far", "calm_ambient", energy=1),
            _bed("tense_plain", "tense_dramatic", energy=3),
            _bed("tense_gulf", "tense_dramatic", flavour="middle_east", energy=5),
            _bed("tense_near", "tense_dramatic", energy=4, drops=(1.0,)),
            _bed("tense_near_late", "tense_dramatic", energy=4, drops=(9.0,)),
        ),
    )
    gulf = BedSegment(part_from="reveal", mood="tense_dramatic", flavour="middle_east")
    plain = BedSegment(part_from="reveal", mood="tense_dramatic")
    assert _picked(library, gulf, 3) == "tense_gulf"
    assert _picked(library, plain, 3) == "tense_plain"
    assert _picked(library, plain, 4) == "tense_near"
    assert _picked(library, BedSegment(part_from="hook", mood="investigative_pulse"), 3) is None


def test_a_fetched_bed_is_never_a_segments_bed() -> None:
    library = sound.Library(
        root=Path("unused"), entries=(_bed("fetched_tense", "tense_dramatic"),),
        fetched=frozenset({"fetched_tense"}),
    )  # fmt: skip
    assert _picked(library, BedSegment(part_from="hook", mood="tense_dramatic"), 3) is None


# --- the director: the change, rendered and measured -----------------------------------------

SILENT_DB = -60.0
CHANGE_S = 3.0  # b07's start on the fixture plan


def _level(path: Path, start: float, end: float) -> float:
    """The mean level of `path` over [start, end]; a silent window reads -inf."""
    found = ffmpeg.mean_volume_db(path, prefilter=f"atrim=start={start}:end={end}")
    return -math.inf if found is None else found


def _mix(
    tmp_path: Path, voice: Path, library: sound.Library, how: BedHow,
    curve: list[MoodPoint] | None = None,
) -> tuple[sound.MixResult, Path, styles.Sound]:  # fmt: skip
    plan, story = _planned("vishva")
    story = story.model_copy(update={"change": BedChange(at_beat="b07", how=how)})
    if curve is not None:
        story = story.model_copy(update={"mood_curve": curve})
    stems = tmp_path / "stems"
    stems.mkdir(parents=True)
    shutil.copy(voice, stems / "voice.wav")
    nums = SPECS["vishva"].sound
    result = sound.build_mix(
        stems=stems, voice=stems / "voice.wav", plan=plan, story=story, nums=nums,
        library=library, runtime_s=fixture.DURATION_S,
    )  # fmt: skip
    return result, stems, nums


def test_a_crossfade_plays_both_beds_for_its_length(
    tmp_path: Path, voice: Path, library: sound.Library
) -> None:
    flat = [MoodPoint(t=0.0, level=0.0), MoodPoint(t=fixture.DURATION_S, level=0.0)]
    result, stems, nums = _mix(tmp_path, voice, library, "crossfade", flat)
    assert [b.id for b in result.beds] == ["bed_tech_curious", "bed_tech_tense"]
    a, b = stems / "music.1.wav", stems / "music.2.wav"
    end = CHANGE_S + nums.bed_crossfade_s
    steady_a, steady_b = _level(a, 1.0, 2.5), _level(b, 4.2, 4.7)
    assert _level(a, CHANGE_S, end) > steady_a - 6.0, "the old bed is not heard in the crossfade"
    assert _level(b, CHANGE_S, end) > steady_b - 6.0, "the new bed is not heard in the crossfade"
    assert _level(a, end + 0.05, 6.0) < SILENT_DB
    assert _level(b, 0.0, CHANGE_S - 0.05) < SILENT_DB
    balance = sound.balance_report(stems)
    assert balance is not None and balance.problems == [], balance
    names = [w.name for w in balance.windows]
    assert len(names) == 3 and any("crossfade" in n for n in names), names
    assert all(w.speech_band_margin_db is not None for w in balance.windows)


def test_a_hard_cut_starts_the_new_bed_within_one_frame(
    tmp_path: Path, voice: Path, library: sound.Library
) -> None:
    _, stems, _ = _mix(tmp_path, voice, library, "hard_cut")
    a, b = stems / "music.1.wav", stems / "music.2.wav"
    frame = 1 / 30
    steady_b = _level(b, 4.0, 4.7)
    assert _level(b, CHANGE_S + frame, CHANGE_S + 0.5) > steady_b - 1.5
    assert _level(a, CHANGE_S, 6.0) < SILENT_DB
    assert _level(b, 0.0, CHANGE_S) < SILENT_DB


def test_a_drop_to_silence_holds_the_music_under_minus_60_db(
    tmp_path: Path, voice: Path, library: sound.Library
) -> None:
    _, stems, nums = _mix(tmp_path, voice, library, "drop_to_silence")
    silence_end = CHANGE_S + nums.bed_silence_s
    assert _level(stems / "music.wav", CHANGE_S, silence_end) < SILENT_DB
    after = silence_end + nums.bed_cut_fade_s
    assert _level(stems / "music.2.wav", after, after + 0.5) > SILENT_DB + 20


def test_the_envelope_still_shapes_each_bed(
    tmp_path: Path, voice: Path, library: sound.Library
) -> None:
    """The swell/drop curve (7.3) rides inside each bed: an 8 dB step in each segment,
    read against the same mix with a flat curve (the fixture beds wobble, and the level
    match moves each bed's gain, so only the difference of differences is the step)."""
    curve = [
        MoodPoint(t=0.0, level=0.0), MoodPoint(t=1.5, level=0.0), MoodPoint(t=1.51, level=-8.0),
        MoodPoint(t=2.9, level=-8.0), MoodPoint(t=3.0, level=0.0), MoodPoint(t=4.5, level=0.0),
        MoodPoint(t=4.51, level=-8.0), MoodPoint(t=6.0, level=-8.0),
    ]  # fmt: skip
    flat = [MoodPoint(t=0.0, level=0.0), MoodPoint(t=fixture.DURATION_S, level=0.0)]
    shaped, shaped_stems, _ = _mix(tmp_path / "shaped", voice, library, "hard_cut", curve)
    plain, plain_stems, _ = _mix(tmp_path / "plain", voice, library, "hard_cut", flat)
    assert len(shaped.beds) == len(plain.beds) == 2, shaped.notes

    def step(name: str, before: tuple[float, float], after: tuple[float, float]) -> float:
        s, p = shaped_stems / name, plain_stems / name
        return (_level(p, *after) - _level(s, *after)) - (_level(p, *before) - _level(s, *before))

    assert step("music.1.wav", (0.6, 1.4), (1.7, 2.8)) == pytest.approx(8.0, abs=1.0)
    assert step("music.2.wav", (3.3, 4.4), (4.6, 5.8)) == pytest.approx(8.0, abs=1.0)


def test_no_approved_bed_for_a_mood_is_one_freesound_bed_and_no_change(
    tmp_path: Path, voice: Path, library: sound.Library
) -> None:
    only_curious = replace(
        library, entries=tuple(e for e in library.entries if e.id != "bed_tech_tense")
    )
    shelf = sound.Library(
        root=library.root, entries=tuple(e for e in library.entries if e.id == "bed_history_calm")
    )
    search = sound.FakeAudioSearch(shelf)
    plan, story = _planned("vishva")
    stems = tmp_path / "stems"
    stems.mkdir()
    shutil.copy(voice, stems / "voice.wav")
    result = sound.build_mix(
        stems=stems, voice=stems / "voice.wav", plan=plan, story=story,
        nums=SPECS["vishva"].sound, library=only_curious, runtime_s=fixture.DURATION_S,
        search=search,
    )  # fmt: skip
    assert search.calls, "the Freesound fallback was not asked"
    assert all(q.split()[-1] == "music" for q in search.calls), search.calls  # 069's anchor
    assert [b.id for b in result.beds] == ["bed_history_calm"]
    assert result.fallback == "fallback bed: tense_dramatic, no approved bed"
    assert result.fallback in result.notes
    assert not (stems / "music.2.wav").exists()
