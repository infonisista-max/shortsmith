"""The image-source interface and the code-only hard rejects (decisions 5.1, 5.2).

`ImageSource` is what every searched source implements: `search` returns the source's
own candidates in its own order, `thumbnail` gives the judge something cheap to look
at, and `fetch` downloads one candidate to the job's cache. The adapters live beside
this module (`web`, ticket 017; the free libraries, ticket 018); `FakeImageSource`
(12.1) is the one tests and smoke run on.

The hard rejects (5.2) are code, never a model call, and they reject a *candidate*,
never a beat: short side under 800 px, aspect past 3:1, a body over 15 MB, a body that
is not an image. `reject_size` runs twice - once on what the source reported, before
the judge is paid anything, and once on the downloaded file's real dimensions, which
is the only size a source cannot get wrong. A source that reports no size (0) is
checked after the download only.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from shortsmith.config import asset_source_names
from shortsmith.contracts import AssetPolicy, Candidate, SearchOrigin

# 5.1: the names `ASSET_SOURCES` may carry that are not searched - owner references
# always come first and generation always last, whether or not they are listed.
BOOKENDS = ("owner", "generate")

# 5.2: the code-only hard rejects.
MIN_SHORT_SIDE = 800
MAX_ASPECT = 3.0
MAX_BYTES = 15 * 1024 * 1024
EPS = 1e-9

# What an image body may say it is; anything else is a non-image body (5.2).
IMAGE_TYPES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif", "image/bmp", "image/tiff"}
)
# The first bytes of the formats the renderer can read, for a body that claims nothing.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)


class SourceError(RuntimeError):
    """One candidate could not be had (a refused download, a rejected body). The step
    drops that candidate and takes the next one; the beat is never rejected (5.2)."""


def media_type(body: bytes) -> str | None:
    """The image type `body` really is, by its first bytes; None when it is not one.
    WebP is `RIFF....WEBP`, so it is checked over the whole twelve-byte header."""
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    for magic, name in _MAGIC:
        if body.startswith(magic):
            return name
    return None


def reject_size(width: int, height: int) -> str | None:
    """Why the dimensions fail the 5.2 hard rejects, or None. A reported 0 (a source
    that does not say) passes here and is caught on the downloaded file instead."""
    if width <= 0 or height <= 0:
        return None
    if min(width, height) < MIN_SHORT_SIDE:
        return f"short side {min(width, height)} px < {MIN_SHORT_SIDE} px"
    if max(width, height) / min(width, height) > MAX_ASPECT + EPS:
        return f"aspect {max(width, height) / min(width, height):.2f}:1 > {MAX_ASPECT:g}:1"
    return None


def reject_body(body: bytes, content_type: str = "") -> str | None:
    """Why a downloaded body fails the 5.2 hard rejects, or None."""
    if len(body) > MAX_BYTES:
        return f"{len(body) / 1024 / 1024:.1f} MB > {MAX_BYTES // 1024 // 1024} MB"
    declared = content_type.split(";")[0].strip().lower()
    if declared and declared not in IMAGE_TYPES:
        return f"content-type {declared} is not an image"
    if media_type(body) is None:
        return "the body is not an image"
    return None


class ImageSource(ABC):
    """One searched source. `search` returns candidates in the source's own order;
    `fetch` downloads one to `dest` plus the file's suffix and returns the path;
    `thumbnail` returns small image bytes for the relevance judge (5.2), or None when
    the source has nothing cheap to show it."""

    origin: SearchOrigin

    @abstractmethod
    def search(self, query: str, n: int) -> list[Candidate]: ...

    @abstractmethod
    def fetch(self, candidate: Candidate, dest: Path) -> Path: ...

    def thumbnail(self, candidate: Candidate) -> bytes | None:
        return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


class FakeImageSource(ImageSource):
    """Solid PNGs at `size` (or `sizes[query]`) behind `https://fake.invalid/` URLs.
    `nothing_found` answers every query with nothing, `nothing_for` those queries.
    `searches` and `fetches` count the calls so tests can prove the cache."""

    def __init__(
        self,
        origin: SearchOrigin,
        *,
        size: tuple[int, int] = (1600, 1000),
        sizes: Mapping[str, tuple[int, int]] | None = None,
        nothing_for: Iterable[str] = (),
        nothing_found: bool = False,
    ) -> None:
        self.origin = origin
        self.size = size
        self.sizes = dict(sizes or {})
        self.nothing_for = frozenset(nothing_for)
        self.nothing_found = nothing_found
        self.searches = 0
        self.fetches = 0

    def search(self, query: str, n: int) -> list[Candidate]:
        self.searches += 1
        if self.nothing_found or query in self.nothing_for:
            return []
        width, height = self.sizes.get(query, self.size)
        base = f"https://fake.invalid/{self.origin}/{_slug(query)}"
        return [
            Candidate(
                url=f"{base}/{i}.png",
                page_url=f"{base}/{i}",
                thumb_url=f"{base}/{i}-thumb.png",
                width=width,
                height=height,
                author=f"fake {self.origin}",
            )
            for i in range(1, n + 1)
        ]

    def _image(self, candidate: Candidate, size: tuple[int, int]) -> Image.Image:
        digest = hashlib.sha256(candidate.url.encode("utf-8")).digest()
        image = Image.new("RGB", size, tuple(digest[:3]))
        label = candidate.url.removeprefix("https://fake.invalid/")
        font = ImageFont.load_default(size=max(16, size[0] // 24))
        ImageDraw.Draw(image).text((24, 24), label, fill=(255, 255, 255), font=font)
        return image

    def fetch(self, candidate: Candidate, dest: Path) -> Path:
        self.fetches += 1
        path = dest.with_suffix(".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._image(candidate, (candidate.width, candidate.height)).save(path, format="PNG")
        return path

    def thumbnail(self, candidate: Candidate) -> bytes | None:
        buffer = BytesIO()
        self._image(candidate, (160, 100)).save(buffer, format="PNG")
        return buffer.getvalue()


def parse_order(text: str) -> tuple[str, ...]:
    """`ASSET_SOURCES` as a tuple of names, blanks dropped."""
    return asset_source_names(text)


def source_order(order: Sequence[str], policy: AssetPolicy) -> list[str]:
    """The *searched* sources in `order` for `policy` (5.1, 5.2): the fixed bookends
    of the ladder (`owner`, `generate`) are listed in the config for readability but
    are not searched, and `rights_safe` removes web search."""
    dropped: set[str] = {*BOOKENDS, *({"web"} if policy == "rights_safe" else set())}
    return [name for name in order if name not in dropped]
