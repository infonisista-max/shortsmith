"""The closed SFX palette (ticket 070; 7.1 and 7.3 as amended at run04 QA, 29 Sep 2026).

Run04 (job `20260928-140620-f774e1`, vishva) played no whoosh and no tick, and a beeping
score counter the planner called `tally_ding`. The cue vocabulary is now six kinds -
tick, whoosh, bass, drum, thump, ding - each with a length in the style's front matter;
the director derives a tick on a pop-in and a whoosh on a transition within the caps;
a ding sits only on an `idea` sticker; and effect files come only from the approved
library, never from a search at job time. The run04 plan and sound story are copied
under `fixtures/run04/` (JSON only).
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest

from shortsmith import ffmpeg, fixture, grammar, render, sound, styles
from shortsmith.contracts import (
    CUE_KINDS,
    AudioEntry,
    BedQuery,
    Cue,
    MoodPoint,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    SoundStory,
    Sticker,
    Transcript,
)
from shortsmith.planner import FakePlanner

RUN04 = Path(__file__).parent / "fixtures" / "run04"
INVENTED = ("popup_tick", "question_tick", "date_stamp", "tally_ding", "money", "changeover")


@pytest.fixture(scope="module")
def specs() -> dict[str, styles.StyleSpec]:
    return render.loaded_styles()


@pytest.fixture(scope="module")
def run04_plan() -> PicturePlan:
    return PicturePlan.model_validate_json(
        (RUN04 / "picture_validated.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def run04_story() -> SoundStory:
    return SoundStory.model_validate_json((RUN04 / "sound.json").read_text(encoding="utf-8"))


def _story(*cues: Cue) -> SoundStory:
    return SoundStory(
        prompt_version="t", theme="t", mood_curve=[MoodPoint(t=0.0, level=0.0)],
        bed_query=BedQuery(theme="tech", mood="curious", energy=3), cues=list(cues),
    )  # fmt: skip


def _items(result: object) -> list[object]:
    return list(getattr(result, "items", []))


# --- the palette in the schema and the grammar -------------------------------------------


def test_the_palette_is_six_kinds_and_the_schema_lists_them() -> None:
    assert CUE_KINDS == ("tick", "whoosh", "bass", "drum", "thump", "ding")
    schema = SoundStory.model_json_schema()
    intent = schema["$defs"]["Cue"]["properties"]["intent"]
    assert intent["enum"] == list(CUE_KINDS)


def test_run04s_sound_story_is_rejected_naming_every_invented_intent(
    specs: dict[str, styles.StyleSpec], run04_plan: PicturePlan, run04_story: SoundStory
) -> None:
    result = grammar.validate_sound(run04_story, run04_plan, specs["vishva"])
    assert isinstance(result, grammar.Violations)
    palette = [v for v in result.items if "outside the sound palette" in v.message]
    assert all(v.rule == "7.1" for v in palette)
    named = " ".join(v.message for v in palette)
    for intent in INVENTED:
        assert repr(intent) in named, intent
    assert not any("'whoosh'" in v.message for v in palette), "whoosh is in the palette"


def _with_sticker(plan: PicturePlan, beat_id: str, intent: str) -> PicturePlan:
    sticker = Sticker(intent=intent, word=0, at_s=None)
    return plan.model_copy(update={"beats": [
        b.model_copy(update={"stickers": [sticker]}) if b.id == beat_id else b
        for b in plan.beats
    ]})  # fmt: skip


def test_a_ding_passes_only_on_an_idea_stickers_pop_in(
    specs: dict[str, styles.StyleSpec], run04_plan: PicturePlan
) -> None:
    """b10 of run04 carries a `shock` sticker and enters on a flash; b04 an `no` sticker
    on a zoom; b01 a text pop. A ding is allowed on an `idea` sticker alone."""
    spec = specs["vishva"]
    idea = _with_sticker(run04_plan, "b10", "idea")
    ok = grammar.validate_sound(_story(Cue(beat_id="b10", intent="ding", at="event")), idea, spec)
    assert not [v for v in _items(ok) if "ding" in str(v)], ok
    for plan, cue in (
        (run04_plan, Cue(beat_id="b10", intent="ding", at="event")),  # a shock sticker
        (run04_plan, Cue(beat_id="b01", intent="ding", at="event")),  # a text pop
        (run04_plan, Cue(beat_id="b05", intent="ding", at="start")),  # a flash transition
        (idea, Cue(beat_id="b10", intent="ding", at="start")),  # the idea beat's enter
    ):
        result = grammar.validate_sound(_story(cue), plan, spec)
        assert isinstance(result, grammar.Violations), cue
        assert any(v.beat_id == cue.beat_id and "'ding'" in v.message for v in result.items)


def test_a_tick_sits_only_on_a_pop_in(
    specs: dict[str, styles.StyleSpec], run04_plan: PicturePlan
) -> None:
    spec = specs["vishva"]
    ok = grammar.validate_sound(_story(Cue(beat_id="b01", intent="tick", at="event")),
                                run04_plan, spec)  # fmt: skip
    assert not [v for v in _items(ok) if "tick" in str(v)], ok
    for cue in (
        Cue(beat_id="b05", intent="tick", at="start"),  # a flash transition
        Cue(beat_id="b06", intent="tick", at="event"),  # a stamp, no pop
    ):
        result = grammar.validate_sound(_story(cue), run04_plan, spec)
        assert isinstance(result, grammar.Violations), cue
        assert any(v.beat_id == cue.beat_id and "'tick'" in v.message for v in result.items)


def test_a_whoosh_rides_any_non_cut_transition_the_style_allows(
    specs: dict[str, styles.StyleSpec], run04_plan: PicturePlan
) -> None:
    """070: `whoosh.on` widened from `flash` to every non-cut enter plus `pop`; b04 of
    run04 enters on a zoom, b03 on a cut."""
    spec = specs["vishva"]
    zoom = grammar.validate_sound(_story(Cue(beat_id="b04", intent="whoosh", at="start")),
                                  run04_plan, spec)  # fmt: skip
    assert not [v for v in _items(zoom) if "whoosh" in str(v)], zoom
    cut = grammar.validate_sound(_story(Cue(beat_id="b03", intent="whoosh", at="start")),
                                 run04_plan, spec)  # fmt: skip
    assert isinstance(cut, grammar.Violations)
    assert any(v.beat_id == "b03" and "'whoosh'" in v.message for v in cut.items)


# --- the style rows ------------------------------------------------------------------------


def test_every_style_carries_the_tick_ding_and_widened_whoosh_rows(
    specs: dict[str, styles.StyleSpec],
) -> None:
    assert len(specs) == 7
    for name, spec in specs.items():
        nums = spec.sound
        assert styles.allows_whoosh(nums), name
        assert nums.whoosh is not None
        moving = [t for t in spec.broll.enter_transitions if t != "cut"]
        assert nums.whoosh.on == [*moving, "pop"], name
        assert (nums.whoosh.max_per_60s, nums.whoosh.min_gap_s, nums.whoosh.max_len_s) == (
            6, 3.0, 0.8
        ), name
        assert nums.tick.on == ["pop"], name
        assert (nums.tick.max_per_60s, nums.tick.min_gap_s, nums.tick.max_len_s) == (
            6, 2.0, 0.25
        ), name
        assert nums.ding.on == ["idea_sticker"] and nums.ding.max_per_60s == 2, name
        assert nums.ding.max_len_s == 0.8, name
        assert set(nums.floor_hits) <= set(nums.floor_max_len_s), name


def _front(name: str) -> str:
    return (styles.STYLES_DIR / f"{name}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("old", "new", "said"),
    [
        ('tick: {max_per_60s: 6, min_gap_s: 2.0, max_len_s: 0.25, "on": [pop]}',
         'tick: {max_per_60s: 6, min_gap_s: 2.0, max_len_s: 0.25, "on": [pop, flash]}',
         "sound.tick.on"),
        ('"on": [fade, whip, zoom, spring, flash, pop]}',
         '"on": [fade, whip, zoom, spring, flash, wipe, pop]}', "sound.whoosh.on"),
        ('"on": [idea_sticker]}', '"on": [pop]}', "sound.ding.on"),
    ],
)  # fmt: skip
def test_the_loader_refuses_a_row_with_an_unknown_trigger(
    tmp_path: Path, old: str, new: str, said: str
) -> None:
    text = _front("vishva")
    assert old in text, old
    for other in styles.STYLES_DIR.glob("*.md"):
        shutil.copy(other, tmp_path / other.name)
    (tmp_path / "vishva.md").write_text(text.replace(old, new), encoding="utf-8")
    with pytest.raises(styles.StyleError, match=said.replace(".", r"\.")):
        styles.load_all(render.registry(), tmp_path)


# --- the director ---------------------------------------------------------------------------


def test_every_pop_in_and_non_cut_transition_of_run04_is_a_candidate(
    specs: dict[str, styles.StyleSpec], run04_plan: PicturePlan
) -> None:
    nums = specs["vishva"].sound
    marks = sound.mark_candidates(run04_plan, nums)
    pops = [
        (b.id, item.at_s)
        for b in run04_plan.beats
        for item in (*b.text_pops, *b.bubbles, *b.stickers)
    ]
    moving = [(b.id, b.start) for b in run04_plan.beats if b.enter != "cut"]
    assert sorted((m.beat_id, m.at_s) for m in marks if m.kind == "tick") == sorted(pops)
    assert sorted((m.beat_id, m.at_s) for m in marks if m.kind == "whoosh") == sorted(moving)
    assert len(pops) == 12 and len(moving) == 11


def test_run04s_derived_ticks_and_whooshes_respect_the_caps_and_gaps(
    specs: dict[str, styles.StyleSpec], run04_plan: PicturePlan, library: sound.Library
) -> None:
    """With no planner cue at all, the director marks pop-ins and transitions itself,
    each kind within `max_per_60s` (scaled, rounded up) and `min_gap_s`; no pop-in or
    transition beyond the cap gets one, and every candidate not marked has its line."""
    nums = specs["vishva"].sound.model_copy(update={"cues_max_per_60s": 200})
    runtime = run04_plan.beats[-1].end
    placed = sound.place_cues(run04_plan, _story(), library, nums, runtime_s=runtime)
    candidates = sound.mark_candidates(run04_plan, nums)
    for kind, row in (("tick", nums.tick), ("whoosh", nums.whoosh)):
        assert row is not None
        cues = [c for c in placed.cues if c.hit == kind]
        cap = sound.mark_cap(row, runtime_s=runtime)
        assert cap == math.ceil(row.max_per_60s * runtime / 60.0 - 1e-6) == 6
        assert 0 < len(cues) <= cap, kind
        times = [c.at_s for c in cues]
        assert all(b - a >= row.min_gap_s - 1e-9 for a, b in zip(times, times[1:], strict=False))
        wanted = {(m.beat_id, m.at_s) for m in candidates if m.kind == kind}
        assert {(c.beat_id, c.at_s) for c in cues} <= wanted
        for m in candidates:
            if m.kind == kind and (m.beat_id, m.at_s) not in {(c.beat_id, c.at_s) for c in cues}:
                assert any(m.beat_id in n and kind in n and "not marked" in n
                           for n in placed.notes), m  # fmt: skip
    tight = nums.model_copy(update={"tick": nums.tick.model_copy(update={"max_per_60s": 1})})
    one = sound.place_cues(run04_plan, _story(), library, tight, runtime_s=runtime)
    assert len([c for c in one.cues if c.hit == "tick"]) == 1


def test_a_ding_is_derived_on_an_idea_sticker_and_never_on_another(
    specs: dict[str, styles.StyleSpec], run04_plan: PicturePlan, library: sound.Library
) -> None:
    nums = specs["vishva"].sound.model_copy(update={"cues_max_per_60s": 200})
    runtime = run04_plan.beats[-1].end
    plain = sound.place_cues(run04_plan, _story(), library, nums, runtime_s=runtime)
    assert not [c for c in plain.cues if c.hit == "ding"], "shock and no stickers get no ding"
    idea = _with_sticker(run04_plan, "b07", "idea")
    placed = sound.place_cues(idea, _story(), library, nums, runtime_s=runtime)
    dings = [c for c in placed.cues if c.hit == "ding"]
    assert [(c.beat_id, c.entry_id) for c in dings] == [("b07", "sfx_ding")]
    assert dings[0].gain_db == sound.cue_level_db("tick", nums), "a ding sits at tick level"


def test_ticks_and_whooshes_sit_at_the_quiet_end_of_the_band(
    specs: dict[str, styles.StyleSpec],
) -> None:
    nums = specs["vishva"].sound
    thump = sound.cue_level_db("thump", nums)
    assert nums.cue_db_min <= sound.cue_level_db("tick", nums) <= thump
    assert nums.cue_db_min <= sound.cue_level_db("whoosh", nums) <= thump


def test_no_placed_cue_is_longer_than_its_kinds_max_len(
    specs: dict[str, styles.StyleSpec], run04_plan: PicturePlan, library: sound.Library
) -> None:
    nums = specs["vishva"].sound.model_copy(update={"cues_max_per_60s": 200})
    runtime = run04_plan.beats[-1].end
    placed = sound.place_cues(run04_plan, _story(), library, nums, runtime_s=runtime)
    assert placed.cues
    for cue in placed.cues:
        entry = placed.library.entry(cue.entry_id)
        assert entry is not None
        assert entry.duration_s <= sound.kind_max_len_s(sound.cue_kind(cue), nums) + 1e-9, cue
    tick = library.entry("sfx_tick")
    assert tick is not None
    long_tick = tick.model_copy(update={"duration_s": nums.tick.max_len_s + 0.1})
    only_long = sound.Library(
        root=library.root, entries=(*(e for e in library.entries if e.id != "sfx_tick"), long_tick)
    )
    none = sound.place_cues(run04_plan, _story(), only_long, nums, runtime_s=runtime)
    assert not [c for c in none.cues if c.hit == "tick"]
    assert any("no approved sfx for 'tick'" in n and "0.25" in n for n in none.notes)


def test_a_kind_with_no_approved_file_drops_its_cue_with_a_line(
    specs: dict[str, styles.StyleSpec], run04_plan: PicturePlan, library: sound.Library
) -> None:
    nums = specs["vishva"].sound.model_copy(update={"cues_max_per_60s": 200})
    no_tick = sound.Library(
        root=library.root, entries=tuple(e for e in library.entries if e.id != "sfx_tick")
    )
    story = _story(Cue(beat_id="b01", intent="tick", at="event"))
    placed = sound.place_cues(run04_plan, story, no_tick, nums, runtime_s=59.5)
    assert not [c for c in placed.cues if c.hit == "tick"]
    assert any("b01" in n and "'tick'" in n and "dropped" in n for n in placed.notes)


def test_a_fetched_sfx_is_not_in_the_approved_library(tmp_path: Path) -> None:
    """075: effect files come only from the tracked catalogue the operator approved; the
    git-ignored `fetched/` catalogue a runtime search appended to is never matched."""
    root = tmp_path / "audio"
    catalogue = fixture.make_catalogue(root)
    (root / sound.FETCHED_DIR).mkdir()
    text = catalogue.read_text(encoding="utf-8")
    (root / sound.FETCHED_DIR / sound.CATALOGUE_NAME).write_text(
        text.replace("id: sfx_tick", "id: sfx_tick_fetched"), encoding="utf-8"
    )
    library = sound.load_catalogue(catalogue)
    assert library.entry("sfx_tick_fetched") is not None
    assert "sfx_tick_fetched" not in {e.id for e in library.approved_sfx()}
    assert "sfx_tick" in {e.id for e in library.approved_sfx()}


class _NoSfxSearch(sound.FakeAudioSearch):
    def sfx(
        self, words: str, intent: str, library: sound.Library, *,
        whoosh_max_len_s: float | None = None,
    ) -> sound.SearchOutcome:  # fmt: skip
        raise AssertionError(f"an SFX search at job time: {words!r} for {intent!r}")


def test_the_mix_never_searches_for_an_effect(
    tmp_path: Path, fixture_clip: Path, specs: dict[str, styles.StyleSpec],
    library: sound.Library,
) -> None:  # fmt: skip
    judged = fixture.smoke_specs(specs, "vishva")["vishva"]
    request = _request("vishva", judged)
    plan = FakePlanner().plan_picture(request)
    story = FakePlanner().plan_sound(request, plan)
    stems = tmp_path / "stems"
    stems.mkdir()
    voice = stems / "voice.wav"
    ffmpeg.run(
        [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(fixture_clip), "-map", "0:a:0",
         "-ac", "1", "-ar", "48000", str(voice)],
        timeout_s=ffmpeg.MEASURE_TIMEOUT_S,
    )  # fmt: skip
    result = sound.build_mix(
        stems=stems, voice=voice, plan=plan, story=story, nums=judged.sound, library=library,
        runtime_s=fixture.DURATION_S, search=_NoSfxSearch(shelf=library),
    )  # fmt: skip
    assert result.cues
    assert all(library.entry(c.entry_id) is not None for c in result.cues)
    sheet = json.loads((stems / sound.CUES_NAME).read_text(encoding="utf-8"))
    assert {c["entry_id"] for c in sheet["cues"]} <= {e.id for e in library.sfx()}


def test_the_operator_remix_writes_the_mix_and_names_each_cue(
    tmp_path: Path, fixture_clip: Path, library: sound.Library,
    specs: dict[str, styles.StyleSpec],
) -> None:  # fmt: skip
    """The operator step's command: a job's plan, story and voice re-mixed into `--out`
    (the job folder untouched), one line per cue with its time, kind and file."""
    from shortsmith import jobs
    from shortsmith.sound import remix

    job = jobs.create(tmp_path / "data", style="vishva")
    request = _request("vishva", specs["vishva"])
    plan = FakePlanner().plan_picture(request)
    story = FakePlanner().plan_sound(request, plan)
    story = story.model_copy(update={"cues": [*story.cues, Cue(beat_id="b02", intent="tally_ding",
                                                                at="event")]})  # fmt: skip
    (job.work_dir / "plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    (job.work_dir / "sound.json").write_text(story.model_dump_json(), encoding="utf-8")
    stems = job.work_dir / "stems"
    stems.mkdir(parents=True)
    ffmpeg.run(
        [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(fixture_clip), "-map", "0:a:0",
         "-ac", "1", "-ar", "48000", str(stems / "voice.wav")],
        timeout_s=ffmpeg.MEASURE_TIMEOUT_S,
    )  # fmt: skip
    before = sorted(p.name for p in stems.iterdir())
    out = tmp_path / "work" / "070"
    result = remix.remix(job.path, out, library=library, log=False)
    assert (out / remix.MIX_NAME).is_file()
    assert sorted(p.name for p in stems.iterdir()) == before, "the job folder is untouched"
    lines = remix.cue_lines(result)
    assert len(lines) == len(result.cues) > 0
    assert all(line.split()[2] in CUE_KINDS for line in lines), lines
    assert all("files/sfx_" in line for line in lines)
    assert not [c for c in result.cues if c.intent == "tally_ding"]


# --- the fake planner -----------------------------------------------------------------------


def _request(name: str, spec: styles.StyleSpec) -> PlanRequest:
    from shortsmith.contracts import Constraints

    return PlanRequest(
        brief="", style=PlanStyle(name=name, status="shipped", numbers=spec.numbers(), prose=""),
        style_note="",
        transcript=Transcript(duration_s=fixture.DURATION_S, segments=[], words=[]),
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )  # fmt: skip


@pytest.mark.parametrize("name", ["explainer", "vishva", "fastfacts"])
def test_the_fake_story_speaks_only_the_palette(
    name: str, specs: dict[str, styles.StyleSpec]
) -> None:
    judged = fixture.smoke_specs(specs, name)[name]
    request = _request(name, judged)
    plan = FakePlanner().plan_picture(request)
    story = FakePlanner().plan_sound(request, plan)
    assert {c.intent for c in story.cues} <= set(CUE_KINDS)
    beats = {b.id: b for b in plan.beats}
    whooshes = [c for c in story.cues if c.intent == "whoosh"]
    assert len(whooshes) == 1 and whooshes[0].at == "start"
    assert beats[whooshes[0].beat_id].enter != "cut"
    ticks = [c for c in story.cues if c.intent == "tick"]
    if any(grammar.pops_in(b) for b in plan.beats):
        assert len(ticks) == 1 and ticks[0].at == "event"
        assert grammar.pops_in(beats[ticks[0].beat_id])
    result = grammar.validate_sound(story, plan, judged)
    assert not isinstance(result, grammar.Violations), result


def test_the_fixture_library_holds_one_file_per_kind(library: sound.Library) -> None:
    kinds = sorted(tag for e in library.sfx() for tag in e.tags.intent)
    assert kinds == sorted(CUE_KINDS)
    tick = library.entry("sfx_tick")
    assert isinstance(tick, AudioEntry) and tick.duration_s <= 0.25
