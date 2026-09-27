"""The image-source interface and the code-only hard rejects (decisions 5.1, 5.2).

`ImageSource` is what every searched source implements: `search` returns the source's
own candidates in its own order, `thumbnail` gives the judge something cheap to look
at, and `fetch` downloads one candidate to the job's cache. The adapters live beside
this module (`web`, ticket 017; the free libraries, ticket 018); `FakeImageSource`
(12.1) is the one tests and smoke run on.

The hard rejects (5.2, amended by 053) are code, never a model call, and they reject a
*candidate*, never a beat: too small for the slot it will be shown in, aspect past 3:1,
a stock-preview host, a body over 15 MB, a body that is not an image. `reject_size`
runs twice - once on what the source reported, before the judge is paid anything, and
once on the downloaded file's real dimensions, which is the only size a source cannot
get wrong. A source that reports no size (0) is checked after the download only.

The size floor follows the slot, not a flat 800 px (053, rule 4): the image must fill
the archival card the renderer would draw for its aspect at no more than the renderer's
1.5x upscale (`card_slot_width`, read from `render`'s numbers, never typed here, with
the style's card border). That is the smallest slot any sourced beat is shown in: a
`photo` beat that cannot be full-bleed is a card by 5.3, and a list or wall base still
sits dimmed under its rows or cells. No real photo is lost to a floor stricter than
where it will be shown; the 5.3 cover requirement decides full-bleed *treatment*
(`assets.full_bleed`), never rejection.

Stock-preview hosts (053, rule 3) are dropped before judging: F1's judge scored alamy
comps and Freepik premium images 3/3 from thumbnails where the watermark is not
visible. `STOCK_HOSTS` is the one list; `reject_host` checks the image host and the
page host, by suffix.

A source may `note` why a search returned what it did (053, rule 5: a 403, an empty
answer); the step drains the notes into the job log after every search.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont

from shortsmith.config import asset_source_names
from shortsmith.contracts import AssetPolicy, Candidate, SearchOrigin

# 5.1: the names `ASSET_SOURCES` may carry that are not searched - owner references
# always come first and generation always last, whether or not they are listed.
BOOKENDS = ("owner", "generate")

# 5.2: the code-only hard rejects.
MAX_ASPECT = 3.0
MAX_BYTES = 15 * 1024 * 1024
EPS = 1e-9

# 5.3: the frame a full-bleed photo must cover and the largest upscale allowed.
FRAME_W, FRAME_H = 1080, 1920
MAX_UPSCALE = 1.5

# 053 rule 3: hosts whose "images" are watermarked previews of paid stock (image host or
# page host, matched by suffix so every CDN subdomain counts).
STOCK_HOSTS: tuple[str, ...] = (
    "alamy.com",
    "freepik.com",
    "stock.adobe.com",
    "ftcdn.net",
    "dreamstime.com",
    "istockphoto.com",
    "gettyimages.com",
    "shutterstock.com",
    "123rf.com",
    "depositphotos.com",
    "pond5.com",
    "canstockphoto.com",
)

def covers_frame(width: int, height: int) -> bool:
    """5.3: the image covers 1080x1920 within the 1.5x upscale."""
    return max(FRAME_W / width, FRAME_H / height) <= MAX_UPSCALE + EPS


def card_slot_width(width: int, height: int, border_px: int) -> float:
    """The width of the image inside the card the renderer draws for this aspect (5.3:
    min(980, 650 x aspect) wide, border included), read from the render constants."""
    # `render` imports this package for the manifest; the constants are read at call time.
    from shortsmith import render  # noqa: PLC0415

    return min(render.CARD_MAX_W, render.CARD_BASE_H * width / height) - 2 * border_px

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


def reject_size(width: int, height: int, border_px: int = 0) -> str | None:
    """Why the dimensions fail the 5.2 hard rejects, or None: aspect past 3:1, or too
    small to fill the card slot (053) the style draws with `border_px`. A reported 0
    (a source that does not say) passes here and is caught on the downloaded file."""
    if width <= 0 or height <= 0:
        return None
    if max(width, height) / min(width, height) > MAX_ASPECT + EPS:
        return f"aspect {max(width, height) / min(width, height):.2f}:1 > {MAX_ASPECT:g}:1"
    slot_w = card_slot_width(width, height, border_px)
    if MAX_UPSCALE * width + EPS < slot_w:
        return f"{width}x{height} px cannot fill a {slot_w:.0f} px wide card at <= {MAX_UPSCALE:g}x"
    return None


def _stock_host(url: str) -> str | None:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return None
    for stock in STOCK_HOSTS:
        if host == stock or host.endswith("." + stock):
            return stock
    return None


def reject_host(candidate: Candidate) -> str | None:
    """Why the candidate is a stock preview (053 rule 3), or None: its image host or
    its page host is one of `STOCK_HOSTS`."""
    stock = _stock_host(candidate.url) or _stock_host(candidate.page_url)
    return f"stock preview host {stock}" if stock else None


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

    def __init__(self) -> None:
        # 053 rule 5: what the source has to say about its last searches (a refused
        # answer, an empty one), one line each, drained into the job log by the step.
        self.notes: list[str] = []

    @abstractmethod
    def search(self, query: str, n: int) -> list[Candidate]: ...

    @abstractmethod
    def fetch(self, candidate: Candidate, dest: Path) -> Path: ...

    def thumbnail(self, candidate: Candidate) -> bytes | None:
        return None

    def note(self, line: str) -> None:
        self.notes.append(line)

    def drain(self) -> list[str]:
        """The notes since the last drain, which are then forgotten."""
        lines, self.notes = list(self.notes), []
        return lines


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
        super().__init__()
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
