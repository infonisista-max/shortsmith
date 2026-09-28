"""The audio catalogue tells the truth (ticket 068).

Run04's catalogue held a car exhaust and an a-cappella chant as beds and a beeping score
counter as `tally_ding`: the Freesound adapter adopted the first hit and tagged it with
the query words. Now `assets/audio/kinds.yaml` says which words each kind needs and
which it may not carry, the adapter checks a hit's own name and tags against the kind
before any download, the entry keeps Freesound's name and tags, and `seed retag` reads
the fetched catalogue back from Freesound and removes what fails. Every answer here is
the recorded run04 one (`fixtures/freesound/run04_sounds.json`), served through an
`httpx.MockTransport`; no test reaches the network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from pydantic import SecretStr

from shortsmith import config, sound
from shortsmith.contracts import AudioCandidate, AudioEntry, AudioTags, BedQuery
from shortsmith.fixture import make_catalogue
from shortsmith.sound import freesound, kinds, seed

FIXTURES = Path(__file__).parent / "fixtures" / "freesound"
KEY = SecretStr("test-token-not-a-real-one")
RUN04: list[dict[str, Any]] = json.loads(
    (FIXTURES / "run04_sounds.json").read_text(encoding="utf-8")
)["sounds"]
BY_ID = {str(s["id"]): s for s in RUN04}
BAD_BEDS = ("557546", "738836")
BAD_SFX = ("253546", "249931")


def _hit(sound_id: str, *, duration: float = 60.0) -> dict[str, object]:
    """One search result in Freesound's shape, carrying run04's real name and tags."""
    known = BY_ID[sound_id]
    return {
        "id": int(sound_id), "name": known["name"], "tags": known["tags"],
        "license": "http://creativecommons.org/publicdomain/zero/1.0/",
        "username": "someone", "url": f"https://freesound.org/people/someone/sounds/{sound_id}/",
        "previews": {"preview-hq-mp3": f"https://cdn.freesound.org/previews/{sound_id}-hq.mp3"},
        "download": f"https://freesound.org/apiv2/sounds/{sound_id}/download/",
        "duration": duration, "type": "wav",
    }  # fmt: skip


class Tape:
    """Answers a search with `results`, `/sounds/<id>/` with run04's name and tags, and
    any preview with the bytes of `audio`; records every URL it saw."""

    def __init__(self, results: list[dict[str, object]] | None = None, *, audio: Path | None = None,
                 status: int = 200) -> None:  # fmt: skip
        self.results = results or []
        self.audio = audio
        self.status = status
        self.urls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.urls.append(url)
        if self.status != 200:
            return httpx.Response(self.status)
        if url.startswith(freesound.API_URL):
            return httpx.Response(200, json={"count": len(self.results), "results": self.results})
        if url.startswith(freesound.SOUND_URL.split("{id}")[0]):
            sound_id = request.url.path.rstrip("/").rsplit("/", 1)[-1]
            known = BY_ID.get(sound_id)
            if known is None:
                return httpx.Response(404)
            return httpx.Response(200, json=known)
        if self.audio is None:
            return httpx.Response(404)
        return httpx.Response(200, content=self.audio.read_bytes())

    def adapter(self) -> freesound.FreesoundAudioSearch:
        client = httpx.Client(transport=httpx.MockTransport(self))
        return freesound.FreesoundAudioSearch(api_key=KEY, client=client)

    def downloads(self) -> list[str]:
        return [u for u in self.urls if "/previews/" in u]


@pytest.fixture
def own_library(tmp_path: Path) -> sound.Library:
    return sound.load_catalogue(make_catalogue(tmp_path / "audio"))


def _bed_file(library: sound.Library) -> Path:
    entry = library.entry("bed_tech_curious")
    assert entry is not None
    return library.file(entry)


# --- kinds.yaml ------------------------------------------------------------------------------


def test_the_shipped_kinds_file_loads_with_a_bed_and_the_palette() -> None:
    loaded = kinds.load_kinds()
    assert sound.CATALOGUE_PATH.parent / "kinds.yaml" == kinds.KINDS_PATH
    assert "bed" in loaded.kinds
    assert {"tick", "whoosh", "drum", "bass", "thump", "ding"} <= set(loaded.sfx_kinds())
    bed = loaded.kind("bed")
    assert {"music", "loop"} <= set(bed.needs)
    assert {"vocal", "chant", "choir", "acappella", "car", "muffler"} <= set(bed.forbids)
    for name in loaded.sfx_kinds():
        forbids = set(loaded.for_sfx(name).forbids)
        assert {"ring", "phone", "bell", "chime", "alarm", "beep", "buzzer", "ringtone",
                "siren"} <= forbids, name  # fmt: skip


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "kinds.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_a_kind_with_no_required_words_is_refused_naming_it(tmp_path: Path) -> None:
    bad: dict[str, object] = {
        "sfx_forbids": ["ring"], "kinds": {"bed": {"needs": ["music"]}, "tick": {"needs": []}}
    }
    with pytest.raises(kinds.KindError, match=r"kinds.yaml: kind 'tick'.*no required words"):
        kinds.load_kinds(_write(tmp_path, bad))


def test_a_word_in_both_lists_is_refused_naming_it(tmp_path: Path) -> None:
    both = {"kinds": {"bed": {"needs": ["music", "voice"], "forbids": ["voice"]}}}
    with pytest.raises(kinds.KindError, match=r"kind 'bed'.*'voice'.*both"):
        kinds.load_kinds(_write(tmp_path, both))
    shared = {"sfx_forbids": ["ding"], "kinds": {"bed": {"needs": ["music"]},
                                                  "ding": {"needs": ["ding"]}}}  # fmt: skip
    with pytest.raises(kinds.KindError, match=r"kind 'ding'.*'ding'.*both"):
        kinds.load_kinds(_write(tmp_path, shared))


def test_a_kinds_file_without_a_bed_is_refused(tmp_path: Path) -> None:
    with pytest.raises(kinds.KindError, match="no 'bed' kind"):
        kinds.load_kinds(_write(tmp_path, {"kinds": {"tick": {"needs": ["tick"]}}}))


def test_a_broken_kinds_file_stops_the_app_naming_it(tmp_path: Path) -> None:
    from shortsmith import app as app_module
    from shortsmith.planner import FakePlanner
    from shortsmith.presenter import FakeFaceDetector
    from shortsmith.qa.gate import FakeGate
    from shortsmith.render import FakeRenderer
    from shortsmith.transcriber import FakeTranscriber
    from tests.test_app import _settings  # pyright: ignore[reportPrivateUsage]

    broken = _write(tmp_path, {"kinds": {"bed": {"needs": []}}})
    with pytest.raises(kinds.KindError, match="kind 'bed'"):
        app_module.create_app(
            _settings(tmp_path), transcriber=FakeTranscriber(), planner=FakePlanner(),
            renderer=FakeRenderer(), gate=FakeGate(), detector=FakeFaceDetector(),
            start_worker=False, audio_kinds=broken,
        )  # fmt: skip


# --- the check ---------------------------------------------------------------------------


def _refusal(kind: kinds.Kind, sound_id: str) -> str | None:
    known = BY_ID[sound_id]
    return kinds.refusal(kind, str(known["name"]), [str(t) for t in known["tags"]])


def test_run04s_car_exhaust_and_chant_are_refused_as_beds_naming_the_words() -> None:
    bed = kinds.load_kinds().kind("bed")
    car = _refusal(bed, "557546")
    assert car is not None and "mufflers" in car
    chant = _refusal(bed, "738836")
    assert chant is not None and "chant" in chant and "choir" in chant


def test_run04s_score_beeps_and_buzzer_are_refused_for_every_sfx_kind() -> None:
    loaded = kinds.load_kinds()
    asked = [*loaded.sfx_kinds(), "tally_ding", "changeover", "money"]
    for name in asked:
        kind = loaded.for_sfx(name)
        beeps = _refusal(kind, "253546")
        assert beeps is not None and "beep" in beeps, name
        buzzer = _refusal(kind, "249931")
        assert buzzer is not None and "buzzer" in buzzer, name


def test_a_planner_intent_outside_the_file_needs_its_own_words() -> None:
    """Until 070 closes the palette, an intent kinds.yaml does not name is checked
    against its own words and every SFX kind's forbidden list."""
    loaded = kinds.load_kinds()
    stamp = loaded.for_sfx("date_stamp")
    assert _refusal(stamp, "210316") is None
    assert _refusal(stamp, "63523") is not None
    assert set(loaded.sfx_forbids) <= set(stamp.forbids)


def test_a_plural_tag_matches_its_word() -> None:
    bed = kinds.Kind(name="bed", needs=("loop",), forbids=("muffler",))
    assert kinds.refusal(bed, "x", ["loops"]) is None
    refused = kinds.refusal(bed, "x", ["loops", "mufflers"])
    assert refused is not None and "mufflers" in refused


# --- adoption ------------------------------------------------------------------------------


def test_the_adapter_refuses_run04s_beds_before_any_download(
    own_library: sound.Library,
) -> None:
    tape = Tape([_hit("557546"), _hit("738836")], audio=_bed_file(own_library))
    query = BedQuery(theme="history documentary", mood="regal intriguing eastern oud", energy=3)
    outcome = tape.adapter().bed("history documentary regal", query, own_library)
    assert outcome.adopted is None
    assert tape.downloads() == [], "a refused hit is never downloaded"
    assert len(outcome.notes) == 2
    assert "buick regal gs_magnaflow.mp3" in outcome.notes[0] and "mufflers" in outcome.notes[0]
    assert "chant" in outcome.notes[1]
    assert not own_library.fetched_catalogue.exists()


def test_the_adapter_refuses_run04s_beeps_and_buzzer_for_a_cue(
    own_library: sound.Library,
) -> None:
    tape = Tape([_hit("253546", duration=1.46), _hit("249931", duration=0.6)])
    for intent in ("tally_ding", "changeover", "tick", "drum"):
        outcome = tape.adapter().sfx("score ding", intent, own_library)
        assert outcome.adopted is None, intent
        assert any("beep" in n for n in outcome.notes) and any("buzzer" in n for n in outcome.notes)
    assert tape.downloads() == []


def test_a_catalogued_entry_is_not_reused_when_its_own_name_fails_the_kind(
    own_library: sound.Library,
) -> None:
    """Run04's car exhaust already sits in the fetched catalogue; a search that returns it
    again must not reuse it as a bed."""
    freesound.append_entry(own_library.fetched_catalogue, AudioEntry(
        id="freesound_557546", kind="bed", file="fetched/freesound_557546.mp3",
        source="freesound", licence="CC0 1.0", duration_s=60.0, energy=3,
        tags=AudioTags(theme=["history"], mood=["regal"]),
    ))  # fmt: skip
    tape = Tape([_hit("557546")])
    outcome = tape.adapter().bed("regal", BedQuery(theme="history", mood="regal", energy=3),
                                 sound.load_catalogue(own_library.catalogue))  # fmt: skip
    assert outcome.adopted is None and "mufflers" in outcome.notes[0]


def _candidate(**overrides: object) -> AudioCandidate:
    base: dict[str, object] = {
        "id": "512345", "name": "Curious Tech Loop", "kind": "bed",
        "tags": ["Tech", "curious", "loop", "Electronic", "synth"], "licence": "CC BY 4.0",
        "author": "synthsmith", "page_url": "https://freesound.org/people/synthsmith/sounds/512345/",
        "preview_url": "https://cdn.freesound.org/previews/512/512345_7654321-hq.mp3",
    }  # fmt: skip
    return AudioCandidate.model_validate({**base, **overrides})


def test_an_adopted_bed_keeps_freesounds_name_and_tags_and_never_a_query_only_word(
    own_library: sound.Library,
) -> None:
    candidate = _candidate()
    tape = Tape([], audio=_bed_file(own_library))
    entry = tape.adapter().adopt(candidate, library=own_library, mood=["nostalgic", "curious"])
    assert entry.source_name == "Curious Tech Loop"
    assert entry.source_tags == ["Tech", "curious", "loop", "Electronic", "synth"]
    source = {t.lower() for t in candidate.tags}
    tagged = {*entry.tags.theme, *entry.tags.mood, *entry.tags.intent}
    assert tagged <= source, f"query-only words leaked: {tagged - source}"
    assert entry.tags.mood == ["curious"], "a query mood word Freesound also used"
    assert "tech" in entry.tags.theme
    row = sound.load_catalogue(own_library.catalogue).entry(entry.id)
    assert row is not None and row.source_name == entry.source_name
    assert row.source_tags == entry.source_tags
    written = own_library.fetched_catalogue.read_text(encoding="utf-8")
    assert "source_name: Curious Tech Loop" in written


def test_the_search_bed_path_tags_from_the_source_not_the_query(
    own_library: sound.Library,
) -> None:
    body = json.loads((FIXTURES / "search.json").read_text(encoding="utf-8"))
    tape = Tape(body["results"], audio=_bed_file(own_library))
    query = BedQuery(theme="cooking kitchen", mood="nostalgic curious", energy=2)
    outcome = tape.adapter().bed("cooking nostalgic", query, own_library)
    assert outcome.adopted is not None
    tags = outcome.adopted.tags
    assert "cooking" not in tags.theme and "nostalgic" not in tags.mood
    assert tags.mood == ["curious"]


# --- the fake search ---------------------------------------------------------------------


def test_the_fake_search_refuses_a_mislabelled_shelf_entry(own_library: sound.Library) -> None:
    car = AudioEntry(
        id="freesound_557546", kind="bed", file="fetched/freesound_557546.mp3",
        source="freesound", licence="CC0 1.0", duration_s=60.0, energy=3,
        source_name="buick regal gs_magnaflow.mp3", source_tags=["buick", "mufflers"],
        tags=AudioTags(theme=["history"], mood=["regal"]),
    )  # fmt: skip
    beeps = AudioEntry(
        id="freesound_253546", kind="sfx", file="fetched/freesound_253546.mp3",
        source="freesound", licence="CC0 1.0", duration_s=1.46, energy=5,
        source_name="SCORE COUNT.wav", source_tags=["beep", "ding", "score"],
        tags=AudioTags(intent=["tally_ding"]),
    )  # fmt: skip
    shelf = sound.Library(root=own_library.root, entries=(car, beeps))
    search = sound.FakeAudioSearch(shelf=shelf)
    bed = search.bed("regal", BedQuery(theme="history", mood="regal", energy=3), own_library)
    assert bed.adopted is None and any("mufflers" in n for n in bed.notes)
    cue = search.sfx("tally ding", "tally_ding", own_library)
    assert cue.adopted is None and any("beep" in n for n in cue.notes)


def test_the_fake_search_still_serves_a_hand_seeded_shelf(own_library: sound.Library) -> None:
    """An operator-seeded entry has no Freesound name; its hand-written tags stand."""
    search = sound.FakeAudioSearch(shelf=own_library)
    bed = search.bed("tech", BedQuery(theme="tech", mood="curious", energy=3), own_library)
    assert bed.adopted is not None


# --- seed retag ----------------------------------------------------------------------------

RUN04_FETCHED: list[tuple[str, str, list[str]]] = [
    ("557546", "bed", []), ("738836", "bed", []), ("669855", "sfx", ["drum"]),
    ("115525", "sfx", ["bass"]), ("339437", "sfx", ["thump"]), ("118338", "sfx", ["question_tick"]),
    ("210316", "sfx", ["date_stamp"]), ("249931", "sfx", ["changeover"]),
    ("253546", "sfx", ["tally_ding"]), ("63523", "sfx", ["money"]),
]  # fmt: skip
REMOVED = {"557546", "738836", "253546", "249931"}


def _run04_library(root: Path) -> Path:
    """A tracked catalogue and run04's fetched one, each file a few placeholder bytes."""
    root.mkdir(parents=True)
    tracked = root / sound.CATALOGUE_NAME
    tracked.write_text("# the operator's catalogue\nentries: []\n", encoding="utf-8")
    fetched = root / sound.FETCHED_DIR
    fetched.mkdir()
    entries: list[dict[str, object]] = []
    for sound_id, kind, intent in RUN04_FETCHED:
        name = f"freesound_{sound_id}.mp3"
        (fetched / name).write_bytes(b"placeholder")
        theme, mood = (["history", "oud"], ["regal"]) if kind == "bed" else ([], [])
        entries.append({
            "id": f"freesound_{sound_id}", "kind": kind, "file": f"fetched/{name}",
            "source": "freesound", "licence": "CC0 1.0", "duration_s": 1.0, "energy": 3,
            "tags": {"theme": theme, "mood": mood, "intent": intent},
        })  # fmt: skip
    (fetched / sound.CATALOGUE_NAME).write_text(
        yaml.safe_dump({"entries": entries}, sort_keys=False), encoding="utf-8"
    )
    return tracked


def test_retag_keeps_the_good_entries_and_removes_run04s_four_with_their_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tracked = _run04_library(tmp_path / "audio")
    tracked_before = tracked.read_bytes()
    tape = Tape()
    assert freesound.retag(tracked, tape.adapter()) == 0
    out = capsys.readouterr().out
    library = sound.load_catalogue(tracked)
    kept = {e.id.removeprefix("freesound_") for e in library.entries}
    assert kept == {s for s, _, _ in RUN04_FETCHED} - REMOVED
    for sound_id in REMOVED:
        assert not (tmp_path / "audio" / "fetched" / f"freesound_{sound_id}.mp3").exists()
        assert f"freesound_{sound_id}: removed" in out
    snare = library.entry("freesound_669855")
    assert snare is not None
    assert (snare.source_name, snare.source_tags) == ("Snare hit", ["snare", "drum", "hit"])
    assert snare.tags.intent == ["drum"]
    assert library.file(snare).is_file()
    assert "freesound_115525: kept" in out
    assert tracked.read_bytes() == tracked_before, "the tracked catalogue is never touched"
    asked = [u for u in tape.urls if "/sounds/" in u]
    assert len(asked) == len(RUN04_FETCHED)


def test_retag_without_a_key_says_so_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tracked = _run04_library(tmp_path / "audio")
    fetched = tracked.parent / sound.FETCHED_DIR / sound.CATALOGUE_NAME
    before = fetched.read_bytes()
    settings = config.Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert seed.retag_command(tracked, settings) == 1
    assert "FREESOUND_API_KEY" in capsys.readouterr().err
    assert fetched.read_bytes() == before


def test_retag_leaves_an_entry_it_cannot_read_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tracked = _run04_library(tmp_path / "audio")
    fetched = tracked.parent / sound.FETCHED_DIR / sound.CATALOGUE_NAME
    before = fetched.read_bytes()
    assert freesound.retag(tracked, Tape(status=503).adapter()) == 1
    assert "503" in capsys.readouterr().err
    assert fetched.read_bytes() == before, "nothing is written when any read fails"


def test_seed_takes_the_retag_command() -> None:
    with pytest.raises(SystemExit):
        seed.main(["nonsense"])
    assert "retag" in seed.COMMANDS
