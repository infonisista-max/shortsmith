"""What every real image source shares: the HTTP client, the judge's thumbnail and
the 5.2-checked download (decisions 5.1, 5.2, 13.1).

Each adapter (`web`, and the free libraries `commons`, `openverse`, `pexels`,
`pixabay`) differs only in the request it builds and the JSON or markup it maps into
`Candidate`. Everything below the mapping is the same for all of them and lives here:

- `_get` is one capped GET through the adapter's own client (tests pass an
  `httpx.MockTransport`, so no adapter test ever touches the network).
- `thumbnail` downloads the API's own small preview for the relevance judge, capped at
  2 MB and refused when the bytes are not an image; the judge then reads the URL only.
- `fetch` downloads the chosen candidate, applies the 5.2 body rejects (over 15 MB, not
  an image) *before* the file is written, and names the file after what its bytes
  really are. A refusal is a `SourceError`, so the step drops that candidate and takes
  the next one; the beat is never rejected for it.

Nothing here is metered: the four 018 sources are free (Pexels and Pixabay want a key
but charge nothing), so no `search` ledger row is written. A metered adapter adds one
of its own before calling `search`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import httpx

from shortsmith.assets.base import MAX_BYTES, ImageSource, SourceError, media_type, reject_body
from shortsmith.contracts import Candidate

TIMEOUT_S = 30.0
THUMB_MAX_BYTES = 2 * 1024 * 1024

SUFFIX: Mapping[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}


class HttpImageSource(ImageSource):
    """The shared half of a real `ImageSource`; subclasses add `origin` and `search`.

    `headers` are sent with every request (a browser header set for the scraped web
    source, an API key for Pexels). `client` is the seam the tests replace."""

    headers: Mapping[str, str] = {}

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
        max_bytes: int = MAX_BYTES,
    ) -> None:
        self._client = client
        self._timeout_s = timeout_s
        self._max_bytes = max_bytes
        self.searches = 0

    def _get(
        self, url: str, *, params: Mapping[str, str] | None = None
    ) -> httpx.Response:
        sent = dict(self.headers)
        client = self._client
        if client is not None:
            return client.get(url, params=params, headers=sent, follow_redirects=True)
        with httpx.Client(timeout=self._timeout_s, follow_redirects=True) as owned:
            return owned.get(url, params=params, headers=sent)

    def _json(self, url: str, params: Mapping[str, str]) -> object | None:
        """One GET answered as JSON, or None when the source could not be read: a
        source that fails is a source with no hits and never fails the job (5.2)."""
        self.searches += 1
        try:
            response = self._get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    def thumbnail(self, candidate: Candidate) -> bytes | None:
        url = candidate.thumb_url or candidate.url
        try:
            response = self._get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        body = response.content
        if len(body) > THUMB_MAX_BYTES or media_type(body) is None:
            return None
        return body

    def fetch(self, candidate: Candidate, dest: Path) -> Path:
        """Download the chosen candidate, 5.2 body rejects applied before writing."""
        try:
            response = self._get(candidate.url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceError(f"{candidate.url} could not be downloaded: {exc}") from None
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self._max_bytes:
            raise SourceError(
                f"{candidate.url} is {int(declared) / 1024 / 1024:.1f} MB, "
                f"over the {self._max_bytes // 1024 // 1024} MB limit"
            )
        body = response.content
        why = reject_body(body, response.headers.get("content-type", ""))
        if why is not None:
            raise SourceError(f"{candidate.url} rejected: {why}")
        kind = media_type(body)
        assert kind is not None  # reject_body already refused a body that is not an image
        path = dest.with_suffix(SUFFIX[kind])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path


def field(value: object, name: str) -> object:
    """`value[name]` when `value` is a JSON object, else None."""
    if isinstance(value, dict):
        return value.get(name)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    return None


def text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def number(value: object) -> int:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def items(value: object, name: str) -> list[object]:
    """The list at `value[name]`, or an empty list when the reply has no such list."""
    listed = field(value, name)
    return list(listed) if isinstance(listed, list) else []  # pyright: ignore[reportUnknownArgumentType]


def domain(url: str) -> str | None:
    host = httpx.URL(url).host
    return host.removeprefix("www.") or None
