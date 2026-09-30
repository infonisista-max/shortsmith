"""Moving footage: the free stock video sources a `clip` beat draws from (ticket 058;
decisions 4.1 and 5.1 as amended, 5.2, 5.4, 13.1).

A `clip` is a full-screen moving shot, always muted, drawn where a `photo` is drawn.
Its sources are Pexels video, then Pixabay video (`CLIP_ORDER`), on the same free keys
the image adapters use; each is a `ClipSource`, an `ImageSource` whose candidates are
`ClipCandidate`s carrying the video's `duration_s`, its preview image (`thumb_url`, what
the relevance judge looks at: 5.2 on the same 0-3 scale) and every `files` variant the
site serves. The asset step picks the file with `choose_file`: the smallest that covers
1080x1920 at no more than the style's `broll.full_bleed_max_upscale` (a 1920x1080
landscape at 1.78x is accepted, a 1280x720 at 2.67x is not) and weighs no more than
`CLIP_MAX_BYTES`; portrait files rank first among equals. The file is downloaded into the
job's asset folder (never hotlinked at render time, never committed) and probed with
ffprobe, the one size and length a source cannot misreport.

`HttpClipSource` is the shared HTTP half: the search template notes every search's
source, status and hit count (053 rule 5, extended by 058), and `fetch` streams the
video to disk under the size cap, refusing a body that is not a video. Pixabay wants its
key as a query parameter, so `PixabayClipSource.scrub` blanks the key out of every line
the adapter or the step logs (058 (8): the key never appears in a log line or a rights
row). `FakeClipSource` (12.1) writes a synthetic `testsrc2` clip with a tone track - the
tone proves the master carries no clip audio - behind fake URLs, with the same "nothing
found" modes as the fake image source.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC
from collections.abc import Iterable, Mapping, Sequence
from io import BytesIO
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydantic import SecretStr

from shortsmith.assets.base import ImageSource, SourceError, covers_frame, reject_host
from shortsmith.assets.http import TIMEOUT_S, HttpImageSource, field, items, number, text
from shortsmith.contracts import Candidate, ClipOrigin, StrictModel
from shortsmith.ffmpeg import FFMPEG, run

# 058 (3): the clip sources in order; both need the free key the image adapter uses.
CLIP_ORDER: tuple[ClipOrigin, ...] = ("pexels", "pixabay")
# 058 (3): the downloaded file is the smallest that meets the cover bar, capped here.
CLIP_MAX_BYTES = 80 * 1024 * 1024
# 058 (8): the credit line names the site the way it asks to be named.
SITE_NAMES: Mapping[str, str] = {"pexels": "Pexels", "pixabay": "Pixabay"}
# The names the step's cache and log lines use for the video sources, so a clip search
# never shares a cache folder with the image search of the same query.
SOURCE_NAMES: Mapping[str, str] = {"pexels": "pexels video", "pixabay": "pixabay video"}

VIDEO_TYPES = frozenset({"video/mp4", "video/quicktime", "video/webm", "video/x-m4v"})
_SUFFIX: Mapping[str, str] = {
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm", "video/x-m4v": ".m4v",
}  # fmt: skip
CHUNK = 1 << 16
EPS = 1e-9
# 102: the clip file choice prefers a file at least the composition's width.
FULL_WIDTH_PX = 1080
# 102: the motion measure's frame size - small grey frames, enough to see movement.
MOTION_W, MOTION_H = 64, 114


class ClipFile(StrictModel):
    """One file variant a video site serves: its URL, pixel size, weight when the site
    says it (0 otherwise) and the site's own quality label."""

    url: str
    width: int
    height: int
    size_bytes: int = 0
    quality: str = ""


class ClipCandidate(Candidate):
    """A video search hit: a `Candidate` (its `url`, `width` and `height` are the
    largest file's until `choose_file` picks) with every file variant in `files`."""

    files: list[ClipFile] = []


def video_media_type(body: bytes) -> str | None:
    """The video type `body`'s first bytes say it is, or None: an ISO base media file
    (mp4, mov, m4v) carries `ftyp` at byte 4; WebM / Matroska opens with the EBML magic."""
    if len(body) >= 8 and body[4:8] == b"ftyp":
        return "video/mp4"
    if body[:4] == b"\x1aE\xdf\xa3":
        return "video/webm"
    return None


def is_portrait(candidate: Candidate) -> bool:
    return candidate.height >= candidate.width


def choose_file(
    candidate: ClipCandidate, *, max_upscale: float, max_bytes: int = CLIP_MAX_BYTES
) -> Candidate | None:
    """The file the step downloads (058 (3), 102): among the variants whose 9:16 crop
    covers 1080x1920 at no more than `max_upscale` and that weigh at most `max_bytes`,
    the smallest at least `FULL_WIDTH_PX` wide (a file of unknown weight sorts after every
    known one, then by pixel area); when none is that wide, the largest (run05 b18 took
    Pexels' 540x960, a 2x upscale, beside a 1080x1920). None when no variant meets the
    bar. The result is a plain `Candidate` at that file's URL and size, carrying the
    hit's page, preview, author, licence and duration."""
    fits = [
        f
        for f in candidate.files
        if f.width > 0
        and f.height > 0
        and covers_frame(f.width, f.height, max_upscale)
        and f.size_bytes <= max_bytes
    ]
    if not fits:
        return None
    wide = [f for f in fits if f.width >= FULL_WIDTH_PX]
    if wide:  # 102: never a soft upscale when a full-width file is served
        best = min(wide, key=lambda f: (f.size_bytes == 0, f.size_bytes, f.width * f.height))
    else:
        best = max(fits, key=lambda f: (f.width * f.height, -f.size_bytes))
    return Candidate(
        url=best.url,
        page_url=candidate.page_url,
        thumb_url=candidate.thumb_url,
        width=best.width,
        height=best.height,
        author=candidate.author,
        licence=candidate.licence,
        duration_s=candidate.duration_s,
    )


def motion_profile(path: Path, *, fps: float) -> list[float]:
    """102: how much the clip moves, measured locally with ffmpeg: frames sampled `fps`
    times a second (the style's `broll.motion.clip.motion_fps`), scaled to small grey
    frames; entry i is the mean absolute difference (0-1) between sample i and i+1, the
    movement over the i-th step (seconds i/fps to (i+1)/fps). Empty when the file gives
    fewer than two samples."""
    proc = run([
        FFMPEG, "-v", "error", "-i", str(path), "-an", "-vf",
        f"fps={fps:g},scale={MOTION_W}:{MOTION_H},format=gray", "-f", "rawvideo", "-",
    ])  # fmt: skip
    size = MOTION_W * MOTION_H
    data = np.frombuffer(proc.stdout, dtype=np.uint8)
    count = data.size // size
    if count < 2:
        return []
    frames = data[: count * size].reshape(count, size).astype(np.int16)
    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=1) / 255.0
    return [round(float(d), 5) for d in diffs]


def best_window(
    profile: Sequence[float], *, fps: float, need_s: float, duration_s: float
) -> tuple[float, float]:
    """102: (start second, mean movement) of the clip's most moving `need_s` stretch
    that still ends inside the file: the window of `need_s * fps` steps with the highest
    mean, the earliest on a tie. A window longer than the measure starts at 0 and scores
    the whole profile; an empty profile is (0, 0)."""
    if not profile:
        return 0.0, 0.0
    steps = max(1, round(need_s * fps))
    if steps >= len(profile):
        return 0.0, round(sum(profile) / len(profile), 5)
    last = min(len(profile) - steps, math.floor((duration_s - need_s) * fps + EPS))
    best, best_at = -1.0, 0
    for at in range(max(last, 0) + 1):
        mean = sum(profile[at : at + steps]) / steps
        if mean > best + EPS:
            best, best_at = mean, at
    return round(best_at / fps, 3), round(best, 5)


def reject_clip(candidate: ClipCandidate, *, max_upscale: float) -> str | None:
    """Why no file of the hit can be shown (058 (3)), or None: the stock-host rule
    (053 rule 3) and the cover bar with the weight cap."""
    why = reject_host(candidate)
    if why is not None:
        return why
    if choose_file(candidate, max_upscale=max_upscale) is not None:
        return None
    sizes = ", ".join(f"{f.width}x{f.height}" for f in candidate.files) or "no files"
    return (
        f"no file ({sizes}) covers 1080x1920 at <= {max_upscale:g}x under "
        f"{CLIP_MAX_BYTES // 1024 // 1024} MB"
    )


class ClipSource(ImageSource, ABC):
    """A stock video source: an `ImageSource` whose `search` returns `ClipCandidate`s.
    `scrub` removes the source's secret from a log line (Pixabay's key rides the URL)."""

    origin: ClipOrigin  # pyright: ignore[reportIncompatibleVariableOverride]

    @property
    def name(self) -> str:
        return SOURCE_NAMES[self.origin]

    def scrub(self, line: str) -> str:
        return line


def _float(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


class HttpClipSource(HttpImageSource, ClipSource):
    """The shared HTTP half of a real clip source: the noted search and the streamed,
    size-capped, type-checked video download."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
        max_bytes: int = CLIP_MAX_BYTES,
    ) -> None:
        super().__init__(client=client, timeout_s=timeout_s, max_bytes=max_bytes)

    def search(self, query: str, n: int) -> list[Candidate]:
        """058 (5): every search says which source answered what for which query and
        how many hits it gave, whether or not it found anything."""
        self.searches += 1
        self._status = None
        candidates = self._search(query, n)
        if self._status is not None:
            self.note(
                f"{self.name}: {query!r} answered {self._status} with {len(candidates)} "
                f"candidate{'s' if len(candidates) != 1 else ''}"
            )
        return candidates

    def note(self, line: str) -> None:
        super().note(self.scrub(line))

    def fetch(self, candidate: Candidate, dest: Path) -> Path:
        """Stream the chosen file to `dest` with the video suffix its bytes say, refusing
        a body over `max_bytes` or one that is not a video (a `SourceError`: the step
        drops the candidate and takes the next, 5.2)."""
        client = self._client
        try:
            if client is not None:
                return self._stream(client, candidate, dest)
            with httpx.Client(timeout=self._timeout_s, follow_redirects=True) as owned:
                return self._stream(owned, candidate, dest)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise SourceError(f"{candidate.url} could not be downloaded: {exc}") from None

    def _stream(self, client: httpx.Client, candidate: Candidate, dest: Path) -> Path:
        with client.stream("GET", candidate.url, headers=dict(self.headers)) as response:
            response.raise_for_status()
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > self._max_bytes:
                raise SourceError(
                    f"{candidate.url} is {int(declared) / 1024 / 1024:.1f} MB, "
                    f"over the {self._max_bytes // 1024 // 1024} MB limit"
                )
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type and content_type not in VIDEO_TYPES and not content_type.startswith(
                "application/octet-stream"
            ):
                raise SourceError(
                    f"{candidate.url} rejected: content-type {content_type} is not a video"
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp = dest.with_suffix(".part")
            size = 0
            head = b""
            with temp.open("wb") as handle:
                for chunk in response.iter_bytes(CHUNK):
                    size += len(chunk)
                    if size > self._max_bytes:
                        handle.close()
                        temp.unlink(missing_ok=True)
                        raise SourceError(
                            f"{candidate.url} rejected: over {self._max_bytes // 1024 // 1024} MB"
                        )
                    if len(head) < 12:
                        head += chunk[: 12 - len(head)]
                    handle.write(chunk)
        kind = video_media_type(head)
        if kind is None:
            temp.unlink(missing_ok=True)
            raise SourceError(f"{candidate.url} rejected: the body is not a video")
        path = dest.with_suffix(_SUFFIX.get(content_type, _SUFFIX[kind]))
        path.unlink(missing_ok=True)
        temp.rename(path)
        return path


# --- Pexels video (058 (3)) -------------------------------------------------------------------

PEXELS_API_URL = "https://api.pexels.com/v1/videos/search"
PEXELS_LICENCE = "Pexels License"


def _area(f: ClipFile) -> int:
    return f.width * f.height


class PexelsClipSource(HttpClipSource):
    """`GET /v1/videos/search` with the key in the `Authorization` header (as the image
    adapter sends it); each video maps to a `ClipCandidate` with the page URL, the
    preview `image`, the `duration`, the `user`'s name and every `video_files` entry."""

    origin = "pexels"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
        max_bytes: int = CLIP_MAX_BYTES,
    ) -> None:
        super().__init__(client=client, timeout_s=timeout_s, max_bytes=max_bytes)
        self._api_key = api_key
        self.headers = {"Authorization": api_key.get_secret_value()}

    def _search(self, query: str, n: int) -> list[Candidate]:
        body = self._json(PEXELS_API_URL, {"query": query, "per_page": str(n)}, query=query)
        if body is None:
            return []
        candidates: list[Candidate] = []
        for video in items(body, "videos"):
            files = [
                ClipFile(
                    url=text(field(f, "link")), width=number(field(f, "width")),
                    height=number(field(f, "height")), size_bytes=number(field(f, "size")),
                    quality=text(field(f, "quality")),
                )  # fmt: skip
                for f in items(video, "video_files")
                if text(field(f, "link"))
            ]
            if not files:
                continue
            largest = max(files, key=_area)
            candidates.append(
                ClipCandidate(
                    url=largest.url,
                    page_url=text(field(video, "url")),
                    thumb_url=text(field(video, "image")),
                    width=largest.width,
                    height=largest.height,
                    author=text(field(field(video, "user"), "name")) or None,
                    licence=PEXELS_LICENCE,
                    duration_s=_float(field(video, "duration")),
                    files=files,
                )
            )
            if len(candidates) >= n:
                break
        return candidates


# --- Pixabay video (058 (3)) ------------------------------------------------------------------

PIXABAY_API_URL = "https://pixabay.com/api/videos/"
PIXABAY_LICENCE = "Pixabay Content License"
PIXABAY_MIN_PER_PAGE = 3  # the API refuses a smaller page than this
PIXABAY_SIZES = ("large", "medium", "small", "tiny")
# 058 (3): `film` unless the beat asks for animation in so many words.
ANIMATION_WORDS = re.compile(r"\b(animation|animated|cartoon|motion graphics)\b", re.IGNORECASE)


def video_type(query: str) -> str:
    return "animation" if ANIMATION_WORDS.search(query) else "film"


class PixabayClipSource(HttpClipSource):
    """`GET /api/videos/` with the key as a query parameter (the API takes it no other
    way), so every line this adapter notes and every line the step logs about its
    candidates passes through `scrub` (058 (8)). Each hit maps to a `ClipCandidate` from
    its `videos.large/medium/small/tiny` variants, the `duration`, the large variant's
    `thumbnail` and the `user`."""

    origin = "pixabay"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_S,
        max_bytes: int = CLIP_MAX_BYTES,
    ) -> None:
        super().__init__(client=client, timeout_s=timeout_s, max_bytes=max_bytes)
        self._api_key = api_key

    def scrub(self, line: str) -> str:
        secret = self._api_key.get_secret_value()
        return line.replace(secret, "***") if secret else line

    def _search(self, query: str, n: int) -> list[Candidate]:
        params = {
            "key": self._api_key.get_secret_value(),
            "q": query,
            "per_page": str(max(n, PIXABAY_MIN_PER_PAGE)),
            "video_type": video_type(query),
            "safesearch": "true",
        }
        body = self._json(PIXABAY_API_URL, params, query=query)
        if body is None:
            return []
        candidates: list[Candidate] = []
        for hit in items(body, "hits"):
            videos = field(hit, "videos")
            files: list[ClipFile] = []
            thumb = ""
            for name in PIXABAY_SIZES:
                variant = field(videos, name)
                url = text(field(variant, "url"))
                if not url:
                    continue
                files.append(
                    ClipFile(
                        url=url, width=number(field(variant, "width")),
                        height=number(field(variant, "height")),
                        size_bytes=number(field(variant, "size")), quality=name,
                    )  # fmt: skip
                )
                thumb = thumb or text(field(variant, "thumbnail"))
            if not files:
                continue
            largest = max(files, key=_area)
            candidates.append(
                ClipCandidate(
                    url=largest.url,
                    page_url=text(field(hit, "pageURL")),
                    thumb_url=thumb,
                    width=largest.width,
                    height=largest.height,
                    author=text(field(hit, "user")) or None,
                    licence=PIXABAY_LICENCE,
                    duration_s=_float(field(hit, "duration")),
                    files=files,
                )
            )
            if len(candidates) >= n:
                break
        return candidates


# --- the fake (12.1) ----------------------------------------------------------------------------


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "x"


def make_test_clip(
    path: Path, *, width: int, height: int, duration_s: float, mark: str = "0x000000",
    still_s: float = 0.0,
) -> Path:  # fmt: skip
    """A synthetic moving clip: ffmpeg's `testsrc2` pattern (it moves everywhere in the
    frame) with a 440 Hz tone track, so a render that carried the clip's sound would be
    heard, and a corner block in the `mark` colour so two clips of the same size are two
    files. 102: the first `still_s` seconds hold the first frame (the whole clip when it is
    at least `duration_s`), for the motion check. H.264 at `ultrafast`: about half a
    second to write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    block = f"drawbox=x=0:y=0:w={max(2, width // 6)}:h={max(2, height // 12)}:color={mark}:t=fill"
    if still_s > 0:
        block = f"loop=loop={round(min(still_s, duration_s) * 30)}:size=1:start=0,{block}"
    run(
        [
            FFMPEG, "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=s={width}x{height}:r=30:d={duration_s:g}",
            "-f", "lavfi", "-i",
            f"aevalsrc=exprs='0.5*sin(2*PI*440*t)':s=48000:c=mono:d={duration_s:g}",
            "-map", "0:v", "-map", "1:a", "-t", f"{duration_s:g}", "-vf", block,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(path),
        ],  # fmt: skip
    )
    return path


class FakeClipSource(ClipSource):
    """Synthetic clips behind `https://fake.invalid/<origin>-video/` URLs: `size` and
    `duration_s` (or per-query `sizes` / `durations`) describe every hit; `nothing_found`
    and `nothing_for` are the empty modes. 102: the hits numbered in `still` (1-based)
    never move, and every clip holds its first frame for `still_s` seconds. `searches`
    and `fetches` count the calls."""

    def __init__(
        self,
        origin: ClipOrigin,
        *,
        size: tuple[int, int] = (1080, 1920),
        duration_s: float = 3.0,
        sizes: Mapping[str, tuple[int, int]] | None = None,
        durations: Mapping[str, float] | None = None,
        nothing_for: Iterable[str] = (),
        nothing_found: bool = False,
        still: Iterable[int] = (),
        still_s: float = 0.0,
    ) -> None:
        super().__init__()
        self.origin = origin
        self.still = frozenset(still)
        self.still_s = still_s
        self.size = size
        self.duration_s = duration_s
        self.sizes = dict(sizes or {})
        self.durations = dict(durations or {})
        self.nothing_for = frozenset(nothing_for)
        self.nothing_found = nothing_found
        self.searches = 0
        self.fetches = 0

    def search(self, query: str, n: int) -> list[Candidate]:
        self.searches += 1
        if self.nothing_found or query in self.nothing_for:
            self.note(f"{self.name}: {query!r} answered 200 with 0 candidates")
            return []
        width, height = self.sizes.get(query, self.size)
        duration = self.durations.get(query, self.duration_s)
        base = f"https://fake.invalid/{self.origin}-video/{_slug(query)}"
        licence = PEXELS_LICENCE if self.origin == "pexels" else PIXABAY_LICENCE
        found: list[Candidate] = [
            ClipCandidate(
                url=f"{base}/{i}.mp4",
                page_url=f"{base}/{i}",
                thumb_url=f"{base}/{i}-thumb.png",
                width=width,
                height=height,
                author=f"fake {self.origin} video",
                licence=licence,
                duration_s=duration,
                files=[ClipFile(url=f"{base}/{i}.mp4", width=width, height=height,
                                size_bytes=4 * 1024 * 1024, quality="hd")],  # fmt: skip
            )
            for i in range(1, n + 1)
        ]
        self.note(f"{self.name}: {query!r} answered 200 with {len(found)} candidates")
        return found

    def _thumb(self, candidate: Candidate) -> Image.Image:
        digest = hashlib.sha256(candidate.url.encode("utf-8")).digest()
        image = Image.new("RGB", (160, 100), tuple(digest[:3]))
        label = candidate.url.removeprefix("https://fake.invalid/")
        font = ImageFont.load_default(size=12)
        ImageDraw.Draw(image).text((4, 4), label, fill=(255, 255, 255), font=font)
        return image

    def fetch(self, candidate: Candidate, dest: Path) -> Path:
        self.fetches += 1
        digest = hashlib.sha256(candidate.url.encode("utf-8")).hexdigest()
        duration = candidate.duration_s or self.duration_s
        number = candidate.url.rsplit("/", 1)[-1].removesuffix(".mp4")
        still_s = duration if number.isdigit() and int(number) in self.still else self.still_s
        return make_test_clip(
            dest.with_suffix(".mp4"), width=candidate.width, height=candidate.height,
            duration_s=duration, mark=f"0x{digest[:6]}", still_s=still_s,
        )  # fmt: skip

    def thumbnail(self, candidate: Candidate) -> bytes | None:
        buffer = BytesIO()
        self._thumb(candidate).save(buffer, format="PNG")
        return buffer.getvalue()
