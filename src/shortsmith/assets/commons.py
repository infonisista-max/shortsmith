"""Wikimedia Commons, the third rung of the 5.1 source order (ticket 018).

One `api.php` call per query: a `search` generator over the File namespace, with
`imageinfo` asked for the original URL, its size, the 320 px thumbnail the relevance
judge looks at, and `extmetadata`, which carries the licence short name and the artist
Commons itself recorded. Both are written into the candidate verbatim: v1 records
rights, it never filters on them (5.1, 5.4).

The API answers the generator's pages in no particular order and puts the search rank
in each page's `index`, so the candidates are returned in rank order, which is the
"source's own order" the judge's ties fall back to (5.2). A page with no image URL (a
sound file, a page the generator returned without `imageinfo`) is not a candidate.
No key and no charge, so no ledger row.
"""

from __future__ import annotations

import html
import re

from shortsmith.assets.http import HttpImageSource, field, items, number, text
from shortsmith.contracts import Candidate

API_URL = "https://commons.wikimedia.org/w/api.php"
THUMB_WIDTH = 320
# `filetype:bitmap` keeps the generator off PDFs, SVGs and media files; the rest of
# the query is the beat's own words.
FILETYPE = "filetype:bitmap"

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def artist(value: str) -> str | None:
    """The author from `extmetadata.Artist`, which Commons stores as HTML."""
    plain = _SPACE.sub(" ", html.unescape(_TAG.sub(" ", value))).strip()
    return plain or None


def _meta(info: object, name: str) -> str:
    return text(field(field(field(info, "extmetadata"), name), "value"))


class CommonsImageSource(HttpImageSource):
    origin = "commons"

    def search(self, query: str, n: int) -> list[Candidate]:
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "generator": "search",
            "gsrsearch": f"{FILETYPE} {query}",
            "gsrnamespace": "6",
            "gsrlimit": str(n),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": str(THUMB_WIDTH),
        }
        body = self._json(API_URL, params)
        if body is None:
            return []
        pages = items(field(body, "query"), "pages")
        ranked = sorted(pages, key=lambda page: number(field(page, "index")))
        candidates: list[Candidate] = []
        for page in ranked:
            infos = items(page, "imageinfo")
            info = infos[0] if infos else None
            url = text(field(info, "url"))
            if not url:
                continue
            candidates.append(
                Candidate(
                    url=url,
                    page_url=text(field(info, "descriptionurl")),
                    thumb_url=text(field(info, "thumburl")),
                    width=number(field(info, "width")),
                    height=number(field(info, "height")),
                    author=artist(_meta(info, "Artist")),
                    licence=_meta(info, "LicenseShortName") or "unknown",
                )
            )
            if len(candidates) >= n:
                break
        return candidates
