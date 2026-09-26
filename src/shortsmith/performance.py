"""The published short's audience (decisions 10.2, 14.1(a); ticket 034).

Every published short logs its real YouTube performance on the job so the critic can
later be checked against an actual audience (10.2). The fields live on `job.json`
(`jobs.Performance`: published URL, views, retention) and are typed in on the job page.
When `YOUTUBE_API_KEY` is set, `YouTube.views` fills the view count for a stored URL
with one read-only `videos.list` call on the Data API v3 (`part=statistics`); the key
travels as the `x-goog-api-key` header, never in the URL. Retention is not on the Data
API (it is Analytics, an OAuth grant), so it stays a hand-typed figure. Never an
upload (14.1(a)): the only call this module makes is a GET.

The key is free-tier quota, not metered cash, so no ledger row is written (the same
footing as Pexels, Pixabay and Freesound). A pull that fails is a `YouTubeError` the
route turns into a one-line note on the job; the manual fields are stored either way.
"""

from __future__ import annotations

import re
from typing import cast
from urllib.parse import parse_qs, urlparse

import httpx
from pydantic import SecretStr

from shortsmith.config import Settings

API_URL = "https://www.googleapis.com/youtube/v3/videos"
TIMEOUT_S = 20.0
HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,}$")


class YouTubeError(RuntimeError):
    """The Data API could not give a view count; the message says why."""


def video_id(url: str) -> str | None:
    """The video id in a `youtube.com/shorts/<id>`, `youtu.be/<id>` or
    `youtube.com/watch?v=<id>` URL; None for anything else."""
    parsed = urlparse(url.strip())
    if parsed.hostname not in HOSTS:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    candidate = ""
    if parsed.hostname == "youtu.be":
        candidate = parts[0] if parts else ""
    elif len(parts) == 2 and parts[0] in ("shorts", "embed", "live"):
        candidate = parts[1]
    elif parts == ["watch"]:
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    return candidate if _VIDEO_ID.match(candidate) else None


def _field(value: object, name: str) -> object:
    if isinstance(value, dict):
        return value.get(name)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    return None


def parse_views(body: object, wanted: str) -> int:
    """`items[].statistics.viewCount` (a string on the wire) for the video `wanted`."""
    listed = _field(body, "items")
    if not isinstance(listed, list):
        raise YouTubeError("the reply has no `items` list")
    items = cast("list[object]", listed)
    for item in items:
        if _field(item, "id") != wanted:
            continue
        count = _field(_field(item, "statistics"), "viewCount")
        if isinstance(count, str) and count.isdigit():
            return int(count)
        if isinstance(count, int) and not isinstance(count, bool):
            return count
        raise YouTubeError(f"video {wanted} has no `statistics.viewCount` in the reply")
    raise YouTubeError(f"video {wanted} is not in the reply (private, removed, or a wrong id)")


class YouTube:
    """The read-only pull. `client` is the seam tests replace with an
    `httpx.MockTransport`; the key is a `SecretStr` and never reaches a repr."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._timeout_s = timeout_s

    def _get(self, params: dict[str, str]) -> httpx.Response:
        headers = {"x-goog-api-key": self._api_key.get_secret_value()}
        client = self._client
        if client is not None:
            return client.get(API_URL, params=params, headers=headers)
        with httpx.Client(timeout=self._timeout_s) as owned:
            return owned.get(API_URL, params=params, headers=headers)

    def views(self, video: str) -> int:
        """The current view count of `video`; `YouTubeError` when it cannot be read."""
        try:
            response = self._get({"part": "statistics", "id": video})
        except httpx.HTTPError as exc:
            raise YouTubeError(f"YouTube could not be reached: {exc}") from None
        if response.status_code != 200:
            raise YouTubeError(
                f"YouTube answered {response.status_code}: {_error_text(response)}"
            )
        try:
            body: object = response.json()
        except ValueError:
            raise YouTubeError("YouTube did not answer with JSON") from None
        return parse_views(body, video)


def _error_text(response: httpx.Response) -> str:
    try:
        message = _field(_field(response.json(), "error"), "message")
    except ValueError:
        return response.text[:200]
    return str(message)[:200] if message is not None else response.text[:200]


def from_settings(settings: Settings) -> YouTube | None:
    """The pull `YOUTUBE_API_KEY` enables; None leaves views a hand-typed field."""
    if settings.youtube_api_key is None:
        return None
    return YouTube(api_key=settings.youtube_api_key)
