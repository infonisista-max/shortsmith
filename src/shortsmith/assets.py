"""The asset step (PRD `assets`; ticket 016): one picture for every sourced beat.

`source_assets(validated, references, policy, ...)` walks the validated plan's beats
in order and decides, per beat, which asset it shows and how, recording everything in
an `AssetManifest` (`work/assets.json`):

- Sourced beats are the non-presenter beats the grammar labelled with a
  `subject_kind` (4.2); presenter, hook-card and finale beats only point at assets
  other beats source, through `manifest.aliases`.
- A planned asset id that an earlier beat already sourced is reused as planned
  (4.3). A beat naming a reference id, or whose `query` shares a significant word
  with a reference caption, takes the owner reference first (1.3, 5.1).
- `source_intent` (5.1): `reuse` always takes the nearest earlier asset; `generate`
  is honoured on `concept` beats only (the generator is tried first); `entity` beats
  always search first. `number` and `quote` beats never search or generate (4.2):
  they take a matching reference or the previous beat's asset.
- The ladder (4.4), applied here, never by the planner: every searched source in the
  configured order with `query` (rung 0), then with `query_fallback` (rung 1), then
  generation (rung 2; a no-op while `IMAGE_GEN=none`, ticket 019), then the nearest
  earlier asset of the same `subject_kind` re-dressed with a framing it has not had
  (rung 3), then the presenter PIP over the style gradient (rung 4). Rungs 3 and 4
  carry a stamp word. Never a blank beat. The manifest carries `rescued_max`, the
  style's `rescued_max_per_60s` scaled to the runtime; the gate fails above it.
- Classification by the fetched file's real dimensions (5.3): `photo` only when the
  planner asked for one, the image is portrait, at least 1080 px wide, and covers
  1080x1920 with at most a 1.5x upscale (so a 1079 px portrait is a card), and it is
  not a web image (web images are always re-dressed as cards, 5.1). Anything else is
  a `card`; a planned `photo` that became a card records `treatment_downgraded`.

Search results and fetched files are cached per job under
`work/assets/<sha256(query + source)>/` (5.6), so re-running the step (a plan retry,
a re-render) searches and fetches nothing. No relevance judge yet (017): the first
candidate wins. Every source is a fake in this ticket; real adapters come with 017
and 018.

`ImageSource` is the adapter interface; `FakeImageSource` (12.1) writes solid PNGs
at the sizes it was given, with fake URLs, and has "nothing found" modes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, get_args

from PIL import Image, ImageDraw, ImageFont
from pydantic import TypeAdapter

from shortsmith import ffmpeg
from shortsmith.contracts import (
    AssetManifest,
    AssetPolicy,
    AssetRecord,
    Beat,
    BeatAsset,
    Candidate,
    Crop,
    Generated,
    Origin,
    ReferenceRecord,
    SearchOrigin,
    Treatment,
    ValidatedPlan,
)
from shortsmith.styles import StyleSpec

MANIFEST_NAME = "assets.json"
CACHE_DIR = "assets"
DEFAULT_ORDER: tuple[SearchOrigin, ...] = get_args(SearchOrigin)
CANDIDATES = 6  # 5.2: at most six candidates per beat reach the judge
NOT_SOURCED = frozenset({"presenter_full", "presenter_pip", "hook_cards", "finale"})
REUSING_KINDS = frozenset({"number", "quote"})

# 5.3: the frame a full-bleed photo must cover and the largest upscale allowed.
FRAME_W, FRAME_H = 1080, 1920
MAX_UPSCALE = 1.5
EPS = 1e-9

# 4.4: a re-dress punches in a further step and moves the focus, so no framing repeats.
REDRESS_ZOOM_STEP = 0.15
REDRESS_FOCI: tuple[tuple[float, float], ...] = (
    (0.5, 0.5), (0.35, 0.4), (0.65, 0.6), (0.4, 0.65), (0.6, 0.35),
)  # fmt: skip

# Words too generic to tie a query to a reference caption.
_STOPWORDS = frozenset(
    [
        "the", "and", "for", "with", "from", "into", "over", "this", "that", "photo",
        "image", "picture", "archival", "shot", "view", "close", "closeup", "old", "new",
        "our", "your",
    ]
)  # fmt: skip
_WORD = re.compile(r"[^\W_]+", re.UNICODE)

Clock = Callable[[], datetime]
Planned = Literal["photo", "card", "auto"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AssetError(RuntimeError):
    """The step cannot proceed (a missing reference file, an unreadable image)."""


# --- sources (5.1, 5.2) ------------------------------------------------------------------


class ImageSource(ABC):
    """One searched source. `search` returns candidates in the source's own order;
    `fetch` downloads one to `dest` plus the file's suffix and returns the path."""

    origin: SearchOrigin

    @abstractmethod
    def search(self, query: str, n: int) -> list[Candidate]: ...

    @abstractmethod
    def fetch(self, candidate: Candidate, dest: Path) -> Path: ...


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
                width=width,
                height=height,
                author=f"fake {self.origin}",
            )
            for i in range(1, n + 1)
        ]

    def fetch(self, candidate: Candidate, dest: Path) -> Path:
        self.fetches += 1
        path = dest.with_suffix(".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(candidate.url.encode("utf-8")).digest()
        image = Image.new("RGB", (candidate.width, candidate.height), tuple(digest[:3]))
        label = candidate.url.removeprefix("https://fake.invalid/")
        font = ImageFont.load_default(size=max(16, candidate.width // 24))
        ImageDraw.Draw(image).text((24, 24), label, fill=(255, 255, 255), font=font)
        image.save(path, format="PNG")
        return path


def parse_order(text: str) -> tuple[str, ...]:
    """`ASSET_SOURCES` as a tuple of names, blanks dropped."""
    return tuple(name.strip() for name in text.split(",") if name.strip())


def source_order(order: Sequence[str], policy: AssetPolicy) -> list[str]:
    """The searched sources for `policy` (5.2): `rights_safe` removes web search."""
    return [name for name in order if not (policy == "rights_safe" and name == "web")]


# --- generation (5.5; the generator itself is ticket 019) ---------------------------------


@dataclass(frozen=True)
class GeneratedImage:
    path: Path
    generated: Generated


# A generator writes one image for the beat under the given directory, or returns None
# ("nothing generated"). None in place of the callable is `IMAGE_GEN=none`.
Generate = Callable[[Beat, Path], GeneratedImage | None]


# --- classification (5.3) -------------------------------------------------------------------


def full_bleed(width: int, height: int) -> bool:
    """Portrait, at least 1080 px wide, covering 1080x1920 within the 1.5x upscale."""
    if height <= width or width < FRAME_W:
        return False
    return max(FRAME_W / width, FRAME_H / height) <= MAX_UPSCALE + EPS


def classify(
    width: int, height: int, *, planned: Planned, origin: Origin
) -> tuple[Treatment, bool]:
    """(treatment, downgraded) for an asset of the real `width` x `height`."""
    wants_photo = planned in ("photo", "auto")
    if wants_photo and origin != "web" and full_bleed(width, height):
        return "photo", False
    return "card", planned == "photo"


def _planned(beat: Beat) -> Planned:
    return beat.kind if beat.kind in ("photo", "card") else "auto"  # pyright: ignore[reportReturnType]


# --- the cache (5.6) --------------------------------------------------------------------


def cache_key(query: str, source: str) -> str:
    return hashlib.sha256(query.encode("utf-8") + source.encode("utf-8")).hexdigest()


_CANDIDATES = TypeAdapter(list[Candidate])


@dataclass
class _Fetched:
    path: Path
    candidate: Candidate | None
    fetched_at: str
    generated: Generated | None = None


def _search_cached(
    source: ImageSource, name: str, query: str, cache: Path, clock: Clock
) -> _Fetched | None:
    """The first candidate for `query` from `source`, fetched once per job."""
    folder = cache / cache_key(query, name)
    result = folder / "result.json"
    if result.is_file():
        data = json.loads(result.read_text(encoding="utf-8"))
        if data["file"] is None:
            return None
        candidate = Candidate.model_validate(data["candidate"])
        return _Fetched(folder / data["file"], candidate, data["fetched_at"])
    folder.mkdir(parents=True, exist_ok=True)
    candidates = source.search(query, CANDIDATES)
    record: dict[str, object] = {
        "query": query,
        "source": name,
        "candidates": _CANDIDATES.dump_python(candidates, mode="json"),
        "candidate": None,
        "file": None,
        "fetched_at": None,
    }
    fetched: _Fetched | None = None
    if candidates:
        chosen = candidates[0]  # the relevance judge (017) picks among them
        path = source.fetch(chosen, folder / "image")
        fetched = _Fetched(path, chosen, clock().isoformat())
        record |= {
            "candidate": chosen.model_dump(mode="json"),
            "file": path.name,
            "fetched_at": fetched.fetched_at,
        }
    result.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return fetched


def _generate_cached(beat: Beat, generate: Generate, cache: Path, clock: Clock) -> _Fetched | None:
    folder = cache / cache_key(beat.query, "generated")
    result = folder / "result.json"
    if result.is_file():
        data = json.loads(result.read_text(encoding="utf-8"))
        if data["file"] is None:
            return None
        generated = Generated.model_validate(data["generated"])
        return _Fetched(folder / data["file"], None, data["fetched_at"], generated)
    folder.mkdir(parents=True, exist_ok=True)
    made = generate(beat, folder)
    record: dict[str, object] = {"query": beat.query, "file": None}
    fetched: _Fetched | None = None
    if made is not None:
        fetched = _Fetched(made.path, None, clock().isoformat(), made.generated)
        record |= {
            "file": made.path.relative_to(folder).as_posix(),
            "generated": made.generated.model_dump(mode="json"),
            "fetched_at": fetched.fetched_at,
        }
    result.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return fetched


# --- owner references (1.3) ---------------------------------------------------------------


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 3 and w not in _STOPWORDS}


def matching_reference(
    query: str, references: Sequence[ReferenceRecord]
) -> ReferenceRecord | None:
    """The reference whose caption shares the most significant words with `query`
    (first on a tie), or None when none shares a word."""
    wanted = _words(query)
    best: ReferenceRecord | None = None
    best_score = 0
    for ref in references:
        score = len(wanted & _words(ref.caption))
        if score > best_score:
            best, best_score = ref, score
    return best


RightsImageKind = Literal["image", "clip_frame"]


def _reference_file(
    ref: ReferenceRecord, job_dir: Path, cache: Path
) -> tuple[Path, RightsImageKind]:
    """The still for a reference: the image itself, or one frame of a clip (1.3)."""
    source = job_dir / "input" / ref.file
    if not source.is_file():
        raise AssetError(f"reference {ref.id}: input/{ref.file} is missing")
    if ref.kind == "image":
        return source, "image"
    frame = cache / f"ref-{ref.id}" / "frame.png"
    if not frame.is_file():
        frame.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg.run(
            [ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(source), "-frames:v", "1", str(frame)]
        )
    return frame, "clip_frame"


# --- the step ------------------------------------------------------------------------------


def _measure(path: Path) -> tuple[int, int, str]:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except OSError as exc:
        raise AssetError(f"{path.name} is not a readable image: {exc}") from None
    return width, height, hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path, job_dir: Path) -> str:
    return path.resolve().relative_to(job_dir.resolve()).as_posix()


def stamp_word(beat: Beat) -> str:
    """The word a rescue stamps (4.4): the beat's own stamp or label text, else the
    longest word of its query. Stamps are drawn by ticket 026."""
    if beat.event.text:
        return beat.event.text
    words = sorted(_WORD.findall(beat.query), key=len, reverse=True)
    return words[0].upper() if words else ""


def redress_crop(times: int) -> Crop:
    """The framing for the `times`-th re-dress of an asset: a further punch-in and a
    moved focus, never a framing the asset has had."""
    fx, fy = REDRESS_FOCI[times % len(REDRESS_FOCI)]
    return Crop(zoom=round(1.0 + REDRESS_ZOOM_STEP * times, 4), focus_x=fx, focus_y=fy)


def rescued_max(spec: StyleSpec, runtime_s: float) -> int:
    """`rescued_max_per_60s` scaled to the runtime, rounded up like every maximum."""
    return math.ceil(spec.broll.rescued_max_per_60s * runtime_s / 60 - EPS)


@dataclass
class _Walk:
    job_dir: Path
    cache: Path
    clock: Clock
    references: Sequence[ReferenceRecord]
    records: dict[str, AssetRecord] = field(default_factory=lambda: {})
    beats: list[BeatAsset] = field(default_factory=lambda: [])
    subjects: dict[str, str] = field(default_factory=lambda: {})  # beat id -> subject kind
    aliases: dict[str, str | None] = field(default_factory=lambda: {})
    redresses: dict[str, int] = field(default_factory=lambda: {})

    def add(self, asset_id: str, path: Path, *, origin: Origin, fetched_at: str,
            kind: Literal["image", "clip_frame"] = "image", candidate: Candidate | None = None,
            generated: Generated | None = None) -> AssetRecord:  # fmt: skip
        width, height, digest = _measure(path)
        record = AssetRecord(
            id=asset_id,
            kind=kind,
            origin=origin,
            source_url=candidate.url if candidate else "",
            page_url=candidate.page_url if candidate else "",
            licence="owner" if origin == "owner_supplied" else (
                candidate.licence if candidate else "unknown"),
            author=candidate.author if candidate else None,
            generated=generated,
            file=_rel(path, self.job_dir),
            sha256=digest,
            width=width,
            height=height,
            fetched_at=fetched_at,
        )  # fmt: skip
        self.records[asset_id] = record
        return record

    def owner(self, asset_id: str, ref: ReferenceRecord) -> AssetRecord:
        path, kind = _reference_file(ref, self.job_dir, self.cache)
        return self.add(asset_id, path, origin="owner_supplied", kind=kind,
                        fetched_at=self.clock().isoformat())  # fmt: skip

    def show(self, beat: Beat, record: AssetRecord, rung: int, *,
             redressed: bool = False) -> None:  # fmt: skip
        treatment, downgraded = classify(
            record.width, record.height, planned=_planned(beat), origin=record.origin
        )
        crop = Crop()
        if redressed:
            times = self.redresses.get(record.id, 0) + 1
            self.redresses[record.id] = times
            crop = redress_crop(times)
        self.beats.append(
            BeatAsset(
                beat_id=beat.id,
                asset_id=record.id,
                treatment=treatment,
                fallback_rung=rung,
                treatment_downgraded=downgraded,
                redressed_from=record.id if redressed else None,
                crop=crop,
                stamp=stamp_word(beat) if rung >= 3 else None,
            )
        )
        self.subjects[beat.id] = beat.subject_kind or ""
        if beat.asset_id is not None:
            self.aliases.setdefault(beat.asset_id, record.id)

    def gradient(self, beat: Beat) -> None:
        self.beats.append(
            BeatAsset(beat_id=beat.id, asset_id=None, treatment="gradient", fallback_rung=4,
                      stamp=stamp_word(beat))
        )  # fmt: skip
        self.subjects[beat.id] = beat.subject_kind or ""
        if beat.asset_id is not None:
            self.aliases.setdefault(beat.asset_id, None)

    def nearest(self, subject: str | None = None) -> AssetRecord | None:
        """The asset of the nearest earlier beat that shows one (of `subject` kind)."""
        for shown in reversed(self.beats):
            if shown.asset_id is None:
                continue
            if subject is None or self.subjects.get(shown.beat_id) == subject:
                return self.records[shown.asset_id]
        return None


def _new_id(beat: Beat) -> str:
    return beat.asset_id or f"{beat.id}-asset"


def source_assets(
    validated: ValidatedPlan,
    references: Sequence[ReferenceRecord],
    policy: AssetPolicy,
    *,
    spec: StyleSpec,
    sources: Mapping[str, ImageSource],
    order: Sequence[str] = DEFAULT_ORDER,
    job_dir: Path,
    generate: Generate | None = None,
    clock: Clock = _utc_now,
) -> AssetManifest:
    """Decide every sourced beat's asset per the rules in the module docstring."""
    picture = validated.picture
    cache = job_dir / "work" / CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    searched = [(name, sources[name]) for name in source_order(order, policy) if name in sources]
    by_id = {ref.id: ref for ref in references}
    walk = _Walk(job_dir=job_dir, cache=cache, clock=clock, references=references)

    def search(query: str) -> tuple[_Fetched, SearchOrigin] | None:
        if not query:
            return None
        for name, source in searched:
            found = _search_cached(source, name, query, cache, clock)
            if found is not None:
                return found, source.origin
        return None

    def generated(beat: Beat) -> AssetRecord | None:
        if generate is None:
            return None
        made = _generate_cached(beat, generate, cache, clock)
        if made is None:
            return None
        return walk.add(_new_id(beat), made.path, origin="generated", fetched_at=made.fetched_at,
                        generated=made.generated)  # fmt: skip

    for beat in picture.beats:
        if beat.kind in NOT_SOURCED or beat.subject_kind is None:
            continue
        planned = beat.asset_id
        if planned is not None and planned in walk.records:
            walk.show(beat, walk.records[planned], 0)
            continue
        if planned is not None and planned in by_id:
            walk.show(beat, walk.owner(planned, by_id[planned]), 0)
            continue
        ref = matching_reference(beat.query, references)
        if ref is not None:
            walk.show(beat, walk.owner(_new_id(beat), ref), 0)
            continue
        if beat.subject_kind in REUSING_KINDS or beat.source_intent == "reuse":
            previous = walk.nearest()
            if previous is not None:
                walk.show(beat, previous, 0)
                continue
            if beat.subject_kind in REUSING_KINDS:
                walk.gradient(beat)
                continue
        tried_generation = False
        if beat.subject_kind == "concept" and beat.source_intent == "generate":
            tried_generation = generate is not None
            record = generated(beat)
            if record is not None:
                walk.show(beat, record, 2)
                continue
        found = None
        for rung, query in ((0, beat.query), (1, beat.query_fallback)):
            hit = search(query)
            if hit is not None:
                found = (rung, hit)
                break
        if found is not None:
            rung, (fetched, origin) = found
            record = walk.add(
                _new_id(beat), fetched.path, origin=origin,
                fetched_at=fetched.fetched_at, candidate=fetched.candidate,
            )  # fmt: skip
            walk.show(beat, record, rung)
            continue
        record = None if tried_generation else generated(beat)
        if record is not None:
            walk.show(beat, record, 2)
            continue
        earlier = walk.nearest(beat.subject_kind)
        if earlier is not None:
            walk.show(beat, earlier, 3, redressed=True)
            continue
        walk.gradient(beat)

    runtime = picture.beats[-1].end if picture.beats else 0.0
    return AssetManifest(
        assets=list(walk.records.values()),
        beats=walk.beats,
        aliases=walk.aliases,
        runtime_s=runtime,
        rescued_max=rescued_max(spec, runtime),
    )


# --- the manifest on disk ---------------------------------------------------------------------


def manifest_path(job_dir: Path) -> Path:
    return job_dir / "work" / MANIFEST_NAME


def write_manifest(job_dir: Path, manifest: AssetManifest) -> Path:
    path = manifest_path(job_dir)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_manifest(job_dir: Path) -> AssetManifest | None:
    path = manifest_path(job_dir)
    if not path.is_file():
        return None
    return AssetManifest.model_validate_json(path.read_text(encoding="utf-8"))
