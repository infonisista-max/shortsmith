"""Pixabay, the last searched rung of the 5.1 source order (ticket 018).

One `GET /api/` per query with `PIXABAY_API_KEY` as a query parameter (the API takes
the key no other way). The key is free and the search is not metered, so no ledger row
is written; without a key the adapter is not built and the ladder skips this rung
(`assets.from_settings`). The licence is the same for every file on the site, so it is
recorded as a constant line (5.4).

The size trap: a hit's `imageWidth`/`imageHeight` describe the *original* upload, but
the API only hands out `largeImageURL`, which is capped at 1280 px on its long side.
Reporting the original would tell the 5.2 hard rejects a size the download cannot
deliver, so `scaled` reports what will actually be fetched. The rejects still run again
on the downloaded file, which is the only size a source cannot get wrong.
"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from shortsmith.assets.base import MAX_BYTES
from shortsmith.assets.http import TIMEOUT_S, HttpImageSource, field, items, number, text
from shortsmith.contracts import Candidate

API_URL = "https://pixabay.com/api/"
LICENCE = "Pixabay Content License"
MIN_PER_PAGE = 3  # the API refuses a smaller page than this
LARGE_MAX_SIDE = 1280  # what `largeImageURL` is capped at


def scaled(width: int, height: int, max_side: int) -> tuple[int, int]:
    """`width` x `height` fitted inside `max_side` on its long side, never upscaled;
    a size the source did not report (0) stays 0 and is settled after the download."""
    longest = max(width, height)
    if longest <= 0 or longest <= max_side:
        return width, height
    factor = max_side / longest
    return round(width * factor), round(height * factor)


class PixabayImageSource(HttpImageSource):
    origin = "pixabay"

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

    def search(self, query: str, n: int) -> list[Candidate]:
        params = {
            "key": self._api_key.get_secret_value(),
            "q": query,
            "per_page": str(max(n, MIN_PER_PAGE)),
            "image_type": "photo",
            "safesearch": "true",
        }
        body = self._json(API_URL, params)
        if body is None:
            return []
        candidates: list[Candidate] = []
        for hit in items(body, "hits"):
            url = text(field(hit, "largeImageURL"))
            if not url:
                continue
            width, height = scaled(
                number(field(hit, "imageWidth")),
                number(field(hit, "imageHeight")),
                LARGE_MAX_SIDE,
            )
            candidates.append(
                Candidate(
                    url=url,
                    page_url=text(field(hit, "pageURL")),
                    thumb_url=text(field(hit, "webformatURL")) or text(field(hit, "previewURL")),
                    width=width,
                    height=height,
                    author=text(field(hit, "user")) or None,
                    licence=LICENCE,
                )
            )
            if len(candidates) >= n:
                break
        return candidates
