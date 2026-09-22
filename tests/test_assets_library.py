"""The free-library image sources: Commons, Openverse, Pexels and Pixabay (5.1, 5.4,
13.1; ticket 018).

Each adapter is driven on a recorded response through an `httpx.MockTransport`, so
the request it builds (endpoint, query, paging, the key it carries) and the mapping of
its JSON into `Candidate` (image URL, page URL, thumbnail, reported size, licence text
and author) are pinned without any network. What the adapters share - the capped GET,
the judge's thumbnail and the 5.2-checked download - is `assets.http` and is tested
once here rather than four times.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image
from pydantic import SecretStr

from shortsmith.assets import base, commons, openverse, pexels, pixabay
from shortsmith.assets.base import ImageSource
from shortsmith.contracts import Candidate

FIXTURES = Path(__file__).parent / "fixtures"
QUERY = "India Gate Delhi"
KEY = SecretStr("test-key-not-a-real-one")


def _png(size: tuple[int, int] = (40, 30)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class Recorded:
    """A transport answering one recorded body, recording every request it saw."""

    def __init__(self, body: object | None = None, *, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.body is None:
            return httpx.Response(self.status)
        return httpx.Response(self.status, json=self.body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    @property
    def url(self) -> httpx.URL:
        return self.requests[0].url


def _recorded(name: str) -> object:
    return json.loads((FIXTURES / name / "search.json").read_text(encoding="utf-8"))


# --- Wikimedia Commons ------------------------------------------------------------------


def test_commons_asks_the_api_for_bitmap_files_in_the_file_namespace() -> None:
    tape = Recorded(_recorded("commons"))
    commons.CommonsImageSource(client=tape.client()).search(QUERY, 6)
    params = tape.url.params
    assert tape.url.host == "commons.wikimedia.org"
    assert (params["action"], params["generator"]) == ("query", "search")
    assert QUERY in params["gsrsearch"]
    assert (params["gsrnamespace"], params["gsrlimit"]) == ("6", "6")
    assert "extmetadata" in params["iiprop"]


def test_commons_maps_licence_author_and_both_urls_in_search_rank_order() -> None:
    """5.4: the licence text and author the API returns are recorded, not filtered."""
    tape = Recorded(_recorded("commons"))
    found = commons.CommonsImageSource(client=tape.client()).search(QUERY, 6)
    assert [c.width for c in found] == [4000, 1600, 3600]  # `index`, not dict order
    first = found[0]
    assert first.url == (
        "https://upload.wikimedia.org/wikipedia/commons/a/a1/India_Gate_at_dusk.jpg"
    )
    assert first.page_url == "https://commons.wikimedia.org/wiki/File:India_Gate_at_dusk.jpg"
    assert first.thumb_url.endswith("320px-India_Gate_at_dusk.jpg")
    assert (first.licence, first.author) == ("CC BY-SA 4.0", "Ankit Sharma")
    assert (found[1].licence, found[1].author) == ("Public domain", None)


def test_commons_drops_a_hit_with_no_image_url() -> None:
    """The sound file and the page with no `imageinfo` are not candidates."""
    tape = Recorded(_recorded("commons"))
    found = commons.CommonsImageSource(client=tape.client()).search(QUERY, 6)
    assert len(found) == 3
    assert all(c.url for c in found)


# --- Openverse --------------------------------------------------------------------------


def test_openverse_asks_its_image_endpoint_for_the_page_size() -> None:
    tape = Recorded(_recorded("openverse"))
    openverse.OpenverseImageSource(client=tape.client()).search(QUERY, 4)
    assert tape.url.host == "api.openverse.org"
    assert tape.url.path == "/v1/images/"
    assert (tape.url.params["q"], tape.url.params["page_size"]) == (QUERY, "4")


def test_openverse_builds_the_licence_text_from_code_and_version() -> None:
    tape = Recorded(_recorded("openverse"))
    found = openverse.OpenverseImageSource(client=tape.client()).search(QUERY, 6)
    assert [c.licence for c in found] == ["CC BY-SA 4.0", "CC0 1.0", "Public Domain Mark"]
    assert [c.author for c in found] == ["Meera Iyer", None, "Rawpixel Ltd."]
    assert found[0].page_url == "https://www.flickr.com/photos/traveller/51234567"
    assert found[0].thumb_url.endswith("/thumb/")


def test_openverse_drops_a_result_with_no_full_image_url() -> None:
    tape = Recorded(_recorded("openverse"))
    found = openverse.OpenverseImageSource(client=tape.client()).search(QUERY, 6)
    assert [c.width for c in found] == [3000, 2400, 1800]


# --- Pexels -----------------------------------------------------------------------------


def test_pexels_carries_its_key_in_the_authorization_header() -> None:
    tape = Recorded(_recorded("pexels"))
    pexels.PexelsImageSource(api_key=KEY, client=tape.client()).search(QUERY, 6)
    request = tape.requests[0]
    assert request.url.host == "api.pexels.com"
    assert request.headers["authorization"] == KEY.get_secret_value()
    assert (request.url.params["query"], request.url.params["per_page"]) == (QUERY, "6")


def test_pexels_takes_the_original_file_and_records_the_pexels_licence() -> None:
    tape = Recorded(_recorded("pexels"))
    found = pexels.PexelsImageSource(api_key=KEY, client=tape.client()).search(QUERY, 6)
    assert [c.width for c in found] == [4000, 5000]  # the hit with no `src` is dropped
    first = found[0]
    assert first.url == "https://images.pexels.com/photos/3182812/pexels-photo-3182812.jpeg"
    assert first.page_url == "https://www.pexels.com/photo/india-gate-at-dusk-3182812/"
    assert first.thumb_url.endswith("?h=350")
    assert (first.licence, first.author) == (pexels.LICENCE, "Aditi Rao")


def test_a_key_is_never_printed_by_the_adapter() -> None:
    source = pexels.PexelsImageSource(api_key=KEY, client=Recorded().client())
    assert KEY.get_secret_value() not in repr(source)


# --- Pixabay ----------------------------------------------------------------------------


def test_pixabay_carries_its_key_as_a_query_parameter() -> None:
    tape = Recorded(_recorded("pixabay"))
    pixabay.PixabayImageSource(api_key=KEY, client=tape.client()).search(QUERY, 6)
    params = tape.url.params
    assert tape.url.host == "pixabay.com"
    assert params["key"] == KEY.get_secret_value()
    assert (params["q"], params["image_type"]) == (QUERY, "photo")
    assert int(params["per_page"]) >= pixabay.MIN_PER_PAGE  # the API refuses fewer than 3


def test_pixabay_reports_the_size_of_the_file_it_will_actually_fetch() -> None:
    """`largeImageURL` is capped on its long side, so the reported original size would
    be a misreport to the 5.2 hard rejects; the adapter scales it to what it fetches."""
    tape = Recorded(_recorded("pixabay"))
    found = pixabay.PixabayImageSource(api_key=KEY, client=tape.client()).search(QUERY, 6)
    assert [(c.width, c.height) for c in found] == [(1280, 853), (853, 1280)]
    first = found[0]
    assert first.url.endswith("india-gate_1280.jpg")
    assert first.page_url == "https://pixabay.com/photos/india-gate-delhi-monument-2179532/"
    assert (first.licence, first.author) == (pixabay.LICENCE, "Ravi K")


def test_pixabay_stops_at_n_candidates() -> None:
    tape = Recorded(_recorded("pixabay"))
    found = pixabay.PixabayImageSource(api_key=KEY, client=tape.client()).search(QUERY, 1)
    assert len(found) == 1


# --- what every adapter shares (assets.http) --------------------------------------------


def _sources() -> list[ImageSource]:
    return [
        commons.CommonsImageSource(client=Recorded(None, status=503).client()),
        openverse.OpenverseImageSource(client=Recorded(None, status=503).client()),
        pexels.PexelsImageSource(api_key=KEY, client=Recorded(None, status=503).client()),
        pixabay.PixabayImageSource(api_key=KEY, client=Recorded(None, status=503).client()),
    ]


def test_every_adapter_declares_its_origin() -> None:
    assert [s.origin for s in _sources()] == ["commons", "openverse", "pexels", "pixabay"]


@pytest.mark.parametrize("index", range(4))
def test_a_source_that_answers_an_error_finds_nothing_and_never_raises(index: int) -> None:
    """5.2: a source that fails is a source with no hits; the ladder moves on."""
    assert _sources()[index].search(QUERY, 6) == []


@pytest.mark.parametrize("body", [b"not json at all", b'{"unexpected": true}'])
def test_a_reply_the_adapter_cannot_read_finds_nothing(body: bytes) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    client = httpx.Client(transport=httpx.MockTransport(answer))
    source = openverse.OpenverseImageSource(client=client)
    assert source.search(QUERY, 6) == []


def test_the_thumbnail_the_judge_sees_is_the_apis_own_preview() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=_png()))
    )
    candidate = Candidate(
        url="https://upload.wikimedia.org/full.jpg",
        thumb_url="https://upload.wikimedia.org/320px-thumb.jpg",
        width=4000,
        height=2667,
    )
    assert commons.CommonsImageSource(client=client).thumbnail(candidate) == _png()


def test_fetch_applies_the_body_rejects_before_writing(tmp_path: Path) -> None:
    """5.2: a body that is not an image is a `SourceError`, so the step drops the
    candidate and takes the next; nothing is written."""
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>nope"))
    )
    candidate = Candidate(url="https://images.pexels.com/x.jpg", width=4000, height=6000)
    with pytest.raises(base.SourceError, match="not an image"):
        pexels.PexelsImageSource(api_key=KEY, client=client).fetch(candidate, tmp_path / "image")
    assert not list(tmp_path.iterdir())


def test_fetch_writes_the_body_under_the_suffix_its_bytes_say(tmp_path: Path) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=_png()))
    )
    candidate = Candidate(url="https://cdn.pixabay.com/x.bin", width=1280, height=853)
    written = pixabay.PixabayImageSource(api_key=KEY, client=client).fetch(
        candidate, tmp_path / "image"
    )
    assert written == tmp_path / "image.png"
    assert written.read_bytes() == _png()


def test_scaled_reports_the_capped_size() -> None:
    assert pixabay.scaled(4000, 2667, 1280) == (1280, 853)
    assert pixabay.scaled(900, 600, 1280) == (900, 600)  # never upscaled
    assert pixabay.scaled(0, 0, 1280) == (0, 0)


def test_commons_artist_html_is_reduced_to_a_name() -> None:
    assert commons.artist('<a href="/wiki/User:X" title="X">Ankit Sharma</a>') == "Ankit Sharma"
    assert commons.artist("  Plain Name  ") == "Plain Name"
    assert commons.artist("") is None


def test_openverse_licence_text() -> None:
    assert openverse.licence_text("by-sa", "4.0") == "CC BY-SA 4.0"
    assert openverse.licence_text("cc0", "1.0") == "CC0 1.0"
    assert openverse.licence_text("pdm", None) == "Public Domain Mark"
    assert openverse.licence_text("", "") == "unknown"
