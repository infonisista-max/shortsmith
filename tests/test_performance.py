"""performance: the read-only YouTube Data API pull (decisions 10.2, 14.1(a); ticket 034).

The adapter is driven on a recorded `videos.list` body through an `httpx.MockTransport`,
so the request (endpoint, `part=statistics`, the id, the key as a header and never in
the URL) and the mapping of `statistics.viewCount` are pinned with no network. The
video id parser is pure. Never an upload: the only call is a GET."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from shortsmith import config, performance
from shortsmith.performance import YouTube, YouTubeError

FIXTURES = Path(__file__).parent / "fixtures" / "youtube"
KEY = SecretStr("test-key-not-a-real-one")


def recorded() -> object:
    """The recorded `videos.list` body (also driven by the app tests)."""
    return json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))


class Tape:
    def __init__(self, body: object | None, *, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.body is None:
            return httpx.Response(self.status, text="not json")
        return httpx.Response(self.status, json=self.body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def _youtube(tape: Tape) -> YouTube:
    return YouTube(api_key=KEY, client=tape.client())


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtube.com/shorts/abc123DEF45", "abc123DEF45"),
        ("https://www.youtube.com/shorts/abc123DEF45?feature=share", "abc123DEF45"),
        ("https://youtu.be/abc123DEF45", "abc123DEF45"),
        ("https://www.youtube.com/watch?v=abc123DEF45&t=3s", "abc123DEF45"),
        ("https://m.youtube.com/watch?v=abc123DEF45", "abc123DEF45"),
        ("  https://youtube.com/shorts/abc123DEF45  ", "abc123DEF45"),
        ("https://example.com/shorts/abc123DEF45", None),
        ("https://youtube.com/channel/UCabc", None),
        ("not a url", None),
        ("", None),
    ],
)
def test_the_video_id_is_read_from_the_three_url_shapes(url: str, expected: str | None) -> None:
    assert performance.video_id(url) == expected


def test_one_get_with_the_key_in_a_header_returns_the_view_count() -> None:
    tape = Tape(recorded())
    assert _youtube(tape).views("abc123DEF45") == 18342
    (request,) = tape.requests
    assert request.method == "GET"
    assert str(request.url).startswith(performance.API_URL)
    assert request.url.params["part"] == "statistics"
    assert request.url.params["id"] == "abc123DEF45"
    assert "key" not in request.url.params and KEY.get_secret_value() not in str(request.url)
    assert request.headers["x-goog-api-key"] == KEY.get_secret_value()


def test_a_video_the_api_does_not_return_is_an_error_naming_it() -> None:
    body: object = json.loads('{"kind": "youtube#videoListResponse", "items": []}')
    with pytest.raises(YouTubeError, match="abc123DEF45"):
        _youtube(Tape(body)).views("abc123DEF45")


def test_an_api_error_or_a_body_that_is_not_the_list_is_a_youtube_error() -> None:
    quota: object = json.loads('{"error": {"code": 403, "message": "quota"}}')
    with pytest.raises(YouTubeError, match="403"):
        _youtube(Tape(quota, status=403)).views("x")
    with pytest.raises(YouTubeError):
        _youtube(Tape(None)).views("x")
    no_count: object = json.loads('{"items": [{"id": "x", "statistics": {}}]}')
    with pytest.raises(YouTubeError, match="viewCount"):
        _youtube(Tape(no_count)).views("x")


def test_parse_views_reads_the_string_count() -> None:
    assert performance.parse_views(recorded(), "abc123DEF45") == 18342


def test_from_settings_is_none_without_the_key() -> None:
    off = config.Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert performance.from_settings(off) is None
    on = config.Settings(_env_file=None, youtube_api_key=KEY)  # pyright: ignore[reportCallIssue]
    assert isinstance(performance.from_settings(on), YouTube)
