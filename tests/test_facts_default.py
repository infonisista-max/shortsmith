"""087: a facts-default bed, learned from the references, before any random search.

The default mood is the one with the largest runtime share over the Tier A and B short
cards' parts (long-form, `null` parts and cards 086 skips left out). The profile of the
bed fact channels use lives in `assets/audio/facts_default.yaml`, with each number's
source; a candidate is ranked by its distance to it, measured in numpy. The director
takes an approved bed tagged `facts_default` after the planned mood + flavour and, where
the style's `sound.facts_default_first` says so, before a same-mood bed of another
flavour; the Freesound search only when the library has no such bed at all.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shortsmith import app as app_module
from shortsmith import fixture, render, sound, styles
from shortsmith.contracts import AudioEntry, AudioTags, BedSegment, PicturePlan, SoundStory
from shortsmith.fixture import make_wav
from shortsmith.planner import FakePlanner
from shortsmith.presenter import FakeFaceDetector
from shortsmith.qa.gate import FakeGate
from shortsmith.reference import MusicChange, Part, ReferenceInventoryV2
from shortsmith.render import FakeRenderer
from shortsmith.sound import facts_default as fd
from shortsmith.sound import load_catalogue
from shortsmith.sound import shortlist as sl
from shortsmith.sound.kinds import BED, load_kinds
from shortsmith.transcriber import FakeTranscriber
from tests.test_app import (
    PASSCODE,
    SPECS,
    _settings,  # pyright: ignore[reportPrivateUsage]
    login,
)
from tests.test_bed_changes import _planned  # pyright: ignore[reportPrivateUsage]
from tests.test_shortlist import (
    BASS_ONLY,
    Tape,
    _sources,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_worked_examples import _card  # pyright: ignore[reportPrivateUsage]

SR = 22050
# An A-minor sub-bass drone (A1, C2 and E2 under a slow pulse), with an A3 / C4 / E4 layer
# in the speech band so a phone speaker plays it (069); and a bright C-major arpeggio
# (C5 E5 G5 C6, a quarter second each) over a steady G2.
DARK = (
    "(0.3*sin(2*PI*55*t)+0.15*sin(2*PI*65.41*t)+0.2*sin(2*PI*220*t)"
    "+0.22*sin(2*PI*261.63*t)+0.22*sin(2*PI*329.63*t))*(0.8+0.2*sin(2*PI*0.5*t))"
)
BRIGHT = (
    "0.3*sin(2*PI*98*t)+0.4*exp(-6*mod(t,0.25))*("
    "if(lt(mod(t,1),0.25),sin(2*PI*523.25*t),"
    "if(lt(mod(t,1),0.5),sin(2*PI*659.25*t),"
    "if(lt(mod(t,1),0.75),sin(2*PI*783.99*t),sin(2*PI*1046.5*t)))))"
)


# --- the default mood, learned ----------------------------------------------------------------


def _parts_card(
    vid: str, parts: list[tuple[str, float, float, str | None]], *, tier: str = "A",
    changes: bool = True,
) -> ReferenceInventoryV2:  # fmt: skip
    built = [Part(part=p, start_s=a, end_s=b, music_mood=m) for p, a, b, m in parts]  # pyright: ignore[reportArgumentType]
    moved = [
        MusicChange(at_s=after.start_s, from_part=before.part, to_part=after.part, how="crossfade")
        for before, after in zip(built, built[1:], strict=False)
        if before.music_mood != after.music_mood
    ]
    return _card(vid, tier=tier).model_copy(
        update={"parts": built, "music_changes": moved if changes else [],
                "duration_s": parts[-1][2]}  # fmt: skip
    )


def test_the_largest_runtime_share_wins_over_hand_built_cards() -> None:
    lines: list[str] = []
    cards = [
        _parts_card("tense40", [("hook", 0, 40, "tense_dramatic"),
                                ("reveal", 40, 60, "calm_ambient")]),
        _parts_card("pulse30", [("hook", 0, 30, "investigative_pulse"), ("reveal", 30, 50, None)],
                    tier="B"),
        # long-form: 600 s of calm would win if it counted
        _parts_card("longform", [("hook", 0, 600, "calm_ambient")]),
        # 086 skips it: the parts change mood with no music change
        _parts_card("nochange", [("hook", 0, 30, "calm_ambient"),
                                 ("reveal", 30, 60, "calm_ambient"),
                                 ("ending", 60, 90, "investigative_pulse")], changes=False),
        _parts_card("ours", [("hook", 0, 60, "calm_ambient")], tier="own"),
    ]  # fmt: skip
    learned = fd.default_mood(cards, short_max_s=180.0, log=lines.append)
    assert learned is not None
    assert learned.mood == "tense_dramatic"
    assert learned.runner_up == "investigative_pulse"
    assert learned.shares == pytest.approx(
        {"tense_dramatic": 40 / 90, "investigative_pulse": 30 / 90, "calm_ambient": 20 / 90}
    )
    text = "\n".join(lines)
    assert "longform" in text and "long-form" in text
    assert "nochange" in text and "skipped" in text
    assert "tense_dramatic" in lines[-1] and "investigative_pulse" in lines[-1]


def test_a_tie_goes_to_the_mood_more_cards_carry_and_says_so() -> None:
    lines: list[str] = []
    cards = [
        _parts_card("one", [("hook", 0, 30, "tense_dramatic")]),
        _parts_card("two", [("hook", 0, 15, "investigative_pulse")]),
        _parts_card("three", [("hook", 0, 15, "investigative_pulse")]),
    ]
    learned = fd.default_mood(cards, short_max_s=180.0, log=lines.append)
    assert learned is not None and learned.mood == "investigative_pulse"
    assert any("tie" in line and "cards" in line for line in lines), lines


def test_no_short_card_learns_no_mood() -> None:
    assert fd.default_mood([], short_max_s=180.0, log=lambda _: None) is None


def test_the_frozen_v2_cards_name_investigative_pulse() -> None:
    lines: list[str] = []
    profile = fd.load_profile()
    frozen = Path(__file__).parent / "fixtures" / "reference" / "inventory_v2"
    learned = fd.learned_mood(frozen, profile=profile, log=lines.append)
    assert learned is not None and learned.mood == "investigative_pulse", lines
    assert learned.runner_up == "tense_dramatic"
    assert any("id00R-3OmJ0" in line and "long-form" in line for line in lines), lines


# --- the profile --------------------------------------------------------------------------------


def test_the_committed_profile_loads_with_its_queries() -> None:
    profile = fd.load_profile()
    assert profile.mode == "minor"
    assert profile.percussive_share.about == pytest.approx(0.15)
    assert profile.percussive_share.low is not None and profile.percussive_share.high is not None
    assert profile.percussive_share.low <= 0.15 <= profile.percussive_share.high
    assert profile.sub_bass_share.low is not None
    assert profile.above_1khz_share.high is not None
    assert profile.harmonic_change.high is not None
    assert "dark minimal bass" in profile.queries and "sub bass drone" in profile.queries
    assert profile.short_max_s > 60


PROFILE_TEXT = fd.PROFILE_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ("about: 0.15", "about: 0.5", "percussive_share"),
        ("{max: 0.04}", "{max: 1.4}", "above_1khz_share"),
        ("mode: minor", "mode: lydian", "mode"),
        ("vocals: false", "vocals: true", "vocals"),
    ],
)
def test_a_value_off_its_stated_range_stops_the_loader_naming_the_key(
    tmp_path: Path, old: str, new: str, key: str
) -> None:
    assert old in PROFILE_TEXT, old
    path = tmp_path / "facts_default.yaml"
    path.write_text(PROFILE_TEXT.replace(old, new), encoding="utf-8")
    with pytest.raises(fd.ProfileError, match=key):
        fd.load_profile(path)


def test_an_unknown_key_stops_the_loader(tmp_path: Path) -> None:
    path = tmp_path / "facts_default.yaml"
    path.write_text(PROFILE_TEXT + "\nloudness: 3\n", encoding="utf-8")
    with pytest.raises(fd.ProfileError, match="loudness"):
        fd.load_profile(path)


def _signal(kind: str, seconds: float = 8.0) -> np.ndarray[Any, np.dtype[np.float64]]:
    t = np.arange(int(seconds * SR)) / SR
    if kind == "drone":
        pulse = 0.8 + 0.2 * np.sin(2 * np.pi * 0.5 * t)
        tones = (0.4 * np.sin(2 * np.pi * 55 * t) + 0.2 * np.sin(2 * np.pi * 65.41 * t)
                 + 0.1 * np.sin(2 * np.pi * 82.41 * t))  # fmt: skip
        return tones * pulse
    notes = np.array([523.25, 659.25, 783.99, 1046.5])
    step = (t * 4).astype(int) % 4
    decay = np.exp(-6 * np.mod(t, 0.25))
    return 0.5 * decay * np.sin(2 * np.pi * notes[step] * t)


def test_a_sub_bass_drone_is_nearer_than_a_bright_arpeggio_and_a_vocal_never_ranks() -> None:
    profile = fd.load_profile()
    drone = fd.measure_samples(_signal("drone"), SR, profile)
    bright = fd.measure_samples(_signal("arpeggio"), SR, profile)
    assert drone.minor and not bright.minor
    assert drone.sub_bass_share > 0.5 and bright.sub_bass_share < 0.01
    assert drone.above_1khz_share < 0.01 < bright.above_1khz_share
    assert drone.percussive_share < bright.percussive_share
    assert drone.harmonic_change < bright.harmonic_change
    assert fd.distance(drone, profile) < fd.distance(bright, profile)
    kind = load_kinds().kind(BED)
    ranked = fd.rank(
        [("bright arp synth", ["synth"], bright), ("sub bass drone", ["drone"], drone),
         ("choir vocal drone", ["drone"], drone)],
        profile, kind,
    )  # fmt: skip
    assert [i for i, _ in ranked] == [1, 0], "the vocal file never ranks"
    assert ranked[0][1] == pytest.approx(fd.distance(drone, profile))


# --- the director ---------------------------------------------------------------------------


def _bed(entry_id: str, mood: str, *, flavour: str | None = None, facts: bool = False,
         file: str | None = None) -> AudioEntry:  # fmt: skip
    return AudioEntry(
        id=entry_id, kind="bed", file=file or f"files/{entry_id}.wav", source="test",
        source_url=f"https://example.org/{entry_id}", licence="CC0-1.0", duration_s=8.0,
        tags=AudioTags(mood=[mood], flavour=[flavour] if flavour else [],
                       role=["facts_default"] if facts else []),
        energy=3,
    )  # fmt: skip


KING_SAUD = BedSegment(part_from="hook", mood="investigative_pulse", flavour="middle_east")


def _king_saud() -> tuple[PicturePlan, SoundStory]:
    plan, story = _planned("vishva")
    return plan, story.model_copy(update={"bed": [KING_SAUD], "change": None})


def _first(library: sound.Library, *, first: bool = True,
           segment: BedSegment = KING_SAUD) -> tuple[list[str], list[str], str | None]:  # fmt: skip
    plan, story = _king_saud()
    story = story.model_copy(update={"bed": [segment]})
    nums = SPECS["vishva"].sound.model_copy(update={"facts_default_first": first})
    score, lines, fallback = next(sound.score_candidates(library, story, plan, nums))
    assert score is not None, lines
    return [b.id for b in score.beds], list(lines), fallback


def _library(*entries: AudioEntry) -> sound.Library:
    return sound.Library(root=Path("unused"), entries=entries)


def test_every_shipped_style_puts_the_facts_default_first() -> None:
    for name in styles.shipped(SPECS):
        assert SPECS[name].sound.facts_default_first is True, name


def test_a_style_without_the_switch_stops_the_loader_naming_the_style(tmp_path: Path) -> None:
    target = tmp_path / "styles"
    shutil.copytree(styles.STYLES_DIR, target)
    path = target / "vishva.md"
    front, body = styles.split_front_matter(path.read_text(encoding="utf-8"))
    del front["sound"]["facts_default_first"]
    path.write_text(f"---\n{yaml.safe_dump(front, sort_keys=False)}---\n{body}", encoding="utf-8")
    with pytest.raises(styles.StyleError, match=r"vishva.*facts_default_first"):
        styles.load_all(render.registry(), target)


def test_king_saud_a_flavour_miss_takes_the_facts_default_before_a_same_mood_bed() -> None:
    library = _library(
        _bed("pulse_plain", "investigative_pulse"), _bed("tense_gulf", "tense_dramatic",
                                                         flavour="middle_east"),
        _bed("dark_bass", "investigative_pulse", facts=True),
    )  # fmt: skip
    beds, lines, fallback = _first(library)
    assert beds == ["dark_bass"]
    line = (
        "fallback bed: facts_default dark_bass for investigative_pulse/middle_east, no approved bed"
    )
    assert line in lines
    assert fallback == line


def test_king_saud_without_a_facts_default_takes_the_same_mood_bed() -> None:
    library = _library(_bed("pulse_plain", "investigative_pulse"))
    beds, lines, fallback = _first(library)
    assert beds == ["pulse_plain"] and fallback is None, lines


def test_king_saud_under_a_style_that_keeps_076s_order_takes_the_same_mood_bed() -> None:
    library = _library(
        _bed("pulse_plain", "investigative_pulse"), _bed("dark_bass", "calm_ambient", facts=True)
    )
    beds, _, fallback = _first(library, first=False)
    assert beds == ["pulse_plain"] and fallback is None


def test_the_planned_mood_and_flavour_still_win_over_the_facts_default() -> None:
    library = _library(
        _bed("dark_bass", "investigative_pulse", facts=True),
        _bed("pulse_gulf", "investigative_pulse", flavour="middle_east"),
    )
    beds, _, fallback = _first(library)
    assert beds == ["pulse_gulf"] and fallback is None


@pytest.mark.parametrize("first", [True, False])
def test_a_mood_miss_takes_the_facts_default(first: bool) -> None:
    library = _library(_bed("calm", "calm_ambient"), _bed("dark_bass", "calm_ambient", facts=True))
    beds, lines, _ = _first(library, first=first)
    assert beds == ["dark_bass"]
    assert ("fallback bed: facts_default dark_bass for investigative_pulse/middle_east, no "
            "approved bed") in lines  # fmt: skip
    plain = BedSegment(part_from="hook", mood="investigative_pulse")
    _, lines, _ = _first(library, first=first, segment=plain)
    assert "fallback bed: facts_default dark_bass for investigative_pulse, no approved bed" in lines


def _two_misses(library: sound.Library) -> tuple[sound.Score, list[str]]:
    """King Saud with a change at the reveal: both segments middle_east, both missing."""
    plan, story = _planned("vishva")
    reveal = BedSegment(part_from="reveal", mood="tense_dramatic", flavour="middle_east")
    story = story.model_copy(update={"bed": [KING_SAUD, reveal]})
    assert story.change is not None
    score, lines, _ = next(sound.score_candidates(library, story, plan, SPECS["vishva"].sound))
    assert score is not None, lines
    return score, list(lines)


def test_two_misses_never_change_to_the_bed_already_playing() -> None:
    library = _library(
        _bed("dark_bass", "calm_ambient", facts=True), _bed("tense_plain", "tense_dramatic")
    )
    score, lines = _two_misses(library)
    assert [b.id for b in score.beds] == ["dark_bass", "tense_plain"], lines
    assert score.how is not None and score.change_s is not None


def test_two_misses_with_only_the_facts_default_play_it_through() -> None:
    score, lines = _two_misses(_library(_bed("dark_bass", "calm_ambient", facts=True)))
    assert [b.id for b in score.beds] == ["dark_bass"]
    assert score.how is None and score.change_s is None
    assert "bed dark_bass plays through reveal: no other approved bed, the change is dropped" in (
        lines
    )
    assert not any(line.startswith("bed change at") for line in lines), lines


def test_no_facts_default_and_no_same_mood_bed_is_the_freesound_fallback_as_before() -> None:
    library = _library(_bed("calm", "calm_ambient"))
    shelf = _library(_bed("found", "calm_ambient"))
    search = sound.FakeAudioSearch(shelf)
    plan, story = _king_saud()
    items = list(sound.score_candidates(library, story, plan, SPECS["vishva"].sound, search=search))
    score, lines, fallback = next((s, ls, f) for s, ls, f in items if s is not None)
    assert fallback == "fallback bed: investigative_pulse, no approved bed"
    assert lines[0] == fallback
    assert search.calls and score is not None and score.beds[0].id == "found"


def test_the_facts_default_still_goes_through_069(
    tmp_path: Path, voice: Path
) -> None:
    root = tmp_path / "audio"
    (root / "files").mkdir(parents=True)
    make_wav(root / "files" / "sub_only.wav", expr=BASS_ONLY, duration_s=8.0)
    library = sound.Library(root=root, entries=(
        _bed("sub_only", "calm_ambient", facts=True, file="files/sub_only.wav"),
    ))  # fmt: skip
    plan, story = _king_saud()
    stems = tmp_path / "stems"
    stems.mkdir()
    shutil.copy(voice, stems / "voice.wav")
    result = sound.build_mix(
        stems=stems, voice=stems / "voice.wav", plan=plan, story=story,
        nums=SPECS["vishva"].sound, library=library, runtime_s=fixture.DURATION_S,
    )  # fmt: skip
    text = "\n".join(result.notes)
    assert "fallback bed: facts_default sub_only" in text
    assert "a phone speaker does not play this bed" in text
    assert result.beds == () and result.balance.bed_dropped is not None


# --- 069's lines carry the bed level ------------------------------------------------------------


def test_a_speech_band_refusal_names_the_bed_level() -> None:
    nums = SPECS["vishva"].sound
    over = sound.margin_problem(28.7, nums, level_db=-14.0)
    assert over is not None and "-14.0 dB" in over and "bed level" in over
    under = sound.margin_problem(9.0, nums, level_db=-10.4)
    assert under is not None and "-10.4 dB" in under


# --- the shortlist slot ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def facts_audio(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("facts-audio")
    return {
        "mid": make_wav(root / "mid.wav", expr=DARK, duration_s=8.0),
        "bass": make_wav(root / "bass.wav", expr=BASS_ONLY, duration_s=8.0),
        "click": make_wav(root / "click.wav", expr="0.8*sin(2*PI*1400*t)*exp(-30*t)",
                          duration_s=0.2),
        "dark": make_wav(root / "dark.wav", expr=DARK, duration_s=8.0),
        "bright": make_wav(root / "bright.wav", expr=BRIGHT, duration_s=8.0),
    }


@pytest.fixture(scope="module")
def facts_voice(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return sl.reference_voice(tmp_path_factory.mktemp("facts-voice") / "voice.wav")


def _facts_tape(audio: dict[str, Path]) -> Tape:
    tape = Tape(audio)
    # Openverse, asked first, finds the bright file; Freesound the dark one.
    tape.files["https://cdn.example.test/openverse/tense-cinematic.mp3"] = audio["bright"]
    tape.files["https://cdn.freesound.org/previews/9/9002_1-hq.mp3"] = audio["dark"]
    return tape


def _facts_build(
    tape: Tape, tmp_path: Path, voice: Path, lines: list[str] | None = None
) -> sl.Shortlist:
    library = tmp_path / "audio"
    library.mkdir(exist_ok=True)
    (library / "catalog.yaml").write_text("entries: []\n", encoding="utf-8")
    nums = render.loaded_styles()[styles.DEFAULT].sound
    return sl.build(
        sl.load_slots(), _sources(tape), only=[fd.FACTS_DEFAULT], out_dir=tmp_path / "shortlist",
        library_root=library, inbox=library / "inbox",
        checker=sl.Checker(voice=voice, nums=nums, kinds=load_kinds(), profile=fd.load_profile()),
        log=(lines if lines is not None else []).append,
    )  # fmt: skip


def test_the_committed_slots_carry_facts_default_with_profile_queries_first() -> None:
    slots = sl.load_slots()
    slot = slots.slots[fd.FACTS_DEFAULT]
    profile = fd.load_profile()
    assert slot.kind == "bed" and slot.group == "facts_default"
    assert slot.words[: len(profile.queries)] == profile.queries
    assert slot.words[len(profile.queries):] == slots.slots["investigative_pulse"].words


def test_the_facts_default_slot_asks_profile_words_first_and_ranks_by_distance(
    tmp_path: Path, facts_audio: dict[str, Path], facts_voice: Path
) -> None:
    tape = _facts_tape(facts_audio)
    lines: list[str] = []
    shortlist = _facts_build(tape, tmp_path, facts_voice, lines)
    asked = [r.url.params["q"] for r in tape.searches(sl.OPENVERSE_AUDIO_URL)]
    profile = fd.load_profile()
    assert asked[: len(profile.queries)] == [f"{q} music" for q in profile.queries]
    assert "investigative pulse music" in asked[len(profile.queries):]
    kept = shortlist.slots[fd.FACTS_DEFAULT]
    assert [c.key for c in kept] == [
        "freesound:9002", "openverse:0b5c1d2e-0001-4a6b-9c3d-000000000001",
    ], "nearest first, not the sources' order"
    distances = [c.distance for c in kept]
    assert all(d is not None for d in distances) and distances == sorted(distances)  # pyright: ignore[reportArgumentType]
    assert set(kept[0].profile) == {"harmonic_change", "percussive_share", "sub_bass_share",
                                    "above_1khz_share"}  # fmt: skip
    assert kept[0].tags == AudioTags(mood=["investigative_pulse"], role=["facts_default"])
    # 069's refusal of the bass-only bed names the level it was measured at
    assert any("Low Drone Soundtrack" in line and "bed level -14.0 dB" in line for line in lines)


def test_a_yes_on_a_facts_default_candidate_writes_the_tag_and_the_page_shows_the_distance(
    tmp_path: Path, facts_audio: dict[str, Path], facts_voice: Path
) -> None:
    _facts_build(_facts_tape(facts_audio), tmp_path, facts_voice)
    library = tmp_path / "audio"
    app: FastAPI = app_module.create_app(
        _settings(tmp_path), transcriber=FakeTranscriber(), planner=FakePlanner(),
        specs=SPECS, renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False, shortlist_dir=tmp_path / "shortlist", audio_library=library,
    )  # fmt: skip
    with TestClient(app) as client:
        assert login(client, PASSCODE).status_code == 303
        text = client.get("/audio/shortlist").text
        assert "facts_default" in text and "distance" in text
        assert "sub-bass" in text and "above 1 kHz" in text and "percussive" in text
        assert 'name="role" value="facts_default"' in text
        first = sl.load_shortlist(tmp_path / "shortlist").slots[fd.FACTS_DEFAULT][0]
        yes = client.post(
            "/audio/shortlist/yes",
            data={"key": first.key, "mood": "investigative_pulse", "flavour": "",
                  "role": "facts_default"},  # fmt: skip
            follow_redirects=False,
        )
        assert yes.status_code == 303
    [entry] = load_catalogue(library / "catalog.yaml").entries
    assert entry.tags.role == ["facts_default"]
    sl.check_catalogue(library / "catalog.yaml")


def test_a_role_on_an_effect_is_off_the_closed_lists(tmp_path: Path) -> None:
    catalogue = tmp_path / "catalog.yaml"
    catalogue.write_text(
        "entries:\n"
        "  - {id: x, kind: sfx, file: sfx/x.wav, source: mixkit, licence: Mixkit Free License,\n"
        "     duration_s: 0.2, energy: 3, tags: {intent: [tick], role: [facts_default]}}\n",
        encoding="utf-8",
    )
    with pytest.raises(sound.SoundError, match="facts_default"):
        sl.check_catalogue(catalogue)
    catalogue.write_text(
        "entries:\n"
        "  - {id: y, kind: bed, file: beds/y.wav, source: mixkit, licence: Mixkit Free License,\n"
        "     duration_s: 9, energy: 3, tags: {mood: [calm_ambient], role: [jazz_default]}}\n",
        encoding="utf-8",
    )
    with pytest.raises(sound.SoundError, match="jazz_default"):
        sl.check_catalogue(catalogue)


def test_the_shortlist_json_keeps_distance_and_profile(
    tmp_path: Path, facts_audio: dict[str, Path], facts_voice: Path
) -> None:
    _facts_build(_facts_tape(facts_audio), tmp_path, facts_voice)
    written = json.loads((tmp_path / "shortlist" / sl.SHORTLIST_NAME).read_text("utf-8"))
    first = written["slots"][fd.FACTS_DEFAULT][0]
    assert first["distance"] is not None and first["profile"]["sub_bass_share"] > 0
