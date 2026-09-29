"""The audio shortlist and the approved library (ticket 075).

Both API sources answer recorded bodies through an `httpx.MockTransport` and every file
URL answers the bytes of a synthesised WAV, so the checks - licence, 068's kind check,
the length allowance, the sweep detector, 069's audibility - run on real samples with
no network. The voice the beds are judged against is the fixture clip through the 7.3
voice chain, as the tool builds it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shortsmith import app as app_module
from shortsmith import ffmpeg, render, styles, vocab
from shortsmith.contracts import AudioTags
from shortsmith.fixture import make_wav
from shortsmith.planner import FakePlanner
from shortsmith.presenter import FakeFaceDetector
from shortsmith.qa.gate import FakeGate
from shortsmith.render import FakeRenderer
from shortsmith.sound import SoundError, freesound, load_catalogue
from shortsmith.sound import shortlist as sl
from shortsmith.sound.kinds import load_kinds
from shortsmith.transcriber import FakeTranscriber
from tests.test_app import (
    PASSCODE,
    SPECS,
    _settings,  # pyright: ignore[reportPrivateUsage]
    login,
)

FIXTURES = Path(__file__).parent / "fixtures" / "shortlist"
KEY = SecretStr("test-token-not-a-real-one")
# 069's pair: a bed with a partial inside the speech band, and a bass-only one a phone
# speaker cannot play.
MID_BAND = "(0.25*sin(2*PI*110*t)+0.25*sin(2*PI*550*t))*(0.7+0.3*sin(2*PI*0.5*t))"
BASS_ONLY = "0.5*sin(2*PI*55*t)*(0.8+0.2*sin(2*PI*0.5*t))"
CLICK = "0.8*sin(2*PI*1400*t)*exp(-30*t)"


def _recorded(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def audio(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("shortlist-audio")
    return {
        "mid": make_wav(root / "mid.wav", expr=MID_BAND, duration_s=8.0),
        "bass": make_wav(root / "bass.wav", expr=BASS_ONLY, duration_s=8.0),
        "click": make_wav(root / "click.wav", expr=CLICK, duration_s=0.2),
    }


@pytest.fixture(scope="module")
def voice(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return sl.reference_voice(tmp_path_factory.mktemp("voice") / "voice.wav")


@pytest.fixture(scope="module")
def nums() -> styles.Sound:
    return render.loaded_styles()[styles.DEFAULT].sound


class Tape:
    """Freesound and Openverse answer their recorded bodies (a bed or an effect body by
    the request's own filter); every other URL is a file served from `files`."""

    def __init__(self, audio: dict[str, Path]) -> None:
        self.requests: list[httpx.Request] = []
        self.files: dict[str, Path] = {
            "https://cdn.example.test/openverse/tense-cinematic.mp3": audio["mid"],
            "https://cdn.example.test/openverse/dark-orchestral.mp3": audio["mid"],
            "https://cdn.example.test/openverse/low-drone.mp3": audio["bass"],
            "https://cdn.example.test/openverse/soft-pop-click.ogg": audio["click"],
            "https://cdn.freesound.org/previews/9/9001_1-hq.mp3": audio["mid"],
            "https://cdn.freesound.org/previews/9/9002_1-hq.mp3": audio["mid"],
            "https://cdn.freesound.org/previews/9/9003_1-hq.mp3": audio["mid"],
            "https://cdn.freesound.org/previews/7/7001_1-hq.mp3": audio["click"],
            "https://cdn.freesound.org/previews/7/7002_1-hq.mp3": audio["click"],
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url).split("?")[0]
        if url == freesound.API_URL:
            bed = "tag:music" in request.url.params.get("filter", "")
            body = _recorded(f"freesound_{'bed' if bed else 'effect'}.json")
            return httpx.Response(200, json=body)
        if url == sl.OPENVERSE_AUDIO_URL:
            bed = request.url.params.get("category") == "music"
            body = _recorded(f"openverse_{'bed' if bed else 'effect'}.json")
            return httpx.Response(200, json=body)
        if url.startswith(sl.OPENVERSE_AUDIO_URL):  # one sound by id
            sid = url.removeprefix(sl.OPENVERSE_AUDIO_URL).strip("/")
            hits = _recorded("openverse_bed.json")["results"]
            return httpx.Response(200, json=next(h for h in hits if h["id"] == sid))
        served = self.files.get(url)
        if served is None:
            return httpx.Response(404)
        return httpx.Response(200, content=served.read_bytes())

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def searches(self, prefix: str) -> list[httpx.Request]:
        return [r for r in self.requests if str(r.url).startswith(prefix)]

    def fetched(self) -> list[str]:
        return [
            str(r.url) for r in self.requests
            if not str(r.url).startswith((freesound.API_URL, sl.OPENVERSE_AUDIO_URL))
        ]  # fmt: skip


def _sources(tape: Tape) -> list[sl.Source]:
    client = tape.client()
    return [
        sl.OpenverseSource(client=client),
        sl.FreesoundSource(freesound.FreesoundAudioSearch(api_key=KEY, client=client)),
    ]


@pytest.fixture
def slots() -> sl.Slots:
    return sl.load_slots()


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "audio"
    root.mkdir()
    catalogue = root / "catalog.yaml"
    catalogue.write_text("# the operator's catalogue\nentries: []\n", encoding="utf-8")
    return root


def _build(
    tape: Tape, slots: sl.Slots, library: Path, tmp_path: Path, voice: Path,
    nums: styles.Sound, only: list[str], lines: list[str] | None = None,
) -> sl.Shortlist:  # fmt: skip
    return sl.build(
        slots, _sources(tape), only=only, out_dir=tmp_path / "shortlist",
        library_root=library, inbox=library / "inbox",
        checker=sl.Checker(voice=voice, nums=nums, kinds=load_kinds()),
        log=(lines if lines is not None else []).append,
    )  # fmt: skip


# --- the slots ----------------------------------------------------------------------------


def test_the_committed_slots_are_the_first_batch() -> None:
    slots = sl.load_slots()
    assert slots.keep == 3
    beds = [s.name for s in slots.slots.values() if s.kind == "bed"]
    assert beds == ["tense_dramatic", "investigative_pulse", "mysterious_curiosity",
                    "calm_ambient", "middle_east", "indian", "facts_default"]  # fmt: skip
    effects = {s.name: s.max_len_s for s in slots.slots.values() if s.kind == "sfx"}
    assert effects == {"tick": 0.25, "whoosh": 0.8, "bass": 1.5, "drum": 1.2, "thump": 0.8,
                       "ding": 0.8}  # fmt: skip
    assert slots.slots["middle_east"].group == "flavour"
    assert slots.slots["calm_ambient"].group == "mood"


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("keep: 3\nbeds: {anchor: music, slots: {eerie_scifi: [space]}}\neffects: {}\n",
         "eerie_scifi"),
        ("keep: 3\nbeds: {anchor: music, slots: {jazz: [jazz]}}\neffects: {}\n", "jazz"),
        ("keep: 3\nbeds: {anchor: music, slots: {}}\n"
         "effects: {kazoo: {max_len_s: 1, words: [k]}}\n", "kazoo"),
        ("keep: 3\nbeds: {anchor: music, slots: {calm_ambient: []}}\neffects: {}\n",
         "calm_ambient"),
        ("keep: 3\nbeds: {anchor: music, slots: {}}\neffects: {tick: {words: [tick]}}\n",
         "max_len_s"),
    ],
)  # fmt: skip
def test_a_slot_off_the_closed_lists_stops_the_loader(
    tmp_path: Path, text: str, problem: str
) -> None:
    path = tmp_path / "shortlist.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(sl.ShortlistError, match=problem):
        sl.load_slots(path)


# --- the API searches ---------------------------------------------------------------------


def test_a_bed_slot_asks_both_sources_with_the_music_anchor_and_the_licence_filter(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    tape = Tape(audio)
    _build(tape, slots, library, tmp_path, voice, nums, ["tense_dramatic"])
    openverse = tape.searches(sl.OPENVERSE_AUDIO_URL)
    assert openverse, "Openverse is the main source for beds"
    first = openverse[0].url.params
    assert first["license"] == "cc0,by"
    assert first["category"] == "music"
    assert first["q"] == "tense dramatic music"
    for request in tape.searches(freesound.API_URL):
        assert request.url.params["query"].endswith("music")
        assert "tag:music" in request.url.params["filter"]
        assert freesound.LICENCE_FILTER in request.url.params["filter"]


def test_a_bed_slot_refuses_nc_and_vocals_and_lets_the_ear_judge_a_quiet_bed(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    tape = Tape(audio)
    lines: list[str] = []
    roomy = slots.model_copy(update={"keep": 4})  # every recorded hit is asked
    shortlist = _build(tape, roomy, library, tmp_path, voice, nums, ["tense_dramatic"], lines)
    kept = shortlist.slots["tense_dramatic"]
    assert [c.key for c in kept] == [
        "openverse:0b5c1d2e-0001-4a6b-9c3d-000000000001",
        "openverse:0b5c1d2e-0003-4a6b-9c3d-000000000003", "freesound:9002",
    ]
    text = "\n".join(lines)
    # a CC BY-NC answer is refused, from either source, before any download
    assert "Dark Orchestral Theme" in text and "CC BY-NC 3.0" in text
    assert "Suspense score" in text and "CC BY-NC 4.0" in text
    assert not any("dark-orchestral" in u or "9003_" in u for u in tape.fetched())
    # a vocal "bed" is refused by 068's check, never downloaded
    assert "Choir vocal ambient" in text and "forbidden for bed" in text
    assert not any("9001_" in u for u in tape.fetched())
    # 088: a bass-only bed over 069's ceiling is no longer skipped; it reaches the page
    # with the note, its margin and the level it was measured at, and the ear decides
    drone = kept[1]
    assert drone.name == "Low Drone Soundtrack"
    assert drone.margin_db is not None and drone.margin_db > nums.speech_band_margin_max_db
    assert drone.level_db == nums.bed_db_under_voice
    assert drone.note is not None and "may be hard to hear on a phone speaker" in drone.note
    assert "speech_band_margin_max_db" in drone.note
    assert kept[0].note is None
    first = kept[0]
    assert first.licence == "CC BY 4.0" and first.author == "Anna Keller"
    assert first.page_url == "https://www.jamendo.com/track/1500001"
    assert first.credit.startswith('"Tense Cinematic Strings" by Anna Keller')
    assert first.tags == AudioTags(mood=["tense_dramatic"])
    assert first.margin_db is not None
    assert nums.speech_band_margin_db <= first.margin_db <= nums.speech_band_margin_max_db
    assert (tmp_path / "shortlist" / first.file).is_file()
    written = json.loads((tmp_path / "shortlist" / sl.SHORTLIST_NAME).read_text("utf-8"))
    assert [c["key"] for c in written["slots"]["tense_dramatic"]] == [c.key for c in kept]


def test_an_effect_over_its_length_never_downloads(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    tape = Tape(audio)
    lines: list[str] = []
    shortlist = _build(tape, slots, library, tmp_path, voice, nums, ["tick"], lines)
    for request in tape.searches(freesound.API_URL):
        assert request.url.params["filter"].startswith("duration:[0 TO 0.25]")
        assert "tag:music" not in request.url.params["filter"]
    assert tape.searches(sl.OPENVERSE_AUDIO_URL)[0].url.params["category"] == "sound_effect"
    assert not any("7002_" in u for u in tape.fetched()), "1.2 s is over tick's 0.25 s"
    assert any("Tick long" in line and "0.25" in line for line in lines)
    keys = [c.key for c in shortlist.slots["tick"]]
    assert keys == ["freesound:7001", "openverse:7e1f0000-0001-4c2d-8e9f-000000000011"], (
        "effects: Freesound first"
    )
    assert shortlist.slots["tick"][0].tags == AudioTags(intent=["tick"])


def test_at_most_keep_candidates_per_slot(
    tmp_path: Path, audio: dict[str, Path], library: Path, voice: Path, nums: styles.Sound,
) -> None:  # fmt: skip
    slots = sl.load_slots()
    one = slots.model_copy(update={"keep": 1})
    shortlist = _build(Tape(audio), one, library, tmp_path, voice, nums, ["tense_dramatic"])
    assert len(shortlist.slots["tense_dramatic"]) == 1


# --- the drop folder ----------------------------------------------------------------------


def test_a_drop_file_without_a_filled_sidecar_needs_a_source_and_cannot_be_approved(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    inbox = library / "inbox"
    inbox.mkdir()
    (inbox / "Night Watch.mp3").write_bytes(audio["mid"].read_bytes())
    shortlist = _build(Tape(audio), slots, library, tmp_path, voice, nums, ["calm_ambient"])
    sidecar = inbox / "Night Watch.mp3.source.yaml"
    assert sidecar.is_file()
    template = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    assert set(template) == {"source", "page_url", "attribution", "slot"}
    assert len(sidecar.read_text(encoding="utf-8").strip().splitlines()) == 1
    [waiting] = shortlist.inbox
    assert waiting.needs_source and waiting.name == "Night Watch.mp3"
    with pytest.raises(sl.ShortlistError, match="needs source"):
        sl.approve(
            waiting.key, tags=AudioTags(mood=["calm_ambient"]),
            out_dir=tmp_path / "shortlist", library_root=library,
        )  # fmt: skip
    assert load_catalogue(library / "catalog.yaml").entries == ()


def test_a_filled_drop_file_gets_its_source_licence_template(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    inbox = library / "inbox"
    inbox.mkdir()
    (inbox / "Night Watch.mp3").write_bytes(audio["mid"].read_bytes())
    (inbox / "Night Watch.mp3.source.yaml").write_text(
        '{source: incompetech, page_url: "https://incompetech.com/night-watch", '
        'attribution: "Night Watch by Kevin MacLeod (incompetech.com)", slot: calm_ambient}\n',
        encoding="utf-8",
    )
    shortlist = _build(Tape(audio), slots, library, tmp_path, voice, nums, ["calm_ambient"])
    drop = [c for c in shortlist.slots["calm_ambient"] if c.source == "incompetech"]
    assert len(drop) == 1 and not drop[0].needs_source
    assert drop[0].licence == "CC BY 4.0"
    assert drop[0].credit == "Night Watch by Kevin MacLeod (incompetech.com)"
    assert shortlist.inbox == []
    entry = sl.approve(
        drop[0].key, tags=AudioTags(mood=["calm_ambient"]),
        out_dir=tmp_path / "shortlist", library_root=library,
    )  # fmt: skip
    assert entry.source == "incompetech" and entry.licence == "CC BY 4.0"
    assert (library / entry.file).is_file() and entry.file.startswith("beds/")


# 088: a bed entirely inside the speech band. Levelled on its full-band mean it clears the
# band by 14.1 dB against the reference voice, so the test raises the floor over that.
IN_BAND = "sin(2*PI*1000*t)*(0.1+0.6*lt(mod(t,3),1))"
IN_BAND_MARGIN_DB = 14.1


def test_a_drop_bed_over_the_ceiling_reaches_the_page_and_one_under_the_floor_does_not(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    """088 (Trap Hamza): over 069's ceiling a drop-folder bed is no longer skipped; it
    reaches the page with the note, its margin and the level it was measured at. The
    floor is unchanged: a bed that crowds the voice is skipped as before."""
    inbox = library / "inbox"
    inbox.mkdir()
    (inbox / "Trap Hamza.mp3").write_bytes(audio["bass"].read_bytes())
    make_wav(inbox / "Crowded.wav", expr=IN_BAND, duration_s=8.0)
    for name in ("Trap Hamza.mp3", "Crowded.wav"):
        (inbox / f"{name}.source.yaml").write_text(
            f'{{source: mixkit, page_url: "https://mixkit.co/{name}", attribution: "", '
            "slot: investigative_pulse}\n",
            encoding="utf-8",
        )
    floor = nums.model_copy(update={"speech_band_margin_db": IN_BAND_MARGIN_DB + 2})
    lines: list[str] = []
    shortlist = _build(Tape(audio), slots, library, tmp_path, voice, floor,
                       ["investigative_pulse"], lines)  # fmt: skip
    drops = [c for c in shortlist.slots["investigative_pulse"] if c.source == "mixkit"]
    assert [c.name for c in drops] == ["Trap Hamza.mp3"], lines
    [hamza] = drops
    assert hamza.margin_db is not None and hamza.margin_db > nums.speech_band_margin_max_db
    assert hamza.level_db == nums.bed_db_under_voice
    assert hamza.note is not None and "may be hard to hear on a phone speaker" in hamza.note
    assert f"{hamza.margin_db:.1f} dB" in hamza.note
    crowded = [line for line in lines if "Crowded.wav" in line]
    assert crowded and "under sound.speech_band_margin_db" in crowded[-1], lines


def test_every_bed_candidate_has_a_preview_under_the_voice_at_the_mix_level(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    """088: the page plays the bed the way the viewer hears it - under the reference
    voice, `bed_db_under_voice` under it as the mix levels it - beside the bed alone. An
    effect has none, and a yes never writes the preview into the library."""
    shortlist = _build(Tape(audio), slots, library, tmp_path, voice, nums,
                       ["tense_dramatic", "tick"])  # fmt: skip
    out = tmp_path / "shortlist"
    for candidate in shortlist.slots["tense_dramatic"]:
        assert candidate.preview is not None, candidate.name
        preview = out / candidate.preview
        assert preview.is_file() and preview != out / candidate.file
        # voice plus a bed: louder than the voice alone, and as long as the voice
        mixed, alone = ffmpeg.mean_volume_db(preview), ffmpeg.mean_volume_db(voice)
        assert mixed is not None and alone is not None and mixed > alone
        assert ffmpeg.duration_s(preview) == pytest.approx(ffmpeg.duration_s(voice), abs=0.1)
    assert all(c.preview is None for c in shortlist.slots["tick"])
    bed = shortlist.slots["tense_dramatic"][0]
    entry = sl.approve(bed.key, tags=AudioTags(mood=["tense_dramatic"]), out_dir=out,
                       library_root=library)  # fmt: skip
    text = (library / "catalog.yaml").read_text(encoding="utf-8")
    assert "preview" not in text and "under_voice" not in text
    assert [p.name for p in (library / "beds").iterdir()] == [Path(entry.file).name]


# --- yes and no ---------------------------------------------------------------------------


def test_a_yes_writes_a_valid_catalogue_entry_with_closed_tags(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    shortlist = _build(Tape(audio), slots, library, tmp_path, voice, nums,
                       ["tense_dramatic", "tick"])  # fmt: skip
    bed = shortlist.slots["tense_dramatic"][0]
    entry = sl.approve(
        bed.key, tags=AudioTags(mood=["tense_dramatic"], flavour=["middle_east"]),
        out_dir=tmp_path / "shortlist", library_root=library,
    )  # fmt: skip
    tick = shortlist.slots["tick"][0]
    sl.approve(tick.key, tags=AudioTags(intent=["tick"]), out_dir=tmp_path / "shortlist",
               library_root=library)  # fmt: skip
    catalogue = library / "catalog.yaml"
    assert catalogue.read_text(encoding="utf-8").startswith("# the operator's catalogue")
    loaded = load_catalogue(catalogue)
    assert [e.id for e in loaded.entries] == [
        "openverse_0b5c1d2e-0001-4a6b-9c3d-000000000001", "freesound_7001",
    ]
    first = loaded.entries[0]
    assert first == entry
    assert first.kind == "bed" and first.file.startswith("beds/")
    assert (library / first.file).is_file()
    assert first.source == "openverse" and first.source_url == bed.page_url
    assert first.licence == "CC BY 4.0" and first.author == "Anna Keller"
    assert first.source_name == "Tense Cinematic Strings"
    assert first.source_tags == ["cinematic", "tense"]
    assert first.credit is not None and first.credit.startswith('"Tense Cinematic Strings"')
    assert first.tags == AudioTags(mood=["tense_dramatic"], flavour=["middle_east"])
    assert first.duration_s == pytest.approx(8.0, abs=0.05)
    assert loaded.entries[1].kind == "sfx" and loaded.entries[1].file.startswith("sfx/")
    # the startup check accepts it
    sl.check_catalogue(catalogue)
    # and the candidate has left the page
    after = sl.load_shortlist(tmp_path / "shortlist")
    assert bed.key not in [c.key for c in after.slots["tense_dramatic"]]


@pytest.mark.parametrize(
    ("tags", "problem"),
    [
        (AudioTags(mood=["jazzy"]), "jazzy"),
        (AudioTags(mood=["tense_dramatic"], flavour=["klezmer"]), "klezmer"),
        (AudioTags(), "at least one mood"),
        (AudioTags(mood=["tense_dramatic"], intent=["tick"]), "intent"),
    ],
)
def test_a_yes_with_tags_off_the_closed_lists_is_refused(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound, tags: AudioTags, problem: str,
) -> None:  # fmt: skip
    shortlist = _build(Tape(audio), slots, library, tmp_path, voice, nums, ["tense_dramatic"])
    with pytest.raises(sl.ShortlistError, match=problem):
        sl.approve(shortlist.slots["tense_dramatic"][0].key, tags=tags,
                   out_dir=tmp_path / "shortlist", library_root=library)  # fmt: skip
    assert load_catalogue(library / "catalog.yaml").entries == ()


def test_the_startup_check_refuses_a_catalogue_tag_off_the_closed_lists(tmp_path: Path) -> None:
    catalogue = tmp_path / "catalog.yaml"
    catalogue.write_text(
        "entries:\n"
        "  - {id: x, kind: sfx, file: sfx/x.wav, source: mixkit, licence: Mixkit Free License,\n"
        "     duration_s: 0.2, energy: 3, tags: {intent: [popup_tick]}}\n",
        encoding="utf-8",
    )
    with pytest.raises(SoundError, match="popup_tick"):
        sl.check_catalogue(catalogue)
    with pytest.raises(SoundError, match="popup_tick"):
        app_module.create_app(
            _settings(tmp_path), transcriber=FakeTranscriber(), planner=FakePlanner(),
            specs=SPECS, renderer=FakeRenderer(), gate=FakeGate(),
            detector=FakeFaceDetector(), start_worker=False, audio_catalogue=catalogue,
        )  # fmt: skip


def test_a_no_is_never_shortlisted_again(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    shortlist = _build(Tape(audio), slots, library, tmp_path, voice, nums, ["tense_dramatic"])
    refused = shortlist.slots["tense_dramatic"][0]
    sl.refuse(refused.key, out_dir=tmp_path / "shortlist", library_root=library)
    remembered = yaml.safe_load((library / sl.REFUSED_NAME).read_text(encoding="utf-8"))
    assert remembered["refused"] == [refused.key]
    tape = Tape(audio)
    again = _build(tape, slots, library, tmp_path, voice, nums, ["tense_dramatic"])
    assert refused.key not in [c.key for c in again.slots["tense_dramatic"]]
    assert not any("tense-cinematic" in u for u in tape.fetched()), "not even downloaded"


def test_an_approved_candidate_is_not_shortlisted_again(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    shortlist = _build(Tape(audio), slots, library, tmp_path, voice, nums, ["tense_dramatic"])
    taken = shortlist.slots["tense_dramatic"][0]
    sl.approve(taken.key, tags=AudioTags(mood=["tense_dramatic"]),
               out_dir=tmp_path / "shortlist", library_root=library)  # fmt: skip
    again = _build(Tape(audio), slots, library, tmp_path, voice, nums, ["tense_dramatic"])
    assert taken.key not in [c.key for c in again.slots["tense_dramatic"]]


def test_fetch_approved_downloads_a_missing_api_file_again_by_its_id(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> None:  # fmt: skip
    shortlist = _build(Tape(audio), slots, library, tmp_path, voice, nums, ["tense_dramatic"])
    entry = sl.approve(shortlist.slots["tense_dramatic"][0].key,
                       tags=AudioTags(mood=["tense_dramatic"]), out_dir=tmp_path / "shortlist",
                       library_root=library)  # fmt: skip
    (library / entry.file).unlink()  # a fresh machine: the catalogue, not the media
    lines: list[str] = []
    assert sl.fetch_approved(library / "catalog.yaml", _sources(Tape(audio)), lines.append) == 0
    assert (library / entry.file).read_bytes() == audio["mid"].read_bytes()
    assert lines == [f"{entry.id}: fetched into {entry.file}"]


# --- probe --------------------------------------------------------------------------------


def test_probe_prints_one_line_per_source_and_writes_nothing(
    tmp_path: Path, audio: dict[str, Path]
) -> None:
    tape = Tape(audio)
    lines = sl.probe(_sources(tape))
    assert len(lines) == 2
    openverse, fs = lines
    assert openverse.startswith("openverse: status 200, 3 results")
    assert "Tense Cinematic Strings" in openverse and "by 4.0" in openverse
    assert "95.0 s" in openverse
    assert fs.startswith("freesound: status 200, 3 results")
    assert "Choir vocal ambient" in fs and "creativecommons.org/licenses/by/4.0" in fs
    assert "80.0 s" in fs
    assert tape.fetched() == [], "probe downloads nothing"
    assert list(tmp_path.iterdir()) == []


def test_probe_reports_a_missing_key_without_calling_that_source(
    audio: dict[str, Path],
) -> None:
    tape = Tape(audio)
    lines = sl.probe(sl.sources_for(freesound_key=None, client=tape.client()))
    assert lines[0].startswith("openverse: status 200")
    assert lines[1] == "freesound: FREESOUND_API_KEY is not set in .env; skipped"
    assert tape.searches(freesound.API_URL) == []


# --- the listening page -------------------------------------------------------------------


@pytest.fixture
def page_app(
    tmp_path: Path, audio: dict[str, Path], slots: sl.Slots, library: Path, voice: Path,
    nums: styles.Sound,
) -> FastAPI:  # fmt: skip
    _build(Tape(audio), slots, library, tmp_path, voice, nums, ["tense_dramatic", "tick"])
    return app_module.create_app(
        _settings(tmp_path), transcriber=FakeTranscriber(), planner=FakePlanner(),
        specs=SPECS, renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
        start_worker=False, shortlist_dir=tmp_path / "shortlist", audio_library=library,
    )  # fmt: skip


@pytest.fixture
def page_client(page_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(page_app) as client:
        yield client


def test_the_listening_page_sits_behind_the_passcode(page_client: TestClient) -> None:
    page = page_client.get("/audio/shortlist")
    assert page.status_code == 401 and 'name="passcode"' in page.text


def test_the_listening_page_shows_each_slot_its_players_and_licence_lines(
    page_client: TestClient,
) -> None:
    assert login(page_client, PASSCODE).status_code == 303
    page = page_client.get("/audio/shortlist")
    assert page.status_code == 200
    text = page.text
    assert "tense_dramatic" in text and "tick" in text
    assert text.count("<audio") == 3 * 2 + 2, "088: each bed also plays under the voice"
    assert "CC BY 4.0" in text and "Anna Keller" in text
    assert 'name="mood"' in text and 'name="intent"' in text
    assert 'action="/audio/shortlist/yes"' in text and 'action="/audio/shortlist/no"' in text
    src = text.split('<audio controls preload="none" src="')[1].split('"')[0]
    served = page_client.get(src)
    assert served.status_code == 200 and served.content[:4] == b"RIFF"
    assert page_client.get("/audio/shortlist/files/..%2F..%2Fcatalog.yaml").status_code == 404


def test_the_page_plays_each_bed_under_the_voice_and_notes_a_quiet_one(
    page_client: TestClient, tmp_path: Path, nums: styles.Sound
) -> None:
    """088: a bed card has a second player, the served preview under the voice; the bed
    over 069's ceiling carries its note, margin and level."""
    assert login(page_client, PASSCODE).status_code == 303
    text = page_client.get("/audio/shortlist").text
    shortlist = sl.load_shortlist(tmp_path / "shortlist")
    for candidate in shortlist.slots["tense_dramatic"]:
        assert candidate.preview is not None
        src = "/audio/shortlist/files/" + candidate.preview
        assert f'src="{src}"' in text, candidate.name
        served = page_client.get(src)
        assert served.status_code == 200 and served.content[:4] == b"RIFF"
    assert "under the voice" in text
    assert "may be hard to hear on a phone speaker" in text
    assert f"{nums.bed_db_under_voice:g} dB under the voice" in text


def test_a_yes_on_the_page_approves_and_a_no_refuses(
    page_client: TestClient, library: Path, tmp_path: Path
) -> None:
    assert login(page_client, PASSCODE).status_code == 303
    shortlist = sl.load_shortlist(tmp_path / "shortlist")
    bed, second = shortlist.slots["tense_dramatic"][:2]
    yes = page_client.post(
        "/audio/shortlist/yes", data={"key": bed.key, "mood": "tense_dramatic", "flavour": ""},
        follow_redirects=False,
    )
    assert yes.status_code == 303
    assert [e.id for e in load_catalogue(library / "catalog.yaml").entries] == [
        "openverse_0b5c1d2e-0001-4a6b-9c3d-000000000001"
    ]
    no = page_client.post("/audio/shortlist/no", data={"key": second.key}, follow_redirects=False)
    assert no.status_code == 303
    remembered = yaml.safe_load((library / sl.REFUSED_NAME).read_text(encoding="utf-8"))
    assert remembered["refused"] == [second.key]
    bad = page_client.post("/audio/shortlist/yes", data={"key": "nope:1", "mood": "calm_ambient"})
    assert bad.status_code == 422


def test_moods_on_the_page_come_from_the_closed_list() -> None:
    moods = vocab.load_moods()
    assert set(sl.page_moods(moods)) == set(moods.active_moods())
