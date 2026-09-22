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
  generation (rung 2, ticket 019; a no-op while `IMAGE_GEN=none`), then the nearest
  earlier asset of the same `subject_kind` re-dressed with a framing it has not had
  (rung 3), then the presenter PIP over the style gradient (rung 4). Rungs 3 and 4
  carry a stamp word. Never a blank beat. The manifest carries `rescued_max`, the
  style's `rescued_max_per_60s` scaled to the runtime; the gate fails above it.
- Classification by the fetched file's real dimensions (5.3): `photo` only when the
  planner asked for one, the image is portrait, at least 1080 px wide, and covers
  1080x1920 with at most a 1.5x upscale (so a 1079 px portrait is a card), and it is
  not a web image (web images are always re-dressed as cards, 5.1). Anything else is
  a `card`; a planned `photo` that became a card records `treatment_downgraded`.

- Which candidate a source's hits give the beat (5.2, ticket 017): the code-only hard
  rejects drop what is too small, too wide or not an image (`base`), and the survivors
  go to the relevance judge (`judge`), which scores each 0-3. Best >= 2 wins, ties by
  the source's own order, everything under 2 means the next source and then the
  ladder. A candidate whose download is refused or rejected is dropped and the next
  accepted one is taken; the beat is never rejected for a candidate. With no judge
  configured, its call ceiling spent, or a judge that could not answer, the first
  candidate the hard rejects kept wins and the beat records `judge_skipped`.

Search results and fetched files are cached per job under
`work/assets/<sha256(query + source)>/` (5.6), so re-running the step (a plan retry,
a re-render) searches, judges and fetches nothing; judge verdicts are additionally
cached by candidate URL for the whole job, so the same candidate is never paid for
twice. Queries that were actually sent are counted by `Searching` against the style's
`search_max_queries`; every source shipped so far is free, so that allowance is a
note, never a skipped beat (11.3).

`base` holds the `ImageSource` interface, the hard rejects and `FakeImageSource`
(12.1), which writes solid PNGs at the sizes it was given behind fake URLs and has
"nothing found" modes; `http` the HTTP half every real adapter shares; `web` the
scraped image search (017); `commons`, `openverse`, `pexels` and `pixabay` the free
libraries of the 5.1 order (018); `judge` the relevance judge; `generate` rung 2 -
the two code-built prompt templates, the Gemini REST adapter, the fake, the style's
`gen_max_per_short` ceiling and the generated-file cache (019).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, get_args

from PIL import Image
from pydantic import TypeAdapter

from shortsmith import ffmpeg, jobs, rights
from shortsmith.assets.base import (
    BOOKENDS,
    MAX_ASPECT,
    MAX_BYTES,
    MIN_SHORT_SIDE,
    FakeImageSource,
    ImageSource,
    SourceError,
    media_type,
    parse_order,
    reject_body,
    reject_size,
    source_order,
)
from shortsmith.assets.commons import CommonsImageSource
from shortsmith.assets.generate import (
    FakeImageGenerator,
    GeminiImageGenerator,
    GeneratedAsset,
    Generating,
    GeneratorError,
    ImageGenerator,
)
from shortsmith.assets.judge import (
    FakeRelevanceJudge,
    Judging,
    RelevanceJudge,
    Thumb,
    Verdict,
    VisionJudge,
)
from shortsmith.assets.openverse import OpenverseImageSource
from shortsmith.assets.pexels import PexelsImageSource
from shortsmith.assets.pixabay import PixabayImageSource
from shortsmith.assets.web import WebImageSource
from shortsmith.config import Settings
from shortsmith.contracts import (
    AssetManifest,
    AssetPolicy,
    AssetRecord,
    Beat,
    BeatAsset,
    Candidate,
    Crop,
    Generated,
    JudgeVerdict,
    Origin,
    ReferenceRecord,
    SearchOrigin,
    Treatment,
    ValidatedPlan,
)
from shortsmith.jobs import Job
from shortsmith.ledger import Ledger
from shortsmith.styles import StyleSpec

__all__ = [
    "BOOKENDS",
    "MAX_ASPECT",
    "MAX_BYTES",
    "MIN_SHORT_SIDE",
    "AssetError",
    "CommonsImageSource",
    "FakeImageGenerator",
    "FakeImageSource",
    "FakeRelevanceJudge",
    "GeminiImageGenerator",
    "GeneratedAsset",
    "Generating",
    "GeneratorError",
    "ImageGenerator",
    "ImageSource",
    "Judging",
    "OpenverseImageSource",
    "PexelsImageSource",
    "PixabayImageSource",
    "RelevanceJudge",
    "Searching",
    "SourceError",
    "Sourcing",
    "Thumb",
    "Verdict",
    "VisionJudge",
    "WebImageSource",
    "media_type",
    "parse_order",
    "reject_body",
    "reject_size",
    "source_assets",
    "source_order",
]

MANIFEST_NAME = "assets.json"
CACHE_DIR = "assets"
DEFAULT_ORDER: tuple[SearchOrigin, ...] = get_args(SearchOrigin)
CANDIDATES = 6  # 5.2: at most six candidates per beat reach the judge
NOT_SOURCED = frozenset({"presenter_full", "presenter_pip", "hook_cards", "finale"})
# 018: the sources that want a free key, and the `.env` name that carries it.
KEYED: Mapping[str, str] = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}
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
    verdict: JudgeVerdict | None = None
    judge_skipped: bool = False


@dataclass(frozen=True)
class _Ranked:
    """One surviving candidate with the judge's verdict on it, if it was judged."""

    candidate: Candidate
    verdict: Verdict | None = None


@dataclass
class Searching:
    """The queries this job actually sent, against the style's `search_max_queries`
    (5.6). A query answered from `work/assets/` is not counted: it costs nothing.

    Every source shipped so far is free - web search is scraped, Commons and Openverse
    need no key, Pexels and Pixabay need a free one - so no `search` ledger row is
    written and passing the allowance is a job-log note, never a skipped beat: cost
    never degrades quality (11.3). A metered adapter records its own row per query and
    checks the hard cap before it calls, exactly as the judge does."""

    max_queries: int = 0
    queries: int = 0
    over: bool = False
    notes: list[str] = field(default_factory=lambda: [])

    def count(self, name: str) -> None:
        self.queries += 1
        if self.max_queries and self.queries > self.max_queries and not self.over:
            self.over = True
            self.notes.append(
                f"sourcing: past the style's search_max_queries ({self.max_queries}) at "
                f"{name}; every source is free, so the remaining beats are searched anyway"
            )


def keep(
    candidates: Sequence[Candidate], log: Callable[[str], None] = lambda _: None
) -> list[Candidate]:
    """5.2: the candidates the code-only hard rejects let through, before the judge
    is asked for anything. A rejection is of the candidate, never of the beat."""
    kept: list[Candidate] = []
    for candidate in candidates:
        why = reject_size(candidate.width, candidate.height)
        if why is None:
            kept.append(candidate)
        else:
            log(f"sourcing: {candidate.url} rejected: {why}")
    return kept


def rank(candidates: Sequence[Candidate], verdicts: Sequence[Verdict] | None) -> list[_Ranked]:
    """5.2: the judge's accepted candidates best-first, ties by the source's own order
    (the sort is stable). Unjudged, the source's order is kept exactly as it is."""
    if verdicts is None:
        return [_Ranked(c) for c in candidates]
    scored = [
        (verdict.score, _Ranked(candidate, verdict))
        for candidate, verdict in zip(candidates, verdicts, strict=True)
        if verdict.accepted
    ]
    return [ranked for _, ranked in sorted(scored, key=lambda pair: -pair[0])]


def _verdict(model: str, verdict: Verdict | None) -> JudgeVerdict | None:
    if verdict is None:
        return None
    return JudgeVerdict(model=model, score=verdict.score, reasons=list(verdict.reasons))


def _search_cached(
    source: ImageSource,
    name: str,
    query: str,
    cache: Path,
    clock: Clock,
    judging: Judging,
    searching: Searching,
    *,
    subject_kind: str = "",
    topic: str = "",
    log: Callable[[str], None] = lambda _: None,
) -> _Fetched | None:
    """The candidate `query` from `source` gives this beat (5.2), fetched once per job."""
    folder = cache / cache_key(query, name)
    result = folder / "result.json"
    if result.is_file():
        data = json.loads(result.read_text(encoding="utf-8"))
        if data["file"] is None:
            return None
        candidate = Candidate.model_validate(data["candidate"])
        verdict = data.get("judge")
        return _Fetched(
            folder / data["file"],
            candidate,
            data["fetched_at"],
            verdict=JudgeVerdict.model_validate(verdict) if verdict else None,
            judge_skipped=bool(data.get("judge_skipped", False)),
        )
    folder.mkdir(parents=True, exist_ok=True)
    searching.count(name)
    candidates = keep(source.search(query, CANDIDATES), log)
    verdicts = judging.verdicts(query, subject_kind, topic, candidates, source.thumbnail)
    record: dict[str, object] = {
        "query": query,
        "source": name,
        "candidates": _CANDIDATES.dump_python(candidates, mode="json"),
        "judged": verdicts is not None,
        "candidate": None,
        "judge": None,
        "judge_skipped": verdicts is None,
        "file": None,
        "fetched_at": None,
    }
    fetched: _Fetched | None = None
    for ranked in rank(candidates, verdicts):
        try:
            path = source.fetch(ranked.candidate, folder / "image")
        except SourceError as exc:
            log(f"sourcing: {exc}")
            continue
        why = _reject_fetched(path)
        if why is not None:
            log(f"sourcing: {ranked.candidate.url} rejected: {why}")
            path.unlink(missing_ok=True)
            continue
        fetched = _Fetched(
            path,
            ranked.candidate,
            clock().isoformat(),
            verdict=_verdict(judging.model, ranked.verdict),
            judge_skipped=verdicts is None,
        )
        record |= {
            "candidate": ranked.candidate.model_dump(mode="json"),
            "judge": fetched.verdict.model_dump(mode="json") if fetched.verdict else None,
            "file": path.name,
            "fetched_at": fetched.fetched_at,
        }
        break
    result.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return fetched


def _reject_fetched(path: Path) -> str | None:
    """The 5.2 hard rejects on the downloaded file: the only size a source cannot
    misreport, plus a body Pillow cannot open at all."""
    try:
        with Image.open(path) as image:
            width, height = image.size
    except OSError:
        return "the downloaded file is not a readable image"
    return reject_size(width, height)


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
            generated: Generated | None = None,
            judge: JudgeVerdict | None = None) -> AssetRecord:  # fmt: skip
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
            judge=judge,
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
             redressed: bool = False, judge_skipped: bool = False) -> None:  # fmt: skip
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
                judge_skipped=judge_skipped,
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
    generating: Generating | None = None,
    judging: Judging | None = None,
    searching: Searching | None = None,
    topic: str = "",
    log: Callable[[str], None] = lambda _: None,
    clock: Clock = _utc_now,
) -> AssetManifest:
    """Decide every sourced beat's asset per the rules in the module docstring."""
    picture = validated.picture
    cache = job_dir / "work" / CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    searched = [(name, sources[name]) for name in source_order(order, policy) if name in sources]
    by_id = {ref.id: ref for ref in references}
    walk = _Walk(job_dir=job_dir, cache=cache, clock=clock, references=references)
    judging = judging if judging is not None else Judging()
    searching = searching if searching is not None else Searching()
    generating = generating if generating is not None else Generating()

    def search(beat: Beat, query: str) -> tuple[_Fetched, SearchOrigin] | None:
        if not query:
            return None
        for name, source in searched:
            found = _search_cached(
                source, name, query, cache, clock, judging, searching,
                subject_kind=beat.subject_kind or "", topic=topic, log=log,
            )  # fmt: skip
            if found is not None:
                return found, source.origin
        return None

    def generated(beat: Beat) -> AssetRecord | None:
        made = generating.make(beat, cache)
        if made is None:
            return None
        return walk.add(_new_id(beat), made.path, origin="generated",
                        fetched_at=clock().isoformat(), generated=made.generated)  # fmt: skip

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
            tried_generation = generating.generator is not None
            record = generated(beat)
            if record is not None:
                walk.show(beat, record, 2)
                continue
        found = None
        for rung, query in ((0, beat.query), (1, beat.query_fallback)):
            hit = search(beat, query)
            if hit is not None:
                found = (rung, hit)
                break
        if found is not None:
            rung, (fetched, origin) = found
            record = walk.add(
                _new_id(beat), fetched.path, origin=origin,
                fetched_at=fetched.fetched_at, candidate=fetched.candidate,
                judge=fetched.verdict,
            )  # fmt: skip
            walk.show(beat, record, rung, judge_skipped=fetched.judge_skipped)
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

    for note in (*judging.notes, *searching.notes, *generating.notes):
        log(note)
    runtime = picture.beats[-1].end if picture.beats else 0.0
    return AssetManifest(
        assets=list(walk.records.values()),
        beats=walk.beats,
        aliases=walk.aliases,
        runtime_s=runtime,
        rescued_max=rescued_max(spec, runtime),
        judge_calls=judging.calls,
        judge_max=judging.max_calls,
        search_queries=searching.queries,
        search_max=searching.max_queries,
        generated_images=generating.images,
        gen_max=generating.max_images,
    )


# --- the step as the pipeline runs it ----------------------------------------------------------


_REFS = TypeAdapter(list[ReferenceRecord])


def topic_line(job_dir: Path) -> str:
    """The brief's topic line the judge is told about (5.2): the brief's first
    non-blank line, headings stripped, capped so a whole brief never travels."""
    brief = job_dir / "input" / "brief.md"
    if not brief.is_file():
        return ""
    for line in brief.read_text(encoding="utf-8").splitlines():
        text = line.lstrip("#").strip()
        if text:
            return text[:200]
    return ""


@dataclass
class Sourcing:
    """The `sourcing` step's configuration: the adapters by config name, the 5.1
    order (`ASSET_SOURCES`), the 5.2 policy, the relevance judge (None: no judging,
    the source's own order decides) and the rung-2 generator (None: `IMAGE_GEN=none`).
    A configured name with no adapter is skipped and noted in the job log."""

    sources: Mapping[str, ImageSource] = field(default_factory=lambda: {})
    order: Sequence[str] = DEFAULT_ORDER
    policy: AssetPolicy = "any"
    generator: ImageGenerator | None = None
    judge: RelevanceJudge | None = None
    # Why a configured source has no adapter, one line each, written by
    # `from_settings` and logged by the pipeline before the step runs.
    notes: Sequence[str] = ()

    def missing(self) -> list[str]:
        return [n for n in source_order(self.order, self.policy) if n not in self.sources]

    def run(self, job: Job, spec: StyleSpec, *, clock: Clock = _utc_now) -> AssetManifest:
        """Source every beat of `work/plan.validated.json`, write `work/assets.json`,
        `out/rights.json` and `out/credits.md`. Every candidate rejected, every judge
        note and the spent judge budget are `job.log` lines."""
        job_dir = job.path
        validated = ValidatedPlan.model_validate_json(
            (job_dir / "work" / "plan.validated.json").read_text(encoding="utf-8")
        )
        refs_path = job_dir / "input" / "refs.json"
        references = (
            _REFS.validate_json(refs_path.read_text(encoding="utf-8"))
            if refs_path.is_file()
            else []
        )
        judging = Judging(
            judge=self.judge.bind(job) if self.judge is not None else None,
            max_calls=spec.budget.judge_max_calls,
        )
        searching = Searching(max_queries=spec.budget.search_max_queries)
        generating = Generating(
            generator=self.generator.bind(job) if self.generator is not None else None,
            spec=spec,
            max_images=spec.budget.gen_max_per_short,
        )
        manifest = source_assets(
            validated,
            references,
            self.policy,
            spec=spec,
            sources=self.sources,
            order=self.order,
            job_dir=job_dir,
            generating=generating,
            judging=judging,
            searching=searching,
            topic=topic_line(job_dir),
            log=lambda line: jobs.note(job, line, now=clock),
            clock=clock,
        )
        write_manifest(job_dir, manifest)
        rights.write(job_dir, manifest, validated.picture)
        return manifest


def judge_from_settings(settings: Settings, ledger: Callable[[], Ledger]) -> RelevanceJudge | None:
    """The judge `RELEVANCE_JUDGE` names (5.2); `none` means the source's own order
    decides, which is what the step did before ticket 017."""
    if settings.relevance_judge == "none":
        return None
    if settings.relevance_judge == "fake":
        return FakeRelevanceJudge()
    return VisionJudge(
        ledger, api_key=settings.anthropic_api_key, model=settings.relevance_judge_model
    )


def generator_from_settings(
    settings: Settings, ledger: Callable[[], Ledger]
) -> ImageGenerator | None:
    """The generator `IMAGE_GEN` names (5.5): `none` makes rung 2 a no-op, `fake`
    writes the prompt onto a solid frame for a local run, `gemini` is the REST
    adapter on `IMAGE_GEN_ENDPOINT` with `IMAGE_GEN_MODEL`."""
    if settings.image_gen == "none":
        return None
    if settings.image_gen == "fake":
        return FakeImageGenerator()
    return GeminiImageGenerator(
        ledger,
        api_key=settings.gemini_api_key,
        model=settings.image_gen_model,
        endpoint=settings.image_gen_endpoint,
    )


def from_settings(settings: Settings, *, ledger: Callable[[], Ledger]) -> Sourcing:
    """The configured step: one adapter per name in `ASSET_SOURCES` (5.1). `web` is
    the scraped search (017), `commons`, `openverse`, `pexels` and `pixabay` the free
    libraries (018), and `fake` names the fake source for a local run with no network.
    `ASSET_POLICY=rights_safe` drops `web` from the order and nothing else.

    Pexels and Pixabay want a free key; a configured source whose key is unset is left
    out with a note rather than failing startup, so the ladder simply skips that rung.
    `owner` and `generate` in the order are the fixed bookends and build nothing."""
    order = parse_order(settings.asset_sources)
    wanted = source_order(order, settings.asset_policy)
    sources: dict[str, ImageSource] = {}
    notes: list[str] = []
    for name in wanted:
        if name == "web":
            sources["web"] = WebImageSource()
        elif name == "commons":
            sources["commons"] = CommonsImageSource()
        elif name == "openverse":
            sources["openverse"] = OpenverseImageSource()
        elif name == "pexels" and settings.pexels_api_key is not None:
            sources["pexels"] = PexelsImageSource(api_key=settings.pexels_api_key)
        elif name == "pixabay" and settings.pixabay_api_key is not None:
            sources["pixabay"] = PixabayImageSource(api_key=settings.pixabay_api_key)
        elif name in KEYED:
            notes.append(
                f"{name} is in ASSET_SOURCES but {KEYED[name]} is not set in .env; "
                "that source is skipped (the key is free; decision 5.1)"
            )
    if "fake" in order:
        sources["fake"] = FakeImageSource("web")
    return Sourcing(
        sources=sources,
        order=order,
        policy=settings.asset_policy,
        generator=generator_from_settings(settings, ledger),
        judge=judge_from_settings(settings, ledger),
        notes=notes,
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
