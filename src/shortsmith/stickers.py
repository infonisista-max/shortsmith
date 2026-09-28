"""Stickers: 3D emoji pops from Microsoft Fluent Emoji (ticket 062; 4.1, 5.1 and 9.2 as
amended).

**Catalogue.** `assets/stickers/catalog.yaml` is committed: 40-60 curated emoji, each a
`name` (the Fluent folder name, what the planner may write), its `path` under the
repository's `assets/` folder and its intent `tags` (idea, danger, death, shock, money,
...). `load_catalogue` validates it when the app is built: unique names, non-empty tags
and every path the 3D pattern (`<Name>/3D/<name_snake>_3d.png`, or one folder deeper
under `Default/` for an emoji with skin tones, `..._3d_default.png`); a broken row
stops the app naming it. The planner is told the tags and each tag's names, and picks
by tag, never a file name (`StickerCatalogue.pick`).

**Fetched at job time, never at render time.** The asset step (`StickerShelf.source`)
downloads a sticker's PNG on first use into the cache `<data dir>/cache/stickers/`
(git-ignored with the rest of the data dir; the ticket named `assets/stickers/fetched/`,
but the session could not edit `.gitignore`, so the cache sits where an ignore rule
already covers it) and reuses it after that, then copies it into the job folder
so the renderer reads only the job's own files. One `StickerRecord` per sticker shown;
its rights row and credits line ("Fluent Emoji by Microsoft, MIT License") are derived
from it by `rights`. A failed fetch drops that sticker, logs why, and the job goes on.

`FakeStickerFetcher` draws a PNG with Pillow for the tests and the smoke; the live
`HttpStickerFetcher` is one GET on raw.githubusercontent.com (free, no key).
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import cast
from urllib.parse import quote

import httpx
import yaml
from PIL import Image, ImageDraw
from pydantic import ValidationError

from shortsmith.contracts import PicturePlan, StickerRecord, StrictModel

REPO_ROOT = Path(__file__).resolve().parents[2]
STICKERS_DIR = REPO_ROOT / "assets" / "stickers"
CATALOGUE_PATH = STICKERS_DIR / "catalog.yaml"
# 062 (2): the fetched PNGs, under the (git-ignored) data dir; a job copies what it shows
# into its own folder.
CACHE_SUBDIR = Path("cache") / "stickers"
JOB_DIR = "assets/stickers"  # under the job folder
BASE_URL = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/"
PAGE_URL = "https://github.com/microsoft/fluentui-emoji"
AUTHOR = "Microsoft"
LICENCE = "MIT License"
CREDIT = "Fluent Emoji by Microsoft, MIT License"
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_S = 30.0
USER_AGENT = "shortsmith (https://github.com/infonisista-max/shortsmith)"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# `<Folder>/3D/<snake>_3d.png`, or `<Folder>/Default/3D/<snake>_3d_default.png`.
PATH_PATTERN = re.compile(r"^(?P<folder>[^/]+)/(?P<tone>Default/)?3D/(?P<stem>[a-z0-9_]+)\.png$")
FAKE_SIZE_PX = 256


class StickerError(RuntimeError):
    """The catalogue is broken, or a sticker could not be fetched."""


class StickerEntry(StrictModel):
    name: str
    path: str
    tags: list[str]

    @property
    def url(self) -> str:
        return BASE_URL + quote(self.path)

    @property
    def file_name(self) -> str:
        return self.path.rsplit("/", 1)[-1]


def _snake(folder: str) -> str:
    return folder.lower().replace(" ", "_").replace("-", "_")


def path_problem(entry: StickerEntry) -> str | None:
    """Why `entry.path` is not the Fluent 3D pattern for its own folder, or None."""
    match = PATH_PATTERN.match(entry.path)
    if match is None:
        return f"path {entry.path!r} is not <Name>/3D/<name>_3d.png"
    folder, toned = match["folder"], match["tone"] is not None
    stem = f"{_snake(folder)}_3d" + ("_default" if toned else "")
    if match["stem"] != stem:
        return f"path {entry.path!r} is not the 3D file of {folder!r} ({stem}.png)"
    return None


@dataclass(frozen=True)
class StickerCatalogue:
    entries: tuple[StickerEntry, ...] = ()

    def tags(self) -> list[str]:
        """Every intent tag, sorted: what the planner may ask for."""
        return sorted({t for e in self.entries for t in e.tags})

    def with_tag(self, tag: str) -> list[StickerEntry]:
        return [e for e in self.entries if tag in e.tags]

    def entry(self, name: str) -> StickerEntry | None:
        return next((e for e in self.entries if e.name == name), None)

    def pick(self, intent: str, name: str = "") -> StickerEntry | None:
        """The row the planner asked for: `name` when that row carries `intent`, the
        tag's first row when `name` is empty; None when the tag or the row is not
        there."""
        rows = self.with_tag(intent)
        if not name:
            return rows[0] if rows else None
        return next((e for e in rows if e.name == name), None)


def parse_catalogue(text: str, *, name: str) -> StickerCatalogue:
    loaded: object = yaml.safe_load(text)
    found = cast(dict[str, object], loaded).get("entries") if isinstance(loaded, dict) else None
    if not isinstance(found, list):
        raise StickerError(f"{name}: the sticker catalogue is not a mapping with an `entries` list")
    rows = cast(list[object], found)
    entries: list[StickerEntry] = []
    seen: set[str] = set()
    for i, raw in enumerate(rows, start=1):
        try:
            entry = StickerEntry.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            raise StickerError(f"{name}: row {i}: {problems}") from None
        label = f"{name}: row {i} {entry.name!r}"
        if entry.name in seen:
            raise StickerError(f"{label}: the name is listed twice")
        if not [t for t in entry.tags if t.strip()]:
            raise StickerError(f"{label}: no intent tag")
        problem = path_problem(entry)
        if problem is not None:
            raise StickerError(f"{label}: {problem} (the Fluent Emoji 3D pattern)")
        seen.add(entry.name)
        entries.append(entry)
    return StickerCatalogue(entries=tuple(entries))


def load_catalogue(path: Path = CATALOGUE_PATH) -> StickerCatalogue:
    return parse_catalogue(path.read_text(encoding="utf-8"), name=path.name)


@cache
def shipped() -> StickerCatalogue:
    """The committed catalogue, loaded once per process (the grammar and the prompt
    read it; the app validates it at startup)."""
    return load_catalogue()


# --- fetching ------------------------------------------------------------------------------


class StickerFetcher:
    """One PNG by URL; raises `StickerError` when it cannot."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str) -> bytes:
        raise NotImplementedError


class HttpStickerFetcher(StickerFetcher):
    """A GET on raw.githubusercontent.com (free, no key), capped at `MAX_BYTES`."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        super().__init__()
        self._client = client

    def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        client = self._client or httpx.Client(
            timeout=TIMEOUT_S, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            raise StickerError(f"GET {url}: {type(exc).__name__}: {exc}") from None
        finally:
            if self._client is None:
                client.close()
        if response.status_code != 200:
            raise StickerError(f"GET {url}: HTTP {response.status_code}")
        if len(response.content) > MAX_BYTES:
            raise StickerError(f"GET {url}: {len(response.content)} bytes, over {MAX_BYTES}")
        return response.content


class FakeStickerFetcher(StickerFetcher):
    """12.1: a `FAKE_SIZE_PX` square PNG with a yellow disc on a transparent ground,
    drawn by Pillow; `body` replaces it (a refusal test)."""

    def __init__(self, *, body: bytes | None = None) -> None:
        super().__init__()
        self._body = body

    def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        if self._body is not None:
            return self._body
        image = Image.new("RGBA", (FAKE_SIZE_PX, FAKE_SIZE_PX), (0, 0, 0, 0))
        pad = FAKE_SIZE_PX // 10
        ImageDraw.Draw(image).ellipse(
            (pad, pad, FAKE_SIZE_PX - pad, FAKE_SIZE_PX - pad), fill=(255, 214, 10, 255)
        )
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()


@dataclass
class StickerShelf:
    """The catalogue, the fetcher and the cache folder the asset step sources stickers
    from."""

    catalogue: StickerCatalogue
    fetcher: StickerFetcher
    cache_dir: Path

    def ensure(self, entry: StickerEntry) -> Path:
        """The cached PNG of `entry`, fetched on first use; a body that is not a PNG is
        refused before anything is written."""
        path = self.cache_dir / entry.file_name
        if path.is_file():
            return path
        body = self.fetcher.fetch(entry.url)
        if not body.startswith(PNG_MAGIC):
            raise StickerError(f"GET {entry.url}: the body is not a PNG ({len(body)} bytes)")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        partial.write_bytes(body)
        partial.replace(path)
        return path

    def source(
        self,
        plan: PicturePlan,
        *,
        job_dir: Path,
        log: Callable[[str], None],
        fetched_at: str,
    ) -> list[StickerRecord]:
        """One record per catalogue row the plan's stickers name, in plan order, each
        PNG copied into `<job>/assets/stickers/`. A row the catalogue lacks or a fetch
        that fails drops that sticker with one job.log line; the step goes on."""
        records: dict[str, StickerRecord] = {}
        refused: set[str] = set()
        for beat in plan.beats:
            for sticker in beat.stickers:
                name = sticker.name
                if name in records or name in refused:
                    continue
                entry = self.catalogue.entry(name)
                if entry is None:
                    refused.add(name)
                    log(f"sticker: {beat.id}: {name!r} dropped, not in the sticker catalogue (062)")
                    continue
                try:
                    cached = self.ensure(entry)
                except StickerError as exc:
                    refused.add(name)
                    log(f"sticker: {beat.id}: {name!r} dropped, the fetch failed: {exc} (062)")
                    continue
                records[name] = _copied(entry, cached, job_dir=job_dir, fetched_at=fetched_at)
        return list(records.values())


def _copied(entry: StickerEntry, cached: Path, *, job_dir: Path, fetched_at: str) -> StickerRecord:
    folder = job_dir / JOB_DIR
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / entry.file_name
    shutil.copyfile(cached, target)
    body = target.read_bytes()
    with Image.open(io.BytesIO(body)) as image:
        width, height = image.size
    return StickerRecord(
        name=entry.name, file=f"{JOB_DIR}/{entry.file_name}", source_url=entry.url,
        sha256=hashlib.sha256(body).hexdigest(), width=width, height=height,
        fetched_at=fetched_at,
    )  # fmt: skip


def live_shelf(data_dir: Path) -> StickerShelf:
    """The configured shelf: the shipped catalogue over the live fetcher and the cache
    under the data dir."""
    return StickerShelf(
        catalogue=shipped(), fetcher=HttpStickerFetcher(), cache_dir=data_dir / CACHE_SUBDIR
    )
