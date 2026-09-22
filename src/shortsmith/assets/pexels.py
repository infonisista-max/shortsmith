"""Pexels, the fifth rung of the 5.1 source order (ticket 018).

One `GET /v1/search` per query with `PEXELS_API_KEY` in the `Authorization` header.
The key is free and the search is not metered, so no ledger row is written; the key is
a `SecretStr`, so it never reaches a log or a repr. Without a key the adapter is not
built at all and the ladder simply skips this rung (`assets.from_settings`).

Each photo names its original file, its page on pexels.com, a medium preview for the
relevance judge and the photographer. The licence is the same for every photo on the
site, so it is recorded as a constant line rather than read from the reply (5.4: the
row records what the source says, it is never filtered on).
"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from shortsmith.assets.base import MAX_BYTES
from shortsmith.assets.http import TIMEOUT_S, HttpImageSource, field, items, number, text
from shortsmith.contracts import Candidate

API_URL = "https://api.pexels.com/v1/search"
LICENCE = "Pexels License"
# The `src` sizes, best first: the original is what the hit's reported width and
# height describe, so anything else would misreport the size to the 5.2 hard rejects.
FULL = ("original",)
PREVIEW = ("medium", "small", "tiny", "large")


def _first(src: object, names: tuple[str, ...]) -> str:
    for name in names:
        url = text(field(src, name))
        if url:
            return url
    return ""


class PexelsImageSource(HttpImageSource):
    origin = "pexels"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
        max_bytes: int = MAX_BYTES,
    ) -> None:
        super().__init__(client=client, timeout_s=timeout_s, max_bytes=max_bytes)
        self._api_key = api_key
        self.headers = {"Authorization": api_key.get_secret_value()}

    def search(self, query: str, n: int) -> list[Candidate]:
        body = self._json(API_URL, {"query": query, "per_page": str(n)})
        if body is None:
            return []
        candidates: list[Candidate] = []
        for photo in items(body, "photos"):
            src = field(photo, "src")
            url = _first(src, FULL)
            if not url:
                continue
            candidates.append(
                Candidate(
                    url=url,
                    page_url=text(field(photo, "url")),
                    thumb_url=_first(src, PREVIEW),
                    width=number(field(photo, "width")),
                    height=number(field(photo, "height")),
                    author=text(field(photo, "photographer")) or None,
                    licence=LICENCE,
                )
            )
            if len(candidates) >= n:
                break
        return candidates
