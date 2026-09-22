"""The `web` image source: direct HTTP image search with page follow (5.1, 13.1).

The first real source in the 5.1 order, and the one `ASSET_POLICY=rights_safe`
removes. One GET to the image-search endpoint per query; the results page carries one
JSON blob per hit (the `m` attribute of each result link) with the image URL, the page
it sits on and its thumbnail, and the printed `W x H` beside it is the reported size
the 5.2 hard rejects read before anything is paid for. A hit that names only a page is
followed to that page and its `og:image` (or `twitter:image`) is the image URL, which
is the "page follow" the old engine's scrape step did.

Nothing is scraped for free that the step does not need: `thumbnail` downloads the
search engine's own small preview for the relevance judge, and `fetch` downloads the
full image only for the candidate the judge chose. Both cap what they read, and
`fetch` applies the 5.2 body rejects (over 15 MB, not an image) before the file is
written, raising `SourceError` so the step drops that candidate and takes the next.

No licence filtering in v1 (5.1): every web image gets a rights-log row with both its
URLs, and the step always re-dresses it as a card, never shows it raw. Scraped search
is free, so no `search` ledger row is written here; a metered adapter (018) adds one.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import cast
from urllib.parse import urljoin

import httpx

from shortsmith.assets.base import MAX_BYTES, ImageSource, SourceError, media_type, reject_body
from shortsmith.contracts import Candidate

SEARCH_URL = "https://www.bing.com/images/search"
TIMEOUT_S = 30.0
THUMB_MAX_BYTES = 2 * 1024 * 1024
# A desktop browser's header set: the results page is the desktop one, and a plain
# default user agent is served a page with no result JSON at all.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# One result link per hit: `<a class="iusc" ... m="{&quot;murl&quot;:&quot;...&quot;}">`.
_RESULT = re.compile(r'class="iusc"[^>]*?\sm="([^"]*)"', re.IGNORECASE)
# The size printed beside a hit, "1200 x 800", in the markup that follows its link.
_SIZE = re.compile(r"(\d{2,5})\s*[x×]\s*(\d{2,5})")
_META = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](og:image|twitter:image)(?::src)?["\'][^>]*>',
    re.IGNORECASE,
)
_CONTENT = re.compile(r'content=["\']([^"\']+)["\']', re.IGNORECASE)
SIZE_WINDOW = 4000  # characters after a hit's link its printed size may appear in


def _string(fields: dict[str, object], name: str) -> str:
    value = fields.get(name)
    return value.strip() if isinstance(value, str) else ""


def parse_results(page: str) -> list[dict[str, object]]:
    """One hit per result link: its `m` JSON plus the size printed beside it as
    `width` and `height` (0 when the page does not print one)."""
    hits: list[dict[str, object]] = []
    for match in _RESULT.finditer(page):
        try:
            blob: object = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        if not isinstance(blob, dict):
            continue
        fields = cast("dict[str, object]", blob)
        size = _SIZE.search(page, match.end(), match.end() + SIZE_WINDOW)
        hits.append(
            fields
            | {
                "width": int(size.group(1)) if size else 0,
                "height": int(size.group(2)) if size else 0,
            }
        )
    return hits


def og_image(page: str, page_url: str) -> str:
    """The image a result page points at through `og:image` or `twitter:image`."""
    for match in _META.finditer(page):
        content = _CONTENT.search(match.group(0))
        if content is not None and content.group(1).strip():
            return urljoin(page_url, html.unescape(content.group(1).strip()))
    return ""


class WebImageSource(ImageSource):
    origin = "web"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        endpoint: str = SEARCH_URL,
        timeout_s: float = TIMEOUT_S,
        max_bytes: int = MAX_BYTES,
    ) -> None:
        self._client = client
        self._endpoint = endpoint
        self._timeout_s = timeout_s
        self._max_bytes = max_bytes
        self.searches = 0

    def _get(self, url: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        client = self._client
        if client is not None:
            return client.get(url, params=params, headers=HEADERS, follow_redirects=True)
        with httpx.Client(timeout=self._timeout_s, follow_redirects=True) as owned:
            return owned.get(url, params=params, headers=HEADERS)

    def search(self, query: str, n: int) -> list[Candidate]:
        """The first `n` hits for `query`, page-followed when a hit names no image."""
        self.searches += 1
        params = {"q": query, "form": "HDRSC2", "first": "1"}
        try:
            response = self._get(self._endpoint, params=params)
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        candidates: list[Candidate] = []
        for hit in parse_results(response.text):
            page_url = _string(hit, "purl")
            url = _string(hit, "murl") or (self._follow(page_url) if page_url else "")
            if not url:
                continue
            candidates.append(
                Candidate(
                    url=url,
                    page_url=page_url,
                    thumb_url=_string(hit, "turl"),
                    width=cast("int", hit.get("width", 0)),
                    height=cast("int", hit.get("height", 0)),
                    author=_domain(page_url or url),
                )
            )
            if len(candidates) >= n:
                break
        return candidates

    def _follow(self, page_url: str) -> str:
        try:
            response = self._get(page_url)
            response.raise_for_status()
        except httpx.HTTPError:
            return ""
        return og_image(response.text, page_url)

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
        path = dest.with_suffix(_SUFFIX[kind])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path


_SUFFIX = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}


def _domain(url: str) -> str | None:
    host = httpx.URL(url).host
    return host.removeprefix("www.") or None
