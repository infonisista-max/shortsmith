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
        timeout: bool = False,
        audio: Path | None = None,
        audio_by_url: dict[str, Path] | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.timeout = timeout
        self.audio = audio
        self.audio_by_url = audio_by_url or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url.startswith(freesound.API_URL):
            if self.timeout:
                raise httpx.ReadTimeout("the tape timed out", request=request)
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
    _adapter(tape).search("tech curious", "bed")
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
    _adapter(tape).search("reveal drop", "sfx")
    recorded = json.loads((FIXTURES / "request.json").read_text(encoding="utf-8"))
    assert tape.url.params["filter"] == recorded["sfx_filter"]
    assert tape.url.params["query"] == "reveal drop"


def test_every_search_carries_the_cc0_or_cc_by_licence_filter() -> None:
    """054 (4): only CC0 and CC BY are asked for, beds and SFX alike."""
    for kind in ("bed", "sfx"):
        tape = Tape(_recorded("search.json"))
        _adapter(tape).search("tech", kind)  # pyright: ignore[reportArgumentType]
        assert freesound.LICENCE_FILTER in tape.url.params["filter"], kind
        assert tape.url.params["filter"] == f"{freesound.DURATION_FILTER[kind]} {freesound.LICENCE_FILTER}"  # pyright: ignore[reportArgumentType]  # noqa: E501
    assert freesound.LICENCE_FILTER == 'license:("Attribution" OR "Creative Commons 0")'


def test_search_reports_the_status_and_the_hit_count() -> None:
    """054 (1): the page says what came back so the job log can carry one line per
    search; a 403 or a timeout is a status, never a silent empty list."""
    page = _adapter(Tape(_recorded("search.json"))).search("tech curious", "bed")
    assert (page.status, page.hits) == ("200", 3), "Freesound's own count, not the page"
    assert len(page.candidates) == 2
    forbidden = _adapter(Tape(None, status=403)).search("tech", "bed")
    assert (forbidden.status, forbidden.hits, forbidden.candidates) == ("403", 0, ())
    timed_out = _adapter(Tape(None, timeout=True)).search("tech", "bed")
    assert (timed_out.status, timed_out.hits) == ("timeout", 0)
    garbage = _adapter(Tape({"unexpected": True})).search("tech", "bed")
    assert (garbage.status, garbage.hits) == ("200", 0)


# --- the parsing (5.4: recorded; 054: filtered to CC0 / CC BY) ---------------------------


def test_search_maps_licence_author_and_every_url_and_drops_a_hit_with_no_preview() -> None:
    found = _adapter(Tape(_recorded("search.json"))).search("tech curious", "bed").candidates
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
    assert _adapter(Tape(None, status=503)).search("tech", "bed").candidates == ()
    assert _adapter(Tape({"unexpected": True})).search("tech", "bed").candidates == ()


@pytest.mark.parametrize(
    ("text", "allowed"),
    [
        ("CC0 1.0", True), ("CC0", True), ("CC BY 4.0", True), ("CC BY 3.0", True),
        ("CC BY-NC 3.0", False), ("CC BY-SA 4.0", False), ("CC BY-ND 4.0", False),
        ("CC Sampling+ 1.0", False), ("unknown", False), ("https://example.test/x", False),
    ],
)  # fmt: skip
def test_only_cc0_and_cc_by_are_licences_the_adapter_adopts(text: str, allowed: bool) -> None:
    assert freesound.licence_allowed(text) is allowed


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


COOKING = BedQuery(theme="cooking", mood="nostalgic", energy=2)


def _bed(adapter: freesound.FreesoundAudioSearch, library: sound.Library) -> sound.SearchOutcome:
    return adapter.bed("cooking nostalgic", COOKING, library)


def test_a_fetched_bed_is_measured_scored_and_appended_to_the_catalogue(
    own_library: sound.Library,
) -> None:
    tape = Tape(_recorded("search.json"), audio=_bed_file(own_library))
    query = COOKING
    outcome = _bed(_adapter(tape), own_library)
    assert (outcome.source, outcome.kind) == ("freesound", "bed")
    assert outcome.query == "cooking nostalgic"
    assert (outcome.status, outcome.hits) == ("200", 3)
    assert "adopted freesound_512345" in outcome.line()
    entry = outcome.adopted
    assert entry is not None
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
    first = _bed(adapter, own_library).adopted
    again = _bed(adapter, sound.load_catalogue(own_library.catalogue)).adopted
    assert first is not None and first == again
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


def _results(**overrides: object) -> dict[str, object]:
    """The recorded body with every hit's fields updated by `overrides`."""
    body: dict[str, object] = json.loads((FIXTURES / "search.json").read_text(encoding="utf-8"))
    results: list[dict[str, object]] = body["results"]  # pyright: ignore[reportAssignmentType]
    for hit in results:
        hit.update(overrides)
    return body


CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
FIRST_PREVIEW = "https://cdn.freesound.org/previews/512/512345_7654321-hq.mp3"
THIRD_PREVIEW = "https://cdn.freesound.org/previews/377/377001_1111111-hq.ogg"


def test_when_the_best_result_is_rejected_the_next_is_taken(
    own_library: sound.Library, sounds: Sounds
) -> None:
    """The search's order is kept; a rejected file costs one download, not the bed, and
    the outcome's notes say what was skipped and why."""
    unreadable = own_library.root / "not-audio.bin"
    unreadable.write_bytes(b"this is not audio at all, ffmpeg cannot decode it" * 10)
    tape = Tape(
        _results(duration=2.0, license=CC0),
        audio_by_url={FIRST_PREVIEW: unreadable, THIRD_PREVIEW: _bed_file(own_library)},
    )
    outcome = _adapter(tape).bed("lab curious", BedQuery(theme="lab", mood="curious", energy=3),
                                 own_library)  # fmt: skip
    assert outcome.adopted is not None and outcome.adopted.id == "freesound_377001"
    assert len(tape.fetches()) == 2
    assert not (own_library.root / freesound.FETCHED_DIR / "freesound_512345.mp3").exists()
    assert len(outcome.notes) == 1 and "Curious Tech Loop" in outcome.notes[0]
    assert "not readable audio" in outcome.notes[0]


def test_a_result_outside_cc0_and_cc_by_is_never_adopted_even_when_returned(
    own_library: sound.Library,
) -> None:
    """054 (4): the licence is checked again on the result; a CC BY-NC hit the API hands
    back anyway is skipped with a note, and never downloaded."""
    # In the recording 512345 (CC BY) comes first and is adopted before the CC BY-NC hit
    # is reached; reversed, the BY-NC hit is the best result and must be skipped.
    body: dict[str, object] = json.loads((FIXTURES / "search.json").read_text(encoding="utf-8"))
    results: list[object] = body["results"]  # pyright: ignore[reportAssignmentType]
    body["results"] = list(reversed(results))
    tape = Tape(body, audio=_bed_file(own_library))
    outcome = _adapter(tape).bed("lab curious", BedQuery(theme="lab", mood="curious", energy=3),
                                 own_library)  # fmt: skip
    assert outcome.adopted is not None and outcome.adopted.id == "freesound_512345"
    assert tape.fetches() == [FIRST_PREVIEW], "the BY-NC preview was never downloaded"
    assert any("Lab Pulse" in n and "CC BY-NC 3.0" in n and "not CC0 or CC BY" in n
               for n in outcome.notes)  # fmt: skip
    only_nc = _results(license="http://creativecommons.org/licenses/by-nc/4.0/")
    tape = Tape(only_nc, audio=_bed_file(own_library))
    outcome = _adapter(tape).bed("lab curious", BedQuery(theme="lab", mood="curious", energy=3),
                                 own_library)  # fmt: skip
    assert outcome.adopted is None and tape.fetches() == []
    assert outcome.hits == 3 and len(outcome.notes) == 2, "one note per licence-skipped hit"


def test_a_rejected_candidate_is_remembered_and_not_downloaded_twice(
    own_library: sound.Library, sounds: Sounds
) -> None:
    """An SFX that tripped the detector once is skipped by id on the next search."""
    body = _results(duration=1.0, license=CC0)
    tape = Tape(body, audio=sounds("noise_500ms"))
    adapter = _adapter(tape)
    first = adapter.sfx("reveal drop", "reveal_drop", own_library)
    assert first.adopted is None
    downloads = len(tape.fetches())
    assert downloads == 2, "both previewed hits were fetched and rejected"
    again = adapter.sfx("reveal", "reveal_drop", own_library)
    assert again.adopted is None and len(tape.fetches()) == downloads
    assert all("rejected earlier" in n for n in again.notes) and len(again.notes) == 2


def test_a_fetched_bed_gets_a_rights_row_with_its_source(
    own_library: sound.Library,
) -> None:
    """5.4: the row names the Freesound page, the licence text and the author, with the
    origin `library` - it is a library entry now - and the fetched file's hash."""
    tape = Tape(_recorded("search.json"), audio=_bed_file(own_library))
    entry = _bed(_adapter(tape), own_library).adopted
    assert entry is not None
    result = sound.MixResult(
        premix=own_library.root, music=None, sfx=None, bed=entry, cues=(), notes=(),
        balance=BalanceReport(voice_db=-20.0, bed_accept_db=(-12.0, -9.0),
                              speech_band_margin_min_db=20.0, duck_max_db=4.0),
        library=sound.load_catalogue(own_library.catalogue),
    )  # fmt: skip
    rows = sound.rights_rows(result)
    assert len(rows) == 1
    row = rows[0]
    assert (row.id, row.kind, row.origin) == ("freesound_512345", "music", "library")
    assert row.source_url == "https://freesound.org/people/synthsmith/sounds/512345/"
    assert (row.licence, row.author) == ("CC BY 4.0", "synthsmith")
    assert row.file == "fetched/freesound_512345.mp3" and row.sha256


def test_an_adoption_never_changes_the_tracked_catalogue(
    own_library: sound.Library, sounds: Sounds
) -> None:
    """056 (6): a job never changes a tracked file. A bed and an SFX adopted at run time
    land in the git-ignored fetched catalogue beside their files; the tracked one is
    byte-identical; the next load reads both, so a second job finds them with no search."""
    tracked_before = own_library.catalogue.read_bytes()
    tape = Tape(_recorded("search.json"), audio=_bed_file(own_library))
    adapter = _adapter(tape)
    bed = _bed(adapter, own_library).adopted
    assert bed is not None and bed.id == "freesound_512345"
    click = _candidate(
        id="900002", kind="sfx", tags=["click"], duration_s=2.0,
        preview_url="https://cdn.freesound.org/previews/900/900002-hq.mp3",
    )  # fmt: skip
    sfx = _adapter(Tape(audio=sounds("clicks"))).adopt(click, library=own_library, intent="ding")
    assert own_library.catalogue.read_bytes() == tracked_before
    fetched = own_library.fetched_catalogue
    assert fetched == own_library.root / freesound.FETCHED_DIR / sound.CATALOGUE_NAME
    assert fetched.is_file()
    only_fetched = sound.parse_catalogue(fetched.read_text(encoding="utf-8"), name=fetched.name)
    assert [e.id for e in only_fetched.entries] == [bed.id, sfx.id]
    # The next job's library is the tracked catalogue followed by the fetched one.
    reloaded = sound.load_catalogue(own_library.catalogue)
    seeded = [e.id for e in own_library.entries]
    assert [e.id for e in reloaded.entries] == [*seeded, bed.id, sfx.id]
    assert reloaded.file(bed).is_file() and reloaded.file(sfx).is_file()
    searches = adapter.searches
    chosen, lines = sound.choose_bed(
        reloaded, COOKING, first_stamp_s=1.0, threshold=THRESHOLD, search=adapter,
        default_query="cinematic ambient documentary",
    )  # fmt: skip
    assert chosen is not None and chosen.id == bed.id and adapter.searches == searches
    assert lines[0].startswith(f"bed {bed.id} from the library")
    assert sound.match_sfx("ding", reloaded) == sfx


def test_the_fetched_catalogue_is_git_ignored() -> None:
    """The shipped library's fetched folder stays out of git (056 (6))."""
    import subprocess

    fetched = sound.load_catalogue().fetched_catalogue
    assert fetched == sound.CATALOGUE_PATH.parent / freesound.FETCHED_DIR / sound.CATALOGUE_NAME
    proc = subprocess.run(
        ["git", "check-ignore", "-q", str(fetched)], cwd=sound.REPO_ROOT, capture_output=True,
        check=False,
    )  # fmt: skip
    assert proc.returncode == 0, "assets/audio/fetched/catalog.yaml is not git-ignored"


def test_choose_bed_takes_the_adopted_bed_below_the_threshold(
    own_library: sound.Library,
) -> None:
    """The whole 7.2 path: nothing local scores, the adapter searches with the same
    tags, and the fetched, measured bed is the one chosen."""
    tape = Tape(_recorded("search.json"), audio=_bed_file(own_library))
    chosen, lines = sound.choose_bed(
        own_library, COOKING, first_stamp_s=1.0, threshold=THRESHOLD, search=_adapter(tape),
        default_query="cinematic ambient documentary",
    )  # fmt: skip
    assert chosen is not None and chosen.id == "freesound_512345"
    assert any("from the audio search" in line for line in lines)
    assert lines[0].startswith("audio search freesound bed 'cooking nostalgic': status 200, 3 hits")


def test_a_search_failure_is_logged_per_rung_and_leaves_the_mix_without_a_bed(
    own_library: sound.Library,
) -> None:
    """054 (1): a 403 is one line per rung, with the query, the status and 0 hits."""
    tape = Tape(None, status=403)
    chosen, lines = sound.choose_bed(
        own_library, COOKING, first_stamp_s=1.0, threshold=THRESHOLD, search=_adapter(tape),
        default_query="cinematic ambient documentary",
    )  # fmt: skip
    assert chosen is None
    rungs = sound.bed_queries(COOKING, "cinematic ambient documentary")
    searched = [line for line in lines if line.startswith("audio search freesound bed ")]
    assert len(searched) == len(rungs) == len(tape.requests)
    assert all("status 403, 0 hits" in line for line in searched)
    assert "every audio search came back empty" in lines[-1]


def test_an_empty_sfx_catalogue_is_filled_from_the_search_through_the_sweep_detector(
    tmp_path: Path, sounds: Sounds
) -> None:
    """054 (3): no SFX in the catalogue and a working search still yields the floor hits
    and the cues; a hit that trips R1 is rejected and the next candidate is taken."""
    from shortsmith import fixture, render, styles
    from shortsmith.contracts import Constraints, PlanRequest, PlanStyle, Transcript
    from shortsmith.planner import FakePlanner

    request = PlanRequest(
        brief="", style=PlanStyle(name="explainer", status="shipped", numbers={}, prose=""),
        style_note="", transcript=Transcript(duration_s=fixture.DURATION_S, segments=[], words=[]),
        references=[], constraints=Constraints(max_duration_s=60.0, target_duration_s=6.0),
        asset_policy="any",
    )  # fmt: skip
    plan = FakePlanner().plan_picture(request)
    story = FakePlanner().plan_sound(request, plan)
    nums = render.loaded_styles()[styles.DEFAULT].sound
    empty = sound.Library(root=tmp_path / "audio")  # no catalogue file at all
    body = _results(duration=1.0, license=CC0)
    served = {FIRST_PREVIEW: sounds("noise_500ms"), THIRD_PREVIEW: sounds("clicks")}
    tape = Tape(body, audio_by_url=served)
    placed = sound.place_cues(plan, story, empty, nums, runtime_s=60.0, search=_adapter(tape))
    assert placed.cues, "the floor hits and the cues were placed from the search"
    assert {c.entry_id for c in placed.cues} == {"freesound_377001"}, "the R1 hit was never taken"
    assert any("R1" in n and "Curious Tech Loop" in n for n in placed.notes)
    floor_ids = {c.beat_id for c in placed.cues if c.source == "floor"}
    assert floor_ids, "the floor hits are there"
    assert placed.library.entry("freesound_377001") is not None
    grown = sound.load_catalogue(placed.library.catalogue)
    assert [e.id for e in grown.sfx()] == ["freesound_377001"], "adopted once, tagged for reuse"
    assert grown.sfx()[0].licence == "CC0 1.0"
    assert len(tape.fetches()) == 2, "one rejected, one adopted; every later intent reused it"


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
    chosen, lines = sound.choose_bed(
        own_library, BedQuery(theme="cooking", mood="nostalgic", energy=2),
        first_stamp_s=1.0, threshold=THRESHOLD, search=search,
    )  # fmt: skip
    assert chosen is None and any("no audio search configured" in line for line in lines)


def test_the_freesound_key_is_a_secret() -> None:
    s = _settings(freesound_api_key="freesound_secret")
    assert s.freesound_api_key is not None
    assert s.freesound_api_key.get_secret_value() == "freesound_secret"
    assert "freesound_secret" not in repr(s) + s.model_dump_json()
