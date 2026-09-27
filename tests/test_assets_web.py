"""assets.web + assets.base: the first real image source and the code-only hard
rejects (5.1, 5.2, 13.1).

The adapter is driven on recorded pages through an `httpx.MockTransport`, so request
construction and response parsing are pinned without any network: the search request's
query and headers, the result JSON with its printed size, the page follow to
`og:image`, the thumbnail the judge sees, and a download that refuses an oversized or
non-image body. The hard rejects are pure functions, pinned at their boundaries."""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from shortsmith import render
from shortsmith.assets import base, web
from shortsmith.contracts import Candidate

WEB = Path(__file__).parent / "fixtures" / "web"
QUERY = "India Gate Delhi archival photo"
PAGE_URL = "https://www.archive.example.org/gallery/india-gate"


def _png(size: tuple[int, int] = (40, 30)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class Fake:
    """A transport answering the recorded pages, recording every request it saw."""

    def __init__(self, **bodies: httpx.Response) -> None:
        self.bodies = bodies
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for marker, response in self.bodies.items():
            if marker in str(request.url):
                return response
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def _html(name: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=(WEB / f"{name}.html").read_text(encoding="utf-8"),
        headers={"content-type": "text/html; charset=utf-8"},
    )


def _source(fake: Fake) -> web.WebImageSource:
    return web.WebImageSource(client=fake.client())


# --- the hard rejects (5.2) ------------------------------------------------------------


CARD = 14  # the explainer's card border


def _card_floor(width: int, height: int) -> int:
    """The smallest width that fills the card slot at the renderer's upscale (053):
    derived from the render constants here too, never typed as a number."""
    slot = min(render.CARD_MAX_W, render.CARD_BASE_H * width / height) - 2 * CARD
    return math.ceil(slot / render.CARD_MAX_UPSCALE)


@pytest.mark.parametrize(
    ("width", "height", "rejected"),
    [
        (1200, 800, False),
        (_card_floor(1600, 1000), 397, False),  # a landscape exactly filling the 980 px card
        (_card_floor(1600, 1000) - 1, 396, True),  # one pixel under it does not
        (_card_floor(1000, 1000), _card_floor(1000, 1000), False),  # a square fills 650 px
        (_card_floor(1000, 1000) - 1, _card_floor(1000, 1000) - 1, True),
        (600, 800, False),  # F1's lost portraits fill a card at <= 1.5x (053)
        (768, 896, False),
        (2400, 800, False),  # exactly 3:1 passes
        (2409, 800, True),  # 3.01:1 does not
        (800, 2409, True),
        (0, 0, False),  # a source that reports no size is checked after the download
    ],
)
def test_card_slot_reject_boundaries(width: int, height: int, rejected: bool) -> None:
    """5.2 / 053: the floor is the card slot the image will be shown in, at the
    renderer's 1.5x upscale, plus aspect > 3:1, at the boundary."""
    assert (base.reject_size(width, height, CARD) is not None) is rejected


@pytest.mark.parametrize(
    ("width", "height", "covers"),
    [
        (720, 1280, True),  # covers 1080x1920 at exactly 1.5x
        (719, 1280, False),
        (720, 1279, False),
        (1600, 1000, False),  # a landscape cannot cover the frame
    ],
)
def test_the_5_3_cover_rule_decides_treatment_not_rejection(
    width: int, height: int, covers: bool
) -> None:
    """053: an image that cannot cover the frame is a card (5.3), never a reject. 057:
    the upscale the cover is judged at is the caller's (the style's number)."""
    assert base.covers_frame(width, height, 1.5) is covers
    assert base.reject_size(width, height, CARD) is None


@pytest.mark.parametrize(
    ("width", "height", "covers"),
    [
        (540, 960, True),  # exactly 2.0x
        (539, 960, False),
        (540, 959, False),
        (819, 1024, True),  # run03's owner portrait, 1.875x
        (500, 900, False),  # needs 2.16x
    ],
)
def test_the_cover_rule_at_the_styles_two_x(width: int, height: int, covers: bool) -> None:
    """057: `broll.full_bleed_max_upscale` (2.0) is the limit the treatment is judged
    at; the card slot's 1.5x is untouched."""
    assert base.covers_frame(width, height, 2.0) is covers
    assert base.reject_size(width, height, CARD) is None


def test_a_rejected_candidate_says_why() -> None:
    assert base.reject_size(320, 240, CARD) == (
        "320x240 px cannot fill a 839 px wide card at <= 1.5x"
    )
    assert base.reject_size(3200, 800, CARD) == "aspect 4.00:1 > 3:1"


def test_the_card_slot_is_the_renderers_card_geometry() -> None:
    """053: one source of truth - the slot width is what `render.card_image_size` would
    give an image big enough not to be capped by the upscale."""
    assert base.card_slot_width(1600, 1000, 14) == render.card_image_size(1600, 1000, 14)[0]
    assert base.card_slot_width(700, 1400, 14) == render.card_image_size(700, 1400, 14)[0]


@pytest.mark.parametrize(
    "url",
    [
        "https://c8.alamy.com/comp/RBP0Y6/hindu-priest.jpg",
        "https://img.freepik.com/premium-photo/sadhu.jpg",
        "https://as2.ftcdn.net/jpg/15/11/75/65/1000_F_1511756593.jpg",
        "https://stock.adobe.com/in/images/a-monk/1511756593",
        "https://thumbs.dreamstime.com/b/hindu-sadhu.jpg",
        "https://media.istockphoto.com/id/1335898533/photo/beads.jpg?s=612x612",
        "https://media.gettyimages.com/id/2161923599/photo/devotees.jpg",
        "https://www.shutterstock.com/image-photo/x.jpg",
        "https://us.123rf.com/450wm/x.jpg",
        "https://st.depositphotos.com/x.jpg",
        "https://images.pond5.com/x.jpg",
        "https://cdn.canstockphoto.com/x.jpg",
    ],
)
def test_stock_preview_hosts_are_rejected_by_image_host(url: str) -> None:
    """053: watermarked stock previews never reach the judge, whose thumbnail cannot
    show the watermark."""
    candidate = Candidate(url=url, page_url="https://blog.example.org/post", width=0, height=0)
    why = base.reject_host(candidate)
    assert why is not None and why.startswith("stock preview host ")


def test_stock_preview_hosts_are_rejected_by_page_host_too() -> None:
    candidate = Candidate(
        url="https://cdn.example-images.net/x.jpg",
        page_url="https://www.alamy.com/stock-photo/x.html",
        width=0, height=0,
    )  # fmt: skip
    assert base.reject_host(candidate) == "stock preview host alamy.com"


@pytest.mark.parametrize(
    "url",
    [
        "https://upload.wikimedia.org/wikipedia/commons/a/a1/x.jpg",
        "https://images.pexels.com/photos/1/pexels-photo-1.jpeg",
        "https://notalamy.com/x.jpg",  # a suffix match, not a substring one
        "https://freepik.com.example.org/x.jpg",
    ],
)
def test_other_hosts_pass_the_stock_check(url: str) -> None:
    assert base.reject_host(Candidate(url=url, width=0, height=0)) is None


def test_a_body_over_fifteen_megabytes_or_not_an_image_is_rejected() -> None:
    """5.2: the two rejects that need the body, plus the content-type it claims."""
    assert base.reject_body(_png()) is None
    assert base.reject_body(_png(), "image/png") is None
    assert base.reject_body(b"<html>not an image</html>") == "the body is not an image"
    assert base.reject_body(_png(), "text/html") == "content-type text/html is not an image"
    huge = b"\xff\xd8\xff" + b"0" * base.MAX_BYTES
    assert base.reject_body(huge) == "15.0 MB > 15 MB"


def test_media_type_reads_the_bytes_not_the_name() -> None:
    assert base.media_type(_png()) == "image/png"
    assert base.media_type(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert base.media_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert base.media_type(b"nothing") is None


# --- search, parsing and the page follow (5.1) -----------------------------------------


def test_search_sends_the_query_and_a_desktop_header_set() -> None:
    fake = Fake(**{"bing.com": _html("search"), "archive.example.org": _html("page")})
    _source(fake).search(QUERY, 6)
    request = fake.requests[0]
    assert request.url.params["q"] == QUERY
    assert request.url.host == "www.bing.com"
    assert "Chrome" in request.headers["user-agent"]
    assert request.headers["accept-language"].startswith("en-US")


def test_search_reads_every_hit_with_its_page_and_printed_size() -> None:
    """5.1: `source_url` and `page_url` both recorded; the printed `W x H` is the
    reported size the hard rejects read before anything is paid for."""
    fake = Fake(**{"bing.com": _html("search"), "archive.example.org": _html("page")})
    found = _source(fake).search(QUERY, 6)
    assert [(c.width, c.height) for c in found] == [
        (1600, 1200), (640, 480), (3600, 900), (1400, 1050), (1200, 1200),
    ]  # fmt: skip
    first = found[0]
    assert first.url == "https://photos.example.org/full/india-gate-dusk.jpg"
    assert first.page_url == "https://photos.example.org/india-gate-dusk"
    assert first.thumb_url.startswith("https://thumbs.example.net/th?id=OIP.one")
    assert first.author == "photos.example.org"


def test_a_hit_with_no_image_url_is_followed_to_its_page(
) -> None:  # fmt: skip
    """13.1: the old engine's page-follow step. The fourth hit names only a page;
    its `og:image` is the image URL, resolved against the page it came from."""
    fake = Fake(**{"bing.com": _html("search"), "archive.example.org": _html("page")})
    followed = _source(fake).search(QUERY, 6)[3]
    assert followed.url == "https://www.archive.example.org/media/full/india-gate-archive.jpg"
    assert followed.page_url == PAGE_URL
    assert [str(r.url) for r in fake.requests if "archive" in str(r.url)] == [PAGE_URL]


def test_a_hit_whose_page_cannot_be_followed_is_dropped() -> None:
    fake = Fake(**{"bing.com": _html("search")})  # the page answers 404
    found = _source(fake).search(QUERY, 6)
    assert [c.url for c in found] == [
        "https://photos.example.org/full/india-gate-dusk.jpg",
        "https://blog.example.com/img/india-gate-thumb.jpg",
        "https://banners.example.net/img/india-gate-banner.jpg",
        "https://photos.example.org/full/india-gate-night.jpg",
    ]


def test_search_stops_at_n_candidates() -> None:
    fake = Fake(**{"bing.com": _html("search"), "archive.example.org": _html("page")})
    assert len(_source(fake).search(QUERY, 2)) == 2


def test_a_search_that_cannot_be_reached_finds_nothing_and_never_raises() -> None:
    """5.2: a source that fails is a source with no hits; the ladder moves on."""

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    source = web.WebImageSource(client=httpx.Client(transport=httpx.MockTransport(boom)))
    assert source.search(QUERY, 6) == []


def test_a_page_with_no_printed_size_reports_zero() -> None:
    """A size the page does not print is 0, which the hard rejects let through and
    the downloaded file's real dimensions settle instead."""
    page = (
        '<a class="iusc" m="{&quot;murl&quot;:&quot;https://e.example/x.jpg&quot;,'
        '&quot;purl&quot;:&quot;https://e.example/x&quot;}"></a>'
    )
    (hit,) = web.parse_results(page)
    assert (hit["width"], hit["height"]) == (0, 0)


def test_unparseable_result_json_is_skipped_not_fatal() -> None:
    page = (
        '<a class="iusc" m="{not json}"></a>'
        '<a class="iusc" m="{&quot;cid&quot;:&quot;1&quot;}"></a>'
    )
    assert [hit["cid"] for hit in web.parse_results(page)] == ["1"]


def test_og_image_prefers_og_over_twitter_and_resolves_relative_urls() -> None:
    page = (WEB / "page.html").read_text(encoding="utf-8")
    assert web.og_image(page, PAGE_URL) == (
        "https://www.archive.example.org/media/full/india-gate-archive.jpg"
    )
    assert web.og_image("<html></html>", PAGE_URL) == ""


# --- the thumbnail and the download (5.2) ----------------------------------------------


def test_the_thumbnail_is_the_search_engines_own_preview() -> None:
    fake = Fake(**{"thumbs.example.net": httpx.Response(200, content=_png())})
    candidate = Candidate(
        url="https://photos.example.org/x.jpg",
        thumb_url="https://thumbs.example.net/th?id=OIP.one",
        width=1600,
        height=1200,
    )
    assert _source(fake).thumbnail(candidate) == _png()
    assert "thumbs.example.net" in str(fake.requests[0].url)


def test_a_thumbnail_that_is_not_an_image_is_no_thumbnail() -> None:
    fake = Fake(**{"thumbs": httpx.Response(200, content=b"<html>")})
    candidate = Candidate(url="https://e/x.jpg", thumb_url="https://thumbs/x", width=0, height=0)
    assert _source(fake).thumbnail(candidate) is None


def test_fetch_writes_the_body_under_the_suffix_its_bytes_say(tmp_path: Path) -> None:
    fake = Fake(**{"photos": httpx.Response(200, content=_png(), headers={})})
    candidate = Candidate(url="https://photos.example.org/x.bin", width=1600, height=1200)
    written = _source(fake).fetch(candidate, tmp_path / "image")
    assert written == tmp_path / "image.png"
    assert written.read_bytes() == _png()


def test_fetch_refuses_a_body_the_hard_rejects_reject(tmp_path: Path) -> None:
    """5.2: the rejection names the candidate; the step drops it and takes the next."""
    fake = Fake(**{"photos": httpx.Response(200, content=b"<html>nope</html>")})
    candidate = Candidate(url="https://photos.example.org/x.jpg", width=1600, height=1200)
    with pytest.raises(base.SourceError, match="not an image"):
        _source(fake).fetch(candidate, tmp_path / "image")
    assert not list(tmp_path.iterdir())


def test_fetch_refuses_an_oversized_body_on_its_content_length(tmp_path: Path) -> None:
    fake = Fake(
        **{
            "photos": httpx.Response(
                200, content=_png(), headers={"content-length": str(base.MAX_BYTES + 1)}
            )
        }
    )
    candidate = Candidate(url="https://photos.example.org/x.jpg", width=1600, height=1200)
    with pytest.raises(base.SourceError, match="over the 15 MB limit"):
        _source(fake).fetch(candidate, tmp_path / "image")


def test_a_download_that_answers_an_error_is_a_source_error(tmp_path: Path) -> None:
    fake = Fake()  # everything 404s
    candidate = Candidate(url="https://photos.example.org/x.jpg", width=1600, height=1200)
    with pytest.raises(base.SourceError, match="could not be downloaded"):
        _source(fake).fetch(candidate, tmp_path / "image")
