"""Openverse, the fourth rung of the 5.1 source order (ticket 018).

One `GET /v1/images/` per query against the public API, which needs no key and
charges nothing. Each result already names the full image, the page it was found on,
Openverse's own thumbnail endpoint, the reported size and the creator, so the mapping
is direct; the licence is a code plus a version (`by-sa` + `4.0`), which
`licence_text` turns into the line the rights log stores ("CC BY-SA 4.0"). v1 records
that text, it never filters on it (5.1, 5.4).

A result with no full-image URL (Openverse has the record but not the file) is not a
candidate: the hard rejects and the judge only ever see something fetchable.
"""

from __future__ import annotations

from shortsmith.assets.http import HttpImageSource, field, items, number, text
from shortsmith.contracts import Candidate

API_URL = "https://api.openverse.org/v1/images/"
# The codes Openverse uses that are not a "CC <code> <version>" licence.
NAMED: dict[str, str] = {
    "pdm": "Public Domain Mark",
    "nc-sampling+": "CC Sampling Plus (NonCommercial)",
    "sampling+": "CC Sampling Plus",
}


def licence_text(code: str, version: str | None) -> str:
    """The licence line the rights log stores, from Openverse's code and version."""
    code = (code or "").strip().lower()
    if not code:
        return "unknown"
    if code in NAMED:
        return NAMED[code]
    name = "CC0" if code == "cc0" else f"CC {code.upper()}"
    return f"{name} {version}".strip() if version else name


class OpenverseImageSource(HttpImageSource):
    origin = "openverse"

    def search(self, query: str, n: int) -> list[Candidate]:
        body = self._json(API_URL, {"q": query, "page_size": str(n)})
        if body is None:
            return []
        candidates: list[Candidate] = []
        for result in items(body, "results"):
            url = text(field(result, "url"))
            if not url:
                continue
            candidates.append(
                Candidate(
                    url=url,
                    page_url=text(field(result, "foreign_landing_url")),
                    thumb_url=text(field(result, "thumbnail")),
                    width=number(field(result, "width")),
                    height=number(field(result, "height")),
                    author=text(field(result, "creator")) or None,
                    licence=licence_text(
                        text(field(result, "license")), text(field(result, "license_version"))
                    ),
                )
            )
            if len(candidates) >= n:
                break
        return candidates
