"""The Freesound audio search (decisions 7.1, 7.2, 5.4, 12.1, 13.1; ticket 024).

The adapter is driven on a recorded response through an `httpx.MockTransport`, so the
request it builds (endpoint, query, filter, the token header), the mapping of its JSON
into `AudioCandidate`, and the fetch-measure-check-append path are pinned with no
network. The audio it "downloads" is the synthesised catalogue's own files and the 023
sweep offenders, so the measure and the detector run on real samples.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from shortsmith import config, sound
from shortsmith.contracts import AudioCandidate, BalanceReport, BedQuery
from shortsmith.fixture import make_catalogue
from shortsmith.sound import freesound
from tests.conftest import Sounds

FIXTURES = Path(__file__).parent / "fixtures" / "freesound"
KEY = SecretStr("test-token-not-a-real-one")
THRESHOLD = 0.5


def _recorded(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Tape:
    """A transport that answers the search endpoint with the recorded body and every
    preview URL with the bytes of one local file, recording every request it saw."""

    def __init__(
        self,
        body: object | None = None,
        *,
        status: int = 200,
        audio: Path | None = None,
        audio_by_url: dict[str, Path] | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.audio = audio
        self.audio_by_url = audio_by_url or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url.startswith(freesound.API_URL):
            if self.body is None:
                return httpx.Response(self.status)
            return httpx.Response(self.status, json=self.body)
        served = self.audio_by_url.get(url.split("?")[0], self.audio)
        if served is None:
            return httpx.Response(404)
        return httpx.Response(200, content=served.read_bytes())

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    @property
    def url(self) -> httpx.URL:
        return self.requests[0].url

    def fetches(self) -> list[str]:
        return [str(r.url) for r in self.requests if not str(r.url).startswith(freesound.API_URL)]


def _adapter(tape: Tape) -> freesound.FreesoundAudioSearch:
    return freesound.FreesoundAudioSearch(api_key=KEY, client=tape.client())


@pytest.fixture
def own_library(tmp_path: Path) -> sound.Library:
    """A private synthesised catalogue: the adapter writes into the library it is given,
    so no test may hand it the session-wide one."""
    return sound.load_catalogue(make_catalogue(tmp_path / "audio"))


def _bed_file(library: sound.Library) -> Path:
    entry = library.entry("bed_tech_curious")
    assert entry is not None
    return library.file(entry)


# --- the request ------------------------------------------------------------------------


def test_search_asks_the_text_endpoint_with_the_tags_and_the_token_header() -> None:
    tape = Tape(_recorded("search.json"))
    _adapter(tape).search(["tech", "curious"], "bed")
    request = tape.requests[0]
    recorded = json.loads((FIXTURES / "request.json").read_text(encoding="utf-8"))
    assert str(request.url).split("?")[0] == recorded["url"]
    assert request.method == recorded["method"]
    params = {str(k): str(v) for k, v in recorded["params"].items()}
    for name, value in params.items():
        assert request.url.params[name] == value, name
    assert request.headers["authorization"] == f"Token {KEY.get_secret_value()}"
    assert KEY.get_secret_value() not in str(request.url), "the key never travels in the URL"


def test_search_for_a_cue_filters_on_cue_length() -> None:
    """7.3 R3: a cue is a hit, not a bed, so an SFX search asks for files under 5 s."""
    tape = Tape(_recorded("search.json"))
    _adapter(tape).search(["reveal_drop"], "sfx")
    recorded = json.loads((FIXTURES / "request.json").read_text(encoding="utf-8"))
    assert tape.url.params["filter"] == recorded["sfx_filter"]
    assert tape.url.params["query"] == "reveal_drop"


# --- the parsing (5.4: recorded, never filtered) ----------------------------------------


def test_search_maps_licence_author_and_every_url_and_drops_a_hit_with_no_preview() -> None:
    found = _adapter(Tape(_recorded("search.json"))).search(["tech", "curious"], "bed")
    assert [c.id for c in found] == ["512345", "377001"], "the hit with no preview is dropped"
    first = found[0]
    assert first.kind == "bed"
    assert first.name == "Curious Tech Loop"
    assert first.tags == ["tech", "curious", "loop", "electronic", "synth"]
    assert first.licence == "CC BY 4.0"
    assert first.licence_url == "http://creativecommons.org/licenses/by/4.0/"
    assert first.author == "synthsmith"
    assert first.page_url == "https://freesound.org/people/synthsmith/sounds/512345/"
    assert first.preview_url.endswith("512345_7654321-hq.mp3"), "the HQ mp3 preview first"
    assert first.download_url == "https://freesound.org/apiv2/sounds/512345/download/"
    assert first.duration_s == pytest.approx(64.2)
    second = found[1]
    assert second.licence == "CC BY-NC 3.0"
    assert second.author is None, "an empty username is no author"
    assert second.preview_url.endswith("-hq.ogg"), "without an mp3 the HQ ogg is taken"


@pytest.mark.parametrize(
    ("url", "text"),
    [
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0 1.0"),
        ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0 1.0"),
        ("http://creativecommons.org/licenses/by/4.0/", "CC BY 4.0"),
        ("http://creativecommons.org/licenses/by/3.0/", "CC BY 3.0"),
        ("http://creativecommons.org/licenses/by-nc/4.0/", "CC BY-NC 4.0"),
        ("http://creativecommons.org/licenses/sampling+/1.0/", "CC Sampling+ 1.0"),
        ("https://example.test/some-licence", "https://example.test/some-licence"),
        ("", "unknown"),
    ],
)
def test_licence_text_names_the_creative_commons_licence(url: str, text: str) -> None:
    assert freesound.licence_text(url) == text


def test_a_search_that_fails_finds_nothing_and_never_raises() -> None:
    """A source that fails is a source with no hits: the mix goes on without a bed."""
    assert _adapter(Tape(None, status=503)).search(["tech"], "bed") == []
    assert _adapter(Tape({"unexpected": True})).search(["tech"], "bed") == []


def test_the_key_is_never_printed_by_the_adapter() -> None:
    adapter = _adapter(Tape(None, status=503))
    assert KEY.get_secret_value() not in repr(adapter)


# --- fetch --------------------------------------------------------------------------------


def _candidate(**overrides: object) -> AudioCandidate:
    base: dict[str, object] = {
        "id": "512345",
        "name": "Curious Tech Loop",
        "kind": "bed",
        "tags": ["tech", "curious", "loop"],
        "licence": "CC BY 4.0",
        "licence_url": "http://creativecommons.org/licenses/by/4.0/",
        "author": "synthsmith",
        "page_url": "https://freesound.org/people/synthsmith/sounds/512345/",
        "preview_url": "https://cdn.freesound.org/previews/512/512345_7654321-hq.mp3",
        "download_url": "https://freesound.org/apiv2/sounds/512345/download/",
        "duration_s": 64.2,
    }
    return AudioCandidate.model_validate({**base, **overrides})


def test_fetch_writes_the_preview_under_fetched_named_by_the_source_id(
    tmp_path: Path, own_library: sound.Library
) -> None:
    """The original needs OAuth2, so the HQ preview is what is fetched; it lands under
    `<library>/fetched/` (git-ignored like every audio file) under the source id."""
    tape = Tape(audio=_bed_file(own_library))
    written = _adapter(tape).fetch(_candidate(), into=tmp_path)
    assert written == tmp_path / freesound.FETCHED_DIR / "freesound_512345.mp3"
    assert written.read_bytes() == _bed_file(own_library).read_bytes()
    assert tape.fetches() == [_candidate().preview_url]


def test_fetch_refuses_an_empty_or_failed_download(tmp_path: Path) -> None:
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    with pytest.raises(sound.SoundError, match="empty"):
        _adapter(Tape(audio=empty)).fetch(_candidate(), into=tmp_path)
    with pytest.raises(sound.SoundError, match="could not be downloaded"):
        _adapter(Tape()).fetch(_candidate(), into=tmp_path)
    assert not (tmp_path / freesound.FETCHED_DIR).exists()


# --- adopt: measure, check, score, append (7.2) -------------------------------------------


def test_a_fetched_bed_is_measured_scored_and_appended_to_the_catalogue(
    own_library: sound.Library,
) -> None:
    tape = Tape(_recorded("search.json"), audio=_bed_file(own_library))
    query = BedQuery(theme="cooking", mood="nostalgic", energy=2)
    found = _adapter(tape).beds(query, own_library)
    assert len(found) == 1
    entry = found[0]
    assert entry.id == "freesound_512345" and entry.kind == "bed"
    assert entry.file == "fetched/freesound_512345.mp3"
    assert entry.source == freesound.SOURCE
    assert entry.source_url == "https://freesound.org/people/synthsmith/sounds/512345/"
    assert (entry.licence, entry.author) == ("CC BY 4.0", "synthsmith")
    assert entry.tags.theme == ["cooking"] and entry.tags.mood == ["nostalgic"]
    assert entry.loop_ok is True, "Freesound tagged it a loop"
    # measured by the 023 script, not copied from the reply
    bed_file = _bed_file(own_library)
    assert entry.duration_s == pytest.approx(sound.ffmpeg.duration_s(bed_file), abs=0.05)
    assert 1 <= entry.energy <= 5
    assert own_library.file(entry).is_file()
    # scored like a local entry: both tags hit, so it clears the threshold
    assert sound.bed_score(entry, query) >= THRESHOLD
    # appended to catalog.yaml, after the seeded entries, and the file still loads
    reloaded = sound.load_catalogue(own_library.catalogue)
    assert [e.id for e in reloaded.entries][-1] == "freesound_512345"
    assert len(reloaded.entries) == len(own_library.entries) + 1
    assert reloaded.entry("freesound_512345") == entry
    assert tape.fetches() == [_candidate().preview_url], "only the best result was fetched"


def test_a_bed_already_adopted_is_reused_without_a_download(
    own_library: sound.Library,
) -> None:
    tape = Tape(_recorded("search.json"), audio=_bed_file(own_library))
    adapter = _adapter(tape)
    query = BedQuery(theme="cooking", mood="nostalgic", energy=2)
    first = adapter.beds(query, own_library)
    again = adapter.beds(query, sound.load_catalogue(own_library.catalogue))
    assert first == again
    assert len(tape.fetches()) == 1
    assert len(sound.load_catalogue(own_library.catalogue).entries) == len(own_library.entries) + 1


def test_a_cue_that_trips_the_detector_is_rejected_and_never_reaches_the_catalogue(
    own_library: sound.Library, sounds: Sounds
) -> None:
    """7.3: a fetched SFX goes through R1-R4 like a seeded one; a hit rejects it, the
    file is removed and the catalogue is left as it was."""
    tape = Tape(audio=sounds("noise_500ms"))
    whoosh = _candidate(
        id="900001", kind="sfx", tags=["whoosh"], duration_s=1.0,
        preview_url="https://cdn.freesound.org/previews/900/900001-hq.mp3",
    )  # fmt: skip
    before = own_library.catalogue.read_text(encoding="utf-8")
    with pytest.raises(freesound.Rejected, match="R1"):
        _adapter(tape).adopt(whoosh, library=own_library, intent="reveal_drop")
    assert not (own_library.root / freesound.FETCHED_DIR / "freesound_900001.mp3").exists()
    assert own_library.catalogue.read_text(encoding="utf-8") == before


def test_a_clean_cue_is_adopted_with_its_intent_tag(
    own_library: sound.Library, sounds: Sounds
) -> None:
    tape = Tape(audio=sounds("clicks"))
    click = _candidate(
        id="900002", kind="sfx", tags=["click"], duration_s=2.0,
        preview_url="https://cdn.freesound.org/previews/900/900002-hq.mp3",
    )  # fmt: skip
    entry = _adapter(tape).adopt(click, library=own_library, intent="reveal_drop")
    assert entry.kind == "sfx" and entry.tags.intent == ["reveal_drop"]
    assert (entry.bpm, entry.key) == (None, None), "an SFX has no tempo or key"
    assert entry.loop_ok is False
    assert sound.match_sfx("reveal_drop", sound.load_catalogue(own_library.catalogue)) == entry


def test_when_the_best_result_is_rejected_the_next_is_taken(
    own_library: sound.Library, sounds: Sounds
) -> None:
    """The search's order is kept; a rejected file costs one download, not the bed."""
    body: dict[str, object] = json.loads((FIXTURES / "search.json").read_text(encoding="utf-8"))
    results: list[dict[str, object]] = body["results"]  # pyright: ignore[reportAssignmentType]
    for hit in results:
        hit["duration"] = 2.0
    unreadable = own_library.root / "not-audio.bin"
    unreadable.write_bytes(b"this is not audio at all, ffmpeg cannot decode it" * 10)
    tape = Tape(
        body,
        audio_by_url={
            "https://cdn.freesound.org/previews/512/512345_7654321-hq.mp3": unreadable,
            "https://cdn.freesound.org/previews/377/377001_1111111-hq.ogg": _bed_file(own_library),
        },
    )
    found = _adapter(tape).beds(BedQuery(theme="lab", mood="curious", energy=3), own_library)
    assert [e.id for e in found] == ["freesound_377001"]
    assert len(tape.fetches()) == 2
    assert not (own_library.root / freesound.FETCHED_DIR / "freesound_512345.mp3").exists()


def test_a_fetched_bed_gets_a_rights_row_with_its_source(
    own_library: sound.Library,
) -> None:
    """5.4: the row names the Freesound page, the licence text and the author, with the
    origin `library` - it is a library entry now - and the fetched file's hash."""
    tape = Tape(_recorded("search.json"), audio=_bed_file(own_library))
    entry = _adapter(tape).beds(BedQuery(theme="cooking", mood="nostalgic", energy=2),
                                own_library)[0]  # fmt: skip
    result = sound.MixResult(
        premix=own_library.root, music=None, sfx=None, bed=entry, cues=(), notes=(),
        balance=BalanceReport(voice_db=-20.0, bed_accept_db=(-12.0, -9.0),
                              speech_band_margin_min_db=20.0, duck_max_db=4.0),
    )  # fmt: skip
    rows = sound.rights_rows(result, own_library)
    assert len(rows) == 1
    row = rows[0]
    assert (row.id, row.kind, row.origin) == ("freesound_512345", "music", "library")
    assert row.source_url == "https://freesound.org/people/synthsmith/sounds/512345/"
    assert (row.licence, row.author) == ("CC BY 4.0", "synthsmith")
    assert row.file == "fetched/freesound_512345.mp3" and row.sha256


def test_choose_bed_takes_the_adopted_bed_below_the_threshold(
    own_library: sound.Library,
) -> None:
    """The whole 7.2 path: nothing local scores, the adapter searches with the same
    tags, and the fetched, measured bed is the one chosen."""
    tape = Tape(_recorded("search.json"), audio=_bed_file(own_library))
    query = BedQuery(theme="cooking", mood="nostalgic", energy=2)
    chosen, note = sound.choose_bed(
        own_library, query, first_stamp_s=1.0, threshold=THRESHOLD, search=_adapter(tape)
    )
    assert chosen is not None and chosen.id == "freesound_512345"
    assert "search" in note


def test_a_search_failure_leaves_the_mix_without_a_bed(own_library: sound.Library) -> None:
    chosen, note = sound.choose_bed(
        own_library, BedQuery(theme="cooking", mood="nostalgic", energy=2),
        first_stamp_s=1.0, threshold=THRESHOLD, search=_adapter(Tape(None, status=503)),
    )  # fmt: skip
    assert chosen is None and "found none" in note


# --- config -------------------------------------------------------------------------------


def _settings(**overrides: object) -> config.Settings:
    return config.Settings(_env_file=None, **overrides)  # pyright: ignore[reportCallIssue]


def test_from_settings_builds_the_adapter_only_with_a_key() -> None:
    assert freesound.from_settings(_settings()) is None
    built = freesound.from_settings(_settings(freesound_api_key="fs_x"))
    assert isinstance(built, freesound.FreesoundAudioSearch)


def test_an_empty_freesound_key_means_no_search(
    monkeypatch: pytest.MonkeyPatch, own_library: sound.Library
) -> None:
    """052 / 024: `FREESOUND_API_KEY=` in the operator's `.env` builds no adapter, so
    the director's note says no search is configured instead of calling with `Token `."""
    monkeypatch.setenv("FREESOUND_API_KEY", "")
    search = freesound.from_settings(config.load(env_file=None))
    assert search is None
    chosen, note = sound.choose_bed(
        own_library, BedQuery(theme="cooking", mood="nostalgic", energy=2),
        first_stamp_s=1.0, threshold=THRESHOLD, search=search,
    )  # fmt: skip
    assert chosen is None and "no audio search is configured" in note


def test_the_freesound_key_is_a_secret() -> None:
    s = _settings(freesound_api_key="freesound_secret")
    assert s.freesound_api_key is not None
    assert s.freesound_api_key.get_secret_value() == "freesound_secret"
    assert "freesound_secret" not in repr(s) + s.model_dump_json()
