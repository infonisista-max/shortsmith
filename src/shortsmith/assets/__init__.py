"""The asset step (PRD `assets`; ticket 016): one picture for every sourced beat.

`source_assets(validated, references, policy, ...)` walks the validated plan's beats
in order and decides, per beat, which asset it shows and how, recording everything in
an `AssetManifest` (`work/assets.json`):

- Sourced beats are the non-presenter beats the grammar labelled with a
  `subject_kind` (4.2); presenter and finale beats only point at assets other beats
  source, through `manifest.aliases`.
- The opening beats (055; 3.4 as amended): the first `beats.opening_beats_min` beats
  of the plan carry the short's strongest images of its main subject, so their ladder
  is owner reference (the planner names it, or its caption matches), then the
  best-scored sourced image - every source in the order is searched and the highest
  judge score wins, ties by source order (`best_search`) - then a generated image
  past the `gen_max_per_short` cap (11.3: cost never degrades the opening). They never
  fall to a rung-3 re-dress: with nothing found and nothing generated the beat is shown
  over the gradient with a job-log line (096: a small problem never fails the job; it
  used to raise `AssetError`).
- Replaced beats (096, operator answer 1): a beat the editor or the change box stripped
  of its visual (`replaced`, from `JobRecord.replaced`) runs the replacement ladder
  before any planned reuse, reference or opening rule, every step a
  `sourcing: bNN: replacement ladder: ...` line. A named entity (`depicts_of`) is
  NEVER generated: its owner reference (the planned id, else `matching_reference`)
  while it has a showing left, else a real image already shown for that entity
  (`nearest(entity=...)`, stills only) re-dressed at rung 3, else the gradient.
  Anything else takes a stock clip from the clip sources (`query`, then
  `query_fallback`), else an image generated for the line past the cap (rung 2), else
  the gradient.
- No beat fails the step (096): an exception while sourcing one beat (a missing
  reference file, an unreadable download, a source bug) is a
  `sourcing: bNN: <error>; shown over the gradient (plain fallback)` line and that beat
  takes the gradient; the other beats are sourced as usual. `BudgetExceeded` and
  `LedgerError` still stop the job.
- A planned asset id that an earlier beat already sourced is reused as planned
  (4.3). A beat naming a reference id, or whose `query` shares a significant word
  with a reference caption, takes the owner reference first (1.3, 5.1).
- `source_intent` (5.1): `reuse` takes the nearest earlier asset - on a named-entity
  beat only one first shown for that entity - unless its planned image is capped, when
  the beat is searched afresh (071: only number and quote beats carry on); `generate`
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
- Classification by the fetched file's real dimensions (5.3 as amended by 057):
  `photo` when the planner asked `photo` (or left it open), the image is portrait or
  square (height >= width) and it covers 1080x1920 at no more than the style's
  `broll.full_bleed_max_upscale` (2.0), the width judged after the upscale. The
  origin plays no part (5.1 as amended: the Ken Burns and the overlays are the
  re-dressing, web images included). Anything else - a landscape, an image that
  cannot cover the frame at that upscale, a planned `card` - is a `card`; a planned
  `photo` that became a card records `treatment_downgraded`.

- Which candidate a source's hits give the beat (5.2, ticket 017): the code-only hard
  rejects drop what is too small for the beat's slot, too wide, from a stock-preview
  host or not an image (`base`), and the survivors go to the relevance judge
  (`judge`), which scores each 0-3. Best >= 2 wins, ties by the source's own order,
  everything under 2 means the next source and then the ladder. A candidate whose
  download is refused or rejected is dropped and the next accepted one is taken; the
  beat is never rejected for a candidate. With no judge configured, its call ceiling
  spent, or a judge that could not answer, the first candidate the hard rejects kept
  wins and the beat records `judge_skipped`.

- Named people (053, amending 5.1 and 5.2 after F1 showed a Pexels stranger as Neem
  Karoli Baba): for a beat whose subject is a named entity (`generate.depicts_of`) the
  stock libraries (`STOCK_ORIGINS`: Pexels, Pixabay) are neither searched nor
  accepted - the ladder is owner refs, web, Commons, Openverse with `query`, the same
  with `query_fallback`, then rung 2's stylised illustration, then the usual rungs.
  Name evidence ranks first: `name_words` are the capitalised words of the beat's own
  query (then of `query_fallback`), and a candidate whose page URL or file name carries
  at least half of them (`name_evidence`) ranks ahead of one that does not, judged or
  not; the judge still filters what is under 2.
- The size floor follows the slot (053 rule 4): every sourced beat's image must fill
  the archival card at no more than the renderer's upscale, with the style's card
  border (`card_border`) - a `photo` beat included, since what cannot be full-bleed is
  a card by 5.3. `base.reject_size` holds the arithmetic on `render`'s numbers.
- A source's notes about a search (053 rule 5: a 403, an empty answer, its status and
  the query) are drained into the job log after every search as `sourcing:` lines.

- Moving footage (058, amending 4.1 and 5.1): a `clip` beat asks for a full-screen muted
  stock video. Its ladder runs before the still ladder: a planned reuse of an earlier
  clip record, then Pexels video and Pixabay video (`clips`, in `clip_order`) with
  `query` then `query_fallback` (`_clip_cached`) - each hit's smallest file that covers
  1080x1920 at the style's `broll.full_bleed_max_upscale` under `CLIP_MAX_BYTES`
  (`clips.choose_file`), judged on its preview image, portrait first among equals, and
  at least as long as the beat needs (`clip_need_s`: the beat plus the `number` /
  `quote` beats that carry it on, at the style's playback speed) - fetched into the
  job's asset folder and probed with ffprobe. A named entity (`depicts_of`) is never
  offered a clip (rule 2: a stock stranger is never King Saud) and a beat that finds
  no usable clip takes the still ladder, both with a job-log line saying why. A clip
  record is shown only by clip beats and carry-on beats, never re-dressed (a rescue
  re-dresses stills), and never a set piece's still; it counts as an image for the
  4.3 / 056 reuse rule.

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
from typing import Literal, cast, get_args

from PIL import Image
from pydantic import TypeAdapter

from shortsmith import ffmpeg, jobs, rights
from shortsmith.assets.base import (
    BOOKENDS,
    FRAME_H,
    FRAME_W,
    MAX_ASPECT,
    MAX_BYTES,
    MAX_UPSCALE,
    STOCK_HOSTS,
    FakeImageSource,
    ImageSource,
    SourceError,
    covers_frame,
    media_type,
    parse_order,
    reject_body,
    reject_host,
    reject_size,
    source_order,
)
from shortsmith.assets.clips import (
    CLIP_ORDER,
    ClipCandidate,
    ClipSource,
    FakeClipSource,
    PexelsClipSource,
    PixabayClipSource,
    choose_file,
    is_portrait,
    reject_clip,
)
from shortsmith.assets.commons import CommonsImageSource
from shortsmith.assets.generate import (
    FakeImageGenerator,
    GeminiImageGenerator,
    GeneratedAsset,
    Generating,
    GeneratorError,
    ImageGenerator,
    depicts_of,
    is_diagram_base,
)
from shortsmith.assets.judge import (
    FakeRelevanceJudge,
    Judging,
    RelevanceJudge,
    Thumb,
    Verdict,
    VisionJudge,
)
from shortsmith.assets.lines import FakeLineFinder, LineFinder, VisionLineFinder, find_highlights
from shortsmith.assets.openverse import OpenverseImageSource
from shortsmith.assets.pexels import PexelsImageSource
from shortsmith.assets.pixabay import PixabayImageSource
from shortsmith.assets.web import WebImageSource
from shortsmith.config import Settings
from shortsmith.contracts import (
    AssetKind,
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
    PicturePlan,
    ReferenceRecord,
    SearchOrigin,
    StickerRecord,
    Treatment,
    ValidatedPlan,
)
from shortsmith.jobs import Job
from shortsmith.ledger import BudgetExceeded, Ledger, LedgerError
from shortsmith.stickers import StickerShelf, live_shelf
from shortsmith.styles import StyleSpec

__all__ = [
    "BOOKENDS",
    "CLIP_KIND",
    "CLIP_ORDER",
    "FRAME_H",
    "FRAME_W",
    "MAX_ASPECT",
    "MAX_BYTES",
    "MAX_UPSCALE",
    "STOCK_HOSTS",
    "STOCK_ORIGINS",
    "STOPWORDS",
    "TITLE_WORDS",
    "AssetError",
    "ClipCandidate",
    "ClipSource",
    "CommonsImageSource",
    "FakeClipSource",
    "FakeImageGenerator",
    "FakeImageSource",
    "FakeLineFinder",
    "FakeRelevanceJudge",
    "GeminiImageGenerator",
    "GeneratedAsset",
    "Generating",
    "GeneratorError",
    "ImageGenerator",
    "ImageSource",
    "Judging",
    "LineFinder",
    "OpenverseImageSource",
    "PexelsClipSource",
    "PexelsImageSource",
    "PixabayClipSource",
    "PixabayImageSource",
    "RelevanceJudge",
    "Searching",
    "SourceError",
    "Sourcing",
    "Thumb",
    "Verdict",
    "VisionJudge",
    "VisionLineFinder",
    "WebImageSource",
    "card_border",
    "choose_file",
    "clip_need_s",
    "covers_frame",
    "entity_crossings",
    "find_highlights",
    "image_reuse_problems",
    "image_showings",
    "is_showing",
    "matching_reference",
    "media_type",
    "name_evidence",
    "name_words",
    "parse_order",
    "reject_body",
    "reject_host",
    "reject_size",
    "source_assets",
    "source_order",
    "subject_words",
]

MANIFEST_NAME = "assets.json"
CACHE_DIR = "assets"
DEFAULT_ORDER: tuple[SearchOrigin, ...] = get_args(SearchOrigin)
CANDIDATES = 6  # 5.2: at most six candidates per beat reach the judge
# 020: a `map` is drawn from the bundled geodata (9.3), so it sources no picture either.
NOT_SOURCED = frozenset({"presenter_full", "presenter_pip", "finale", "map"})
# 018: the sources that want a free key, and the `.env` name that carries it.
KEYED: Mapping[str, str] = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}
REUSING_KINDS = frozenset({"number", "quote"})
# 053 rule 1: the stock libraries, never searched for a named entity.
STOCK_ORIGINS: frozenset[str] = frozenset({"pexels", "pixabay"})
# 058: the moving footage kind; its asset is a stock video file (`AssetRecord.kind` `clip`).
CLIP_KIND = "clip"
EPS = 1e-9

# 4.4: a re-dress punches in a further step and moves the focus, so no framing repeats.
REDRESS_ZOOM_STEP = 0.15
REDRESS_FOCI: tuple[tuple[float, float], ...] = (
    (0.5, 0.5), (0.35, 0.4), (0.65, 0.6), (0.4, 0.65), (0.6, 0.35),
)  # fmt: skip

# Words too generic to tie a query to a reference caption (056 (2): "image", "photo",
# "with" never create a match).
STOPWORDS = frozenset(
    [
        "the", "and", "for", "with", "from", "into", "over", "this", "that", "photo",
        "image", "picture", "portrait", "archival", "shot", "view", "close", "closeup",
        "old", "new", "our", "your", "his", "her", "their", "who", "which", "young",
        "family", "official",
    ]
)  # fmt: skip
# 056 (2): titles and honorifics are not a subject's name; "king saud image" names Saud,
# not every king in the plan. A capitalised title is therefore never a name word either.
# Honorifics that are part of how a person is named (Neem Karoli Baba, Guru Nanak,
# Swami Vivekananda) are not titles here: they stay name words.
TITLE_WORDS = frozenset(
    [
        "king", "queen", "prince", "princess", "emperor", "empress", "sultan", "sheikh",
        "shah", "nawab", "nizam", "maharaja", "raja", "rani", "president", "prime",
        "minister", "chancellor", "premier", "governor", "general", "colonel", "captain",
        "admiral", "marshal", "lord", "lady", "sir", "dame", "duke", "duchess", "count",
        "baron", "chief", "ceo", "founder", "chairman", "doctor", "professor", "saint",
        "pope", "bishop", "shri", "sri", "smt", "mr", "mrs", "ms", "dr",
    ]
)  # fmt: skip
_STOPWORDS = STOPWORDS | TITLE_WORDS
_WORD = re.compile(r"[^\W_]+", re.UNICODE)

Clock = Callable[[], datetime]
Planned = Literal["photo", "card", "auto"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AssetError(RuntimeError):
    """The step cannot proceed (a missing reference file, an unreadable image)."""


# --- classification (5.3) -------------------------------------------------------------------


def full_bleed(width: int, height: int, *, max_upscale: float) -> bool:
    """057: portrait or square (height >= width), covering 1080x1920 within
    `max_upscale` (the style's `broll.full_bleed_max_upscale`); the width is judged
    after the upscale, never before."""
    if height < width:
        return False
    return covers_frame(width, height, max_upscale)


def classify(
    width: int, height: int, *, planned: Planned, max_upscale: float
) -> tuple[Treatment, bool]:
    """(treatment, downgraded) for an asset of the real `width` x `height`: `photo`
    when the planner asked `photo` or `auto` and the image can fill the frame, else a
    card; a planned `photo` drawn as a card is the downgrade. The origin plays no part
    (057)."""
    wants_photo = planned in ("photo", "auto")
    if wants_photo and full_bleed(width, height, max_upscale=max_upscale):
        return "photo", False
    return "card", planned == "photo"


def _planned(beat: Beat) -> Planned:
    return beat.kind if beat.kind in ("photo", "card") else "auto"  # pyright: ignore[reportReturnType]


def card_border(spec: StyleSpec) -> int:
    """The style's card border, the one style number the size floor needs (053)."""
    return int(spec.broll.motion.get("card", {}).get("border_px", 0))


# --- name evidence (053 rule 2) -------------------------------------------------------------


def name_words(beat: Beat) -> frozenset[str]:
    """The entity's name as the plan wrote it: the capitalised words of the beat's
    query (its `query_fallback` when the query has none), lower-cased, stopwords out."""
    for text in (beat.query, beat.query_fallback):
        words = {w.lower() for w in _WORD.findall(text) if w[:1].isupper()}
        words = {w for w in words if len(w) >= 3 and w not in _STOPWORDS}
        if words:
            return frozenset(words)
    return frozenset()


def name_evidence(words: frozenset[str], candidate: Candidate) -> bool:
    """Whether the candidate's page URL or file name carries the name: at least half
    of `words`, as whole words of the slugged URLs (so `virat-kohli` counts and
    `ViratKohli` does not)."""
    if not words:
        return False
    found = set(_WORD.findall(f"{candidate.page_url} {candidate.url}".lower()))
    return len(words & found) >= math.ceil(len(words) / 2)


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

    def sha256(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def _fetched_dict(fetched: _Fetched) -> dict[str, object]:
    assert fetched.candidate is not None
    return {
        "candidate": fetched.candidate.model_dump(mode="json"),
        "judge": fetched.verdict.model_dump(mode="json") if fetched.verdict else None,
        "file": fetched.path.name,
        "fetched_at": fetched.fetched_at,
    }


def _alternates(record: Mapping[str, object]) -> list[Mapping[str, object]]:
    """The `alternates` of a cache record: the files fetched after the first (056 (3))."""
    listed = record.get("alternates")
    if not isinstance(listed, list):
        return []
    return [alt for alt in cast("list[object]", listed) if isinstance(alt, Mapping)]  # pyright: ignore[reportUnknownVariableType]


def _fetched_from(data: Mapping[str, object], folder: Path, judge_skipped: bool) -> _Fetched:
    verdict = data.get("judge")
    return _Fetched(
        folder / str(data["file"]),
        Candidate.model_validate(data["candidate"]),
        str(data["fetched_at"]),
        verdict=JudgeVerdict.model_validate(verdict) if verdict else None,
        judge_skipped=judge_skipped,
    )


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
    candidates: Sequence[Candidate],
    log: Callable[[str], None] = lambda _: None,
    border_px: int = 0,
) -> list[Candidate]:
    """5.2: the candidates the code-only hard rejects let through, before the judge
    is asked for anything: the card slot's size floor, the aspect and (053) the
    stock-host list. A rejection is of the candidate, never of the beat, one log line
    each."""
    kept: list[Candidate] = []
    for candidate in candidates:
        why = reject_host(candidate) or reject_size(candidate.width, candidate.height, border_px)
        if why is None:
            kept.append(candidate)
        else:
            log(f"sourcing: {candidate.url} rejected: {why}")
    return kept


def rank(
    candidates: Sequence[Candidate],
    verdicts: Sequence[Verdict] | None,
    names: frozenset[str] = frozenset(),
) -> list[_Ranked]:
    """5.2: the judge's accepted candidates best-first, ties by the source's own order
    (the sort is stable). Unjudged, the source's order is kept exactly as it is. With
    `names` (053 rule 2), name-evidenced candidates rank ahead of the rest either way."""
    if verdicts is None:
        ranked = [_Ranked(c) for c in candidates]
    else:
        ranked = [
            _Ranked(candidate, verdict)
            for candidate, verdict in zip(candidates, verdicts, strict=True)
            if verdict.accepted
        ]
    return sorted(
        ranked,
        key=lambda r: (
            not name_evidence(names, r.candidate),
            -(r.verdict.score if r.verdict is not None else 0),
        ),
    )


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
    border_px: int = 0,
    names: frozenset[str] = frozenset(),
    log: Callable[[str], None] = lambda _: None,
    saturated: Callable[[str], str | None] = lambda _: None,
) -> _Fetched | None:
    """The candidate `query` from `source` gives this beat (5.2), fetched once per job.

    056 (3): `saturated(sha256)` says why a file may not be shown again (its showings
    are spent), or None. A candidate whose file is saturated is skipped with that line
    and the next ranked one is fetched - into the same cache folder as `alternates`, so
    a later beat asking the same query finds every file already fetched and downloads
    only what is new. The search itself is never repeated."""
    folder = cache / cache_key(query, name)
    result = folder / "result.json"
    if result.is_file():
        data = json.loads(result.read_text(encoding="utf-8"))
        if data["file"] is None:
            return None
        skipped = bool(data.get("judge_skipped", False))
        fetched_all = [_fetched_from(data, folder, skipped)] + [
            _fetched_from(alt, folder, skipped) for alt in _alternates(data)
        ]
        for fetched in fetched_all:
            why = saturated(fetched.sha256())
            if why is None:
                return fetched
            log(f"sourcing: {fetched.candidate.url if fetched.candidate else '?'} skipped: {why}")  # noqa: E501
        candidates = _CANDIDATES.validate_python(data["candidates"])
        verdicts = (
            judging.verdicts(query, subject_kind, topic, candidates, source.thumbnail)
            if data.get("judged")
            else None
        )
        record: dict[str, object] = dict(data)
    else:
        folder.mkdir(parents=True, exist_ok=True)
        searching.count(name)
        found = source.search(query, CANDIDATES)
        for line in source.drain():
            log(f"sourcing: {line}")
        candidates = keep(found, log, border_px)
        verdicts = judging.verdicts(query, subject_kind, topic, candidates, source.thumbnail)
        fetched_all = []
        record = {
            "query": query,
            "source": name,
            "candidates": _CANDIDATES.dump_python(candidates, mode="json"),
            "judged": verdicts is not None,
            "candidate": None,
            "judge": None,
            "judge_skipped": verdicts is None,
            "file": None,
            "fetched_at": None,
            "alternates": [],
        }
    seen = {f.candidate.url for f in fetched_all if f.candidate is not None}
    fetched: _Fetched | None = None
    for ranked in rank(candidates, verdicts, names):
        if ranked.candidate.url in seen:
            continue
        dest = folder / ("image" if not fetched_all else f"image-{len(fetched_all) + 1}")
        try:
            path = source.fetch(ranked.candidate, dest)
        except SourceError as exc:
            log(f"sourcing: {exc}")
            continue
        why = _reject_fetched(path, border_px)
        if why is not None:
            log(f"sourcing: {ranked.candidate.url} rejected: {why}")
            path.unlink(missing_ok=True)
            continue
        got = _Fetched(
            path,
            ranked.candidate,
            clock().isoformat(),
            verdict=_verdict(judging.model, ranked.verdict),
            judge_skipped=verdicts is None,
        )
        if not fetched_all:
            record |= _fetched_dict(got)
        else:
            record["alternates"] = [*_alternates(record), _fetched_dict(got)]
        fetched_all.append(got)
        why = saturated(got.sha256())
        if why is not None:
            log(f"sourcing: {ranked.candidate.url} skipped: {why}")
            continue
        fetched = got
        break
    result.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return fetched


def _reject_fetched(path: Path, border_px: int) -> str | None:
    """The 5.2 hard rejects on the downloaded file: the only size a source cannot
    misreport, plus a body Pillow cannot open at all."""
    try:
        with Image.open(path) as image:
            width, height = image.size
    except OSError:
        return "the downloaded file is not a readable image"
    return reject_size(width, height, border_px)


# --- moving footage (058) --------------------------------------------------------------------


def clip_need_s(beat: Beat, beats: Sequence[Beat], *, speed: float = 1.0) -> float:
    """How many seconds of footage `beat` needs (058 (5)): its own length plus the
    consecutive `number` / `quote` beats after it, which carry the clip on over their
    stamps (4.2), all at the style's playback `speed`."""
    ids = [b.id for b in beats]
    at = ids.index(beat.id) if beat.id in ids else -1
    need = beat.end - beat.start
    rest: Sequence[Beat] = beats[at + 1 :] if at >= 0 else ()
    for following in rest:
        if following.subject_kind not in REUSING_KINDS:
            break
        need += following.end - following.start
    return round(need * max(speed, EPS), 3)


def _probe_clip(path: Path) -> tuple[int, int, float] | None:
    """The real size and length of a downloaded clip, or None when ffprobe finds no
    video stream (the one size and length a source cannot misreport)."""
    try:
        width, height = ffmpeg.video_size(path)
        return width, height, ffmpeg.duration_s(path)
    except ffmpeg.FFmpegError:
        return None


def _clip_probe_reject(path: Path, need_s: float, max_upscale: float) -> str | None:
    probed = _probe_clip(path)
    if probed is None:
        return "the downloaded file is not a readable video"
    width, height, duration = probed
    if not covers_frame(width, height, max_upscale):
        return f"{width}x{height} px cannot cover 1080x1920 at <= {max_upscale:g}x"
    if duration + 1e-3 < need_s:
        return f"the file runs {duration:.2f} s, shorter than the {need_s:g} s the beat needs"
    return None


def rank_clips(
    candidates: Sequence[Candidate], verdicts: Sequence[Verdict] | None
) -> list[_Ranked]:
    """058 (3, 4): the judge's accepted clips best-first, portrait ahead of landscape at
    the same score, ties by the source's own order; unjudged, portrait first in the
    source's order."""
    ranked = rank(candidates, verdicts)
    return sorted(ranked, key=lambda r: (
        -(r.verdict.score if r.verdict is not None else 0), not is_portrait(r.candidate),
    ))  # fmt: skip


_CLIP_CANDIDATES = TypeAdapter(list[ClipCandidate])


def _clip_cached(
    source: ClipSource,
    query: str,
    need_s: float,
    cache: Path,
    clock: Clock,
    judging: Judging,
    searching: Searching,
    *,
    max_upscale: float,
    subject_kind: str = "",
    topic: str = "",
    log: Callable[[str], None] = lambda _: None,
    saturated: Callable[[str], str | None] = lambda _: None,
) -> _Fetched | None:
    """The clip `query` from `source` gives a beat needing `need_s` seconds (058), fetched
    once per job. The search is cached like an image search (`result.json` under
    `cache_key(query, source.name)`, a name no image source shares); every file fetched
    for the query is listed in `fetched`, so a later beat asking the same query, or
    needing a longer clip, downloads only what is new. Every line logged about the
    source's candidates passes through `source.scrub` (058 (8))."""
    name = source.name

    def note(line: str) -> None:
        log(f"sourcing: {source.scrub(line)}")

    folder = cache / cache_key(query, name)
    result = folder / "result.json"
    fetched_all: list[dict[str, object]] = []
    if result.is_file():
        data = json.loads(result.read_text(encoding="utf-8"))
        candidates = _CANDIDATES.validate_python(data["candidates"])
        verdicts = (
            judging.verdicts(query, subject_kind, topic, candidates, source.thumbnail)
            if data.get("judged")
            else None
        )
        fetched_all = [dict(f) for f in cast("list[Mapping[str, object]]", data.get("fetched", []))]
        record: dict[str, object] = dict(data)
    else:
        folder.mkdir(parents=True, exist_ok=True)
        searching.count(name)
        found = source.search(query, CANDIDATES)
        for line in source.drain():
            note(line)
        candidates: list[Candidate] = []
        for hit in found:
            if not isinstance(hit, ClipCandidate):
                continue
            why = reject_clip(hit, max_upscale=max_upscale)
            if why is not None:
                note(f"{hit.page_url or hit.url} rejected: {why}")
                continue
            chosen = choose_file(hit, max_upscale=max_upscale)
            assert chosen is not None  # reject_clip said a file fits
            candidates.append(chosen)
        verdicts = judging.verdicts(query, subject_kind, topic, candidates, source.thumbnail)
        record = {
            "query": query,
            "source": name,
            "candidates": _CANDIDATES.dump_python(candidates, mode="json"),
            "judged": verdicts is not None,
            "judge_skipped": verdicts is None,
            "fetched": [],
        }
    by_url: dict[str, dict[str, object]] = {str(f["url"]): f for f in fetched_all}
    fetched: _Fetched | None = None
    for ranked in rank_clips(candidates, verdicts):
        candidate = ranked.candidate
        if candidate.duration_s + 1e-3 < need_s:
            note(f"{candidate.url} skipped: {candidate.duration_s:g} s clip is shorter than "
                 f"the {need_s:g} s the beat needs")  # fmt: skip
            continue
        have: dict[str, object] | None = by_url.get(candidate.url)
        if have is None:
            dest = folder / f"clip-{len(fetched_all) + 1}"
            try:
                path = source.fetch(candidate, dest)
            except SourceError as exc:
                note(str(exc))
                continue
            why = _clip_probe_reject(path, need_s, max_upscale)
            if why is not None:
                note(f"{candidate.url} rejected: {why}")
                path.unlink(missing_ok=True)
                continue
            verdict = _verdict(judging.model, ranked.verdict)
            have = {
                "url": candidate.url,
                "candidate": candidate.model_dump(mode="json"),
                "judge": verdict.model_dump(mode="json") if verdict is not None else None,
                "file": path.name,
                "fetched_at": clock().isoformat(),
            }
            fetched_all.append(have)
            by_url[candidate.url] = have
        else:
            why = _clip_probe_reject(folder / str(have["file"]), need_s, max_upscale)
            if why is not None:
                note(f"{candidate.url} skipped: {why}")
                continue
        got = _fetched_from(have, folder, verdicts is None)
        why = saturated(got.sha256())
        if why is not None:
            note(f"{candidate.url} skipped: {why}")
            continue
        fetched = got
        break
    record["fetched"] = fetched_all
    result.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return fetched


# --- owner references (1.3) ---------------------------------------------------------------


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 3 and w not in _STOPWORDS}


def subject_words(beat: Beat) -> frozenset[str]:
    """What the beat is about, as words (056 (2)): the name the plan wrote (`name_words`,
    the capitalised words of the query with titles and generic words out), else every
    significant word of the query."""
    names = name_words(beat)
    return names if names else frozenset(_words(beat.query))


def matching_reference(
    beat: Beat, references: Sequence[ReferenceRecord]
) -> ReferenceRecord | None:
    """The owner reference whose caption names the beat's subject (056 (2)): the caption
    must share a subject word with the beat - a title or a generic word (king, image,
    with) never counts, and a caption left with no significant word is too vague to
    match anything, so it goes only where the planner named it. The caption sharing the
    most words wins, the first on a tie; None when no caption names the subject."""
    wanted = subject_words(beat)
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


def _measure(path: Path, kind: AssetKind = "image") -> tuple[int, int, float, str]:
    """(width, height, duration_s, sha256): the real size of a still through Pillow, or
    of a clip (058) through ffprobe with its length; 0 s on a still."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if kind == CLIP_KIND:
        probed = _probe_clip(path)
        if probed is None:
            raise AssetError(f"{path.name} is not a readable video")
        width, height, duration = probed
        return width, height, duration, digest
    try:
        with Image.open(path) as image:
            width, height = image.size
    except OSError as exc:
        raise AssetError(f"{path.name} is not a readable image: {exc}") from None
    return width, height, 0.0, digest


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


# 056 (3): a showing is a beat that puts the picture on screen as its own. A `number` or
# `quote` beat over the previous beat's picture carries that showing on (4.2, and the
# renderer continues the motion), and the wall's base and the finale's cards are set
# pieces; neither spends a showing.
SET_PIECE_KINDS = frozenset({"wall", "finale"})


def is_showing(beat: Beat, asset_id: str, previous_asset_id: str | None) -> bool:
    if beat.kind in SET_PIECE_KINDS:
        return False
    return not (beat.subject_kind in REUSING_KINDS and asset_id == previous_asset_id)


def image_showings(manifest: AssetManifest, plan: PicturePlan) -> dict[str, list[str]]:
    """Per image (`sha256`, however many ids point at it), the beats that show it (056
    (3)): carry-on beats and set pieces left out, as `source_assets` counts them."""
    beats = {b.id: b for b in plan.beats}
    out: dict[str, list[str]] = {}
    previous: str | None = None
    for shown in manifest.beats:
        if shown.asset_id is None:
            previous = None
            continue
        beat, record = beats.get(shown.beat_id), manifest.asset(shown.asset_id)
        if beat is not None and record is not None and is_showing(beat, record.id, previous):
            out.setdefault(record.sha256, []).append(shown.beat_id)
        previous = shown.asset_id
    return out


def entity_words(beat: Beat) -> frozenset[str]:
    """Who a beat names (071): its subject words and the words of its lower-third."""
    words = set(subject_words(beat))
    if beat.event.kind == "lower_third" and beat.event.text:
        words |= _words(beat.event.text)
    return frozenset(words)


def same_entity(beat: Beat, other: Beat) -> bool:
    """071: two beats are about one entity when they plan the same asset id or their
    queries or lower-thirds share a name word."""
    if beat.asset_id is not None and beat.asset_id == other.asset_id:
        return True
    return bool(entity_words(beat) & entity_words(other))


def _entity_label(beat: Beat) -> str:
    return beat.event.text if beat.event.kind == "lower_third" and beat.event.text else beat.query


def entity_crossings(manifest: AssetManifest, plan: PicturePlan) -> list[str]:
    """The 071 rule for gate T8: every named-entity beat showing an image first shown on a
    named-entity beat about someone else, naming both beats. A number or quote carry-on
    and a set piece are exempt."""
    beats = {b.id: b for b in plan.beats}
    first: dict[str, Beat] = {}
    problems: list[str] = []
    for shown in manifest.beats:
        beat = beats.get(shown.beat_id)
        record = manifest.asset(shown.asset_id) if shown.asset_id is not None else None
        if beat is None or record is None:
            continue
        origin = first.setdefault(record.sha256, beat)
        if origin is beat or beat.kind in SET_PIECE_KINDS or beat.subject_kind in REUSING_KINDS:
            continue
        if depicts_of(beat) != "named_entity" or depicts_of(origin) != "named_entity":
            continue
        if not same_entity(beat, origin):
            problems.append(
                f"{beat.id} ({_entity_label(beat)}) shows {record.id}, first shown on "
                f"{origin.id} ({_entity_label(origin)}), another entity"
            )
    return problems


def image_reuse_problems(manifest: AssetManifest, plan: PicturePlan) -> list[str]:
    """The 4.3 rule counted by image (056 (3)), for gate T8: every image shown more than
    `manifest.reuse_max` times, named by its ids and its beats. Empty on a manifest
    written before the rule (`reuse_max` 0)."""
    if manifest.reuse_max <= 0:
        return []
    problems: list[str] = []
    for digest, beat_ids in image_showings(manifest, plan).items():
        if len(beat_ids) <= manifest.reuse_max:
            continue
        ids = sorted(a.id for a in manifest.assets if a.sha256 == digest)
        problems.append(
            f"image {digest[:8]} ({', '.join(ids)}) is shown {len(beat_ids)} times "
            f"({', '.join(beat_ids)}), over broll.reuse_max {manifest.reuse_max}"
        )
    return problems


@dataclass
class _Walk:
    job_dir: Path
    cache: Path
    clock: Clock
    references: Sequence[ReferenceRecord]
    reuse_max: int = 0
    full_bleed_max_upscale: float = 1.0  # 057: the style's; 1.0 only in a bare test walk
    records: dict[str, AssetRecord] = field(default_factory=lambda: {})
    beats: list[BeatAsset] = field(default_factory=lambda: [])
    subjects: dict[str, str] = field(default_factory=lambda: {})  # beat id -> subject kind
    aliases: dict[str, str | None] = field(default_factory=lambda: {})
    redresses: dict[str, int] = field(default_factory=lambda: {})
    # 056 (3): showings per image (sha256), and the last asset shown, for the carry-on.
    showings: dict[str, int] = field(default_factory=lambda: {})
    last_asset: str | None = None
    # 071: the beat that first showed each image (sha256), so a rescue knows whose it is.
    firsts: dict[str, Beat] = field(default_factory=lambda: {})

    def blocked_sha(self, beat: Beat, digest: str) -> str | None:
        """Why the image `digest` may not be shown on `beat` (056 (3)), or None: its
        `reuse_max` showings are spent and this beat would be one more."""
        if beat.kind in SET_PIECE_KINDS or self.reuse_max <= 0:
            return None
        shown = self.showings.get(digest, 0)
        if shown < self.reuse_max:
            return None
        ids = sorted(r.id for r in self.records.values() if r.sha256 == digest)
        return (
            f"image {digest[:8]} ({', '.join(ids) or 'not catalogued yet'}) already shown "
            f"{shown} times (broll.reuse_max {self.reuse_max})"
        )

    def blocked(self, beat: Beat, record: AssetRecord) -> str | None:
        """`blocked_sha` for a catalogued asset; a carry-on beat is never blocked."""
        if not is_showing(beat, record.id, self.last_asset):
            return None
        return self.blocked_sha(beat, record.sha256)

    def blocked_ref(self, beat: Beat, ref: ReferenceRecord) -> str | None:
        """`blocked` for an owner reference, read off the record that already carries
        its file; a reference no beat has shown yet is never blocked."""
        rel = f"input/{ref.file}" if ref.kind == "image" else None
        existing = next((r for r in self.records.values() if r.file == rel), None)
        return self.blocked(beat, existing) if existing is not None else None

    def new_id(self, beat: Beat) -> str:
        """The record id for a beat's newly sourced asset: the planned id, unless an
        earlier beat already bound it to another file (056 (3): the third beat wanting
        a spent image gets its own record)."""
        planned = beat.asset_id
        if planned is not None and planned not in self.records:
            return planned
        return f"{beat.id}-asset"

    def add(self, asset_id: str, path: Path, *, origin: Origin, fetched_at: str,
            kind: AssetKind = "image", candidate: Candidate | None = None,
            generated: Generated | None = None,
            judge: JudgeVerdict | None = None) -> AssetRecord:  # fmt: skip
        width, height, duration, digest = _measure(path, kind)
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
            duration_s=duration,
        )  # fmt: skip
        self.records[asset_id] = record
        return record

    def owner(self, asset_id: str, ref: ReferenceRecord) -> AssetRecord:
        path, kind = _reference_file(ref, self.job_dir, self.cache)
        return self.add(asset_id, path, origin="owner_supplied", kind=kind,
                        fetched_at=self.clock().isoformat())  # fmt: skip

    def show(self, beat: Beat, record: AssetRecord, rung: int, *,
             redressed: bool = False, judge_skipped: bool = False) -> None:  # fmt: skip
        if record.kind == CLIP_KIND:
            # 058: a clip is drawn full-screen whatever its aspect (its 9:16 crop covers
            # the frame, `choose_file` saw to that); never a card, never downgraded.
            treatment, downgraded = cast("Treatment", CLIP_KIND), False
        else:
            treatment, downgraded = classify(
                record.width, record.height, planned=_planned(beat),
                max_upscale=self.full_bleed_max_upscale,
            )  # fmt: skip
        crop = Crop()
        if redressed:
            times = self.redresses.get(record.id, 0) + 1
            self.redresses[record.id] = times
            crop = redress_crop(times)
        if is_showing(beat, record.id, self.last_asset):
            self.showings[record.sha256] = self.showings.get(record.sha256, 0) + 1
        self.firsts.setdefault(record.sha256, beat)
        self.last_asset = record.id
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
                diagram_base=is_diagram_base(beat),
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
        self.last_asset = None
        if beat.asset_id is not None:
            self.aliases.setdefault(beat.asset_id, None)

    def nearest(
        self, subject: str | None = None, *, free_for: Beat | None = None,
        stills_only: bool = False, entity: Beat | None = None,
    ) -> AssetRecord | None:  # fmt: skip
        """The asset of the nearest earlier beat that shows one (of `subject` kind);
        with `free_for`, only one that still has a showing left for that beat (056 (3):
        a rescue never re-dresses a spent image); with `stills_only`, never a clip (058:
        a rescue re-dresses stills, a clip is carried on only by a number / quote beat);
        with `entity` a named-entity beat, only an image first shown for that same
        entity (071: never another person's picture)."""
        for shown in reversed(self.beats):
            if shown.asset_id is None:
                continue
            if subject is not None and self.subjects.get(shown.beat_id) != subject:
                continue
            record = self.records[shown.asset_id]
            if stills_only and record.kind == CLIP_KIND:
                continue
            if free_for is not None and self.blocked(free_for, record) is not None:
                continue
            if entity is not None and not self.of_entity(entity, record):
                continue
            return record
        return None

    def of_entity(self, beat: Beat, record: AssetRecord) -> bool:
        """071: whether `record` may be shown on `beat` as the same entity - always for
        a beat that names nobody; for a named entity, only an image first shown for it
        (the same planned id or owner reference, or a shared name word)."""
        if depicts_of(beat) != "named_entity":
            return True
        if record.id == beat.asset_id:
            return True
        ref = matching_reference(beat, self.references)
        if ref is not None and record.file == f"input/{ref.file}":
            return True
        first = self.firsts.get(record.sha256)
        return first is not None and same_entity(beat, first)


def clip_speed(spec: StyleSpec) -> float:
    """The style's clip playback speed (`broll.motion.clip.speed`, 058 (6)); 1.0 when
    the spec carries no clip row."""
    return float(spec.broll.motion.get("clip", {}).get("speed", 1.0))


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
    clips: Mapping[str, ClipSource] | None = None,
    clip_order: Sequence[str] = CLIP_ORDER,
    topic: str = "",
    log: Callable[[str], None] = lambda _: None,
    clock: Clock = _utc_now,
    replaced: frozenset[str] = frozenset(),
) -> AssetManifest:
    """Decide every sourced beat's asset per the rules in the module docstring. `clips`
    are the stock video sources by name (058), tried in `clip_order`; None or empty
    means every clip beat takes the still ladder. `replaced` names the beats whose
    visual was removed (096, `JobRecord.replaced`): they take the replacement ladder."""
    picture = validated.picture
    cache = job_dir / "work" / CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    searched = [(name, sources[name]) for name in source_order(order, policy) if name in sources]
    clip_sources = [clips[name] for name in clip_order if clips and name in clips]
    by_id = {ref.id: ref for ref in references}
    walk = _Walk(job_dir=job_dir, cache=cache, clock=clock, references=references,
                 reuse_max=spec.broll.reuse_max,
                 full_bleed_max_upscale=spec.broll.full_bleed_max_upscale)  # fmt: skip
    judging = judging if judging is not None else Judging()
    searching = searching if searching is not None else Searching()
    generating = generating if generating is not None else Generating()
    border = card_border(spec)
    speed = clip_speed(spec)

    def sources_for(beat: Beat) -> list[tuple[str, ImageSource]]:
        """053 rule 1: a named entity never comes from the stock libraries."""
        if depicts_of(beat) != "named_entity":
            return searched
        skipped = [name for name, _ in searched if name in STOCK_ORIGINS]
        if skipped:
            log(
                f"sourcing: {beat.id}: {', '.join(skipped)} not searched: a named entity is "
                "never shown as a stock stranger (053)"
            )
        return [(name, source) for name, source in searched if name not in STOCK_ORIGINS]

    def cached(beat: Beat, name: str, source: ImageSource, query: str) -> _Fetched | None:
        named = depicts_of(beat) == "named_entity"
        return _search_cached(
            source, name, query, cache, clock, judging, searching,
            subject_kind=beat.subject_kind or "", topic=topic, border_px=border,
            names=name_words(beat) if named else frozenset(), log=log,
            saturated=lambda digest: walk.blocked_sha(beat, digest),
        )  # fmt: skip

    def search(beat: Beat, query: str) -> tuple[_Fetched, SearchOrigin] | None:
        if not query:
            return None
        for name, source in sources_for(beat):
            found = cached(beat, name, source, query)
            if found is not None:
                return found, source.origin
        return None

    def best_search(beat: Beat, query: str) -> tuple[_Fetched, SearchOrigin] | None:
        """055: every source's best candidate for `query`, the highest judge score
        winning and ties going to the source order; an unjudged hit scores as 0 so a
        judged one always beats it."""
        if not query:
            return None
        best: tuple[int, _Fetched, SearchOrigin] | None = None
        for name, source in sources_for(beat):
            found = cached(beat, name, source, query)
            if found is None:
                continue
            score = found.verdict.score if found.verdict is not None else 0
            if best is None or score > best[0]:
                best = (score, found, source.origin)
        return None if best is None else (best[1], best[2])

    def generated(beat: Beat, *, force: bool = False) -> AssetRecord | None:
        made = generating.make(beat, cache, force=force)
        if made is None:
            return None
        return walk.add(walk.new_id(beat), made.path, origin="generated",
                        fetched_at=clock().isoformat(), generated=made.generated)  # fmt: skip

    def skipped(beat: Beat, why: str) -> None:
        log(f"sourcing: {beat.id}: {why}; the next candidate is tried (056)")

    def source_clip(beat: Beat) -> bool:
        """058: the clip ladder for a `clip` beat - a planned reuse of an earlier clip,
        then every clip source with `query` and `query_fallback` - showing the clip and
        returning True, or False (logged) when the beat is to take the still ladder."""
        if depicts_of(beat) == "named_entity":
            log(
                f"sourcing: {beat.id}: a named entity never takes a stock clip; the still "
                "ladder is used instead (053, 058)"
            )
            return False
        planned = beat.asset_id
        if planned is not None and planned in walk.records:
            record = walk.records[planned]
            if record.kind == CLIP_KIND and walk.blocked(beat, record) is None:
                walk.show(beat, record, 0)
                return True
        if not clip_sources:
            log(f"sourcing: {beat.id}: no clip source is configured; the still ladder is used "
                "instead (058)")  # fmt: skip
            return False
        if clip_found(beat) is not None:
            return True
        log(
            f"sourcing: {beat.id}: no usable clip for {beat.query!r} (need "
            f"{clip_need_s(beat, picture.beats, speed=speed):g} s, cover 1080x1920 at <= "
            f"{spec.broll.full_bleed_max_upscale:g}x); the still ladder is used instead (058)"
        )
        return False

    def clip_found(beat: Beat) -> AssetRecord | None:
        """Every clip source with `query` (rung 0) then `query_fallback` (rung 1) (058):
        the first usable clip, shown on the beat, or None."""
        need = clip_need_s(beat, picture.beats, speed=speed)
        for rung, query in ((0, beat.query), (1, beat.query_fallback)):
            if not query:
                continue
            for source in clip_sources:
                found = _clip_cached(
                    source, query, need, cache, clock, judging, searching,
                    max_upscale=spec.broll.full_bleed_max_upscale,
                    subject_kind=beat.subject_kind or "", topic=topic, log=log,
                    saturated=lambda digest: walk.blocked_sha(beat, digest),
                )  # fmt: skip
                if found is None:
                    continue
                record = walk.add(
                    walk.new_id(beat), found.path, origin=source.origin, kind=CLIP_KIND,
                    fetched_at=found.fetched_at, candidate=found.candidate, judge=found.verdict,
                )  # fmt: skip
                walk.show(beat, record, rung, judge_skipped=found.judge_skipped)
                return record
        return None

    def ladder(beat: Beat, step: str) -> None:
        log(f"sourcing: {beat.id}: replacement ladder: {step}")

    def source_replaced(beat: Beat) -> None:
        """Operator answer 1 (096): a beat whose visual was removed is never empty. A
        named entity is never generated: its owner reference, else a real image of it
        already in the reel re-dressed (rung 3), else the gradient. Anything else takes
        a stock clip, else an image generated for the line past the cap (rung 2), else
        the gradient. Every step is a job-log line."""
        if depicts_of(beat) == "named_entity":
            planned = beat.asset_id
            if planned is not None and planned in by_id:
                ref, asset_id = by_id[planned], planned
            else:
                ref = matching_reference(beat, references)
                asset_id = walk.new_id(beat)
            if ref is None:
                ladder(beat, "no owner reference names this entity")
            elif (why := walk.blocked_ref(beat, ref)) is not None:
                ladder(beat, f"owner reference {ref.id!r} is capped: {why}")
            else:
                ladder(beat, f"owner reference {ref.id!r} of the named entity")
                walk.show(beat, walk.owner(asset_id, ref), 0)
                return
            earlier = walk.nearest(free_for=beat, stills_only=True, entity=beat)
            if earlier is not None:
                ladder(beat, f"{earlier.id!r}, a real image of this entity already in the "
                       "reel, re-dressed")  # fmt: skip
                walk.show(beat, earlier, 3, redressed=True)
                return
            ladder(beat, "no real image of this entity is in the reel and a named entity is "
                   "never generated; shown over the gradient")  # fmt: skip
            walk.gradient(beat)
            return
        if not clip_sources:
            ladder(beat, "no clip source is configured")
        elif (clip := clip_found(beat)) is not None:
            ladder(beat, f"stock clip {clip.id!r} from {clip.origin}")
            return
        else:
            ladder(beat, f"no usable stock clip for {beat.query!r} or {beat.query_fallback!r}")
        record = generated(beat, force=True)
        if record is not None:
            ladder(beat, f"generated image {record.id!r} for the line")
            walk.show(beat, record, 2)
            return
        ladder(beat, "nothing could be generated; shown over the gradient")
        walk.gradient(beat)

    opening = {b.id for b in picture.beats[: spec.beats.opening_beats_min]}

    def source_opening(beat: Beat) -> None:
        """The opening's ladder (055): the best-scored sourced image, then a generated
        one past the cap; never a rung-3 re-dress. With neither, the gradient (096)."""
        for rung, query in ((0, beat.query), (1, beat.query_fallback)):
            hit = best_search(beat, query)
            if hit is None:
                continue
            fetched, origin = hit
            record = walk.add(
                walk.new_id(beat), fetched.path, origin=origin,
                fetched_at=fetched.fetched_at, candidate=fetched.candidate,
                judge=fetched.verdict,
            )  # fmt: skip
            walk.show(beat, record, rung, judge_skipped=fetched.judge_skipped)
            return
        record = generated(beat, force=True)
        if record is not None:
            walk.show(beat, record, 2)
            return
        log(
            f"sourcing: {beat.id}: opening beat has no image of {beat.query!r}: nothing was "
            "found and nothing could be generated; shown over the gradient (055, 096)"
        )
        walk.gradient(beat)

    def source_beat(beat: Beat) -> None:
        """One sourced beat's ladder, per the module docstring: a replaced beat's (096)
        first, then a clip beat's, then planned reuse, owner references, the opening's
        and the still ladder."""
        if beat.id in replaced:
            source_replaced(beat)
            return
        # 058: a clip beat runs the clip ladder first; a beat that finds no clip (or may
        # not have one) is sourced as a still below.
        if beat.kind == CLIP_KIND and source_clip(beat):
            return
        planned = beat.asset_id
        capped: list[str] = []  # 071: the planned or matched images this beat may not show
        # 056 (3): a planned reuse, an owner reference or a caption match is taken only
        # while the image has a showing left; past that the beat is sourced afresh.
        if planned is not None and planned in walk.records:
            record = walk.records[planned]
            carries_on = beat.subject_kind in REUSING_KINDS
            if record.kind == CLIP_KIND and beat.kind != CLIP_KIND and not carries_on:
                # 058: a still beat shows a still; the clip stays with its clip beats
                why = f"{planned!r} is a clip; a {beat.kind} beat shows a still (058)"
            elif record.kind == CLIP_KIND and depicts_of(beat) == "named_entity":
                why = f"{planned!r} is a clip; a named entity never takes one (058)"
            elif record.kind != CLIP_KIND and beat.kind == CLIP_KIND:
                why = f"{planned!r} is a still; a clip beat shows moving footage (058)"
            else:
                why = walk.blocked(beat, record)
            if why is None:
                walk.show(beat, record, 0)
                return
            skipped(beat, why)
            capped.append(repr(planned))
        elif planned is not None and planned in by_id:
            why = walk.blocked_ref(beat, by_id[planned])
            if why is None:
                walk.show(beat, walk.owner(planned, by_id[planned]), 0)
                return
            skipped(beat, why)
            capped.append(repr(planned))
        ref = matching_reference(beat, references)
        if ref is not None:
            why = walk.blocked_ref(beat, ref)
            if why is None:
                walk.show(beat, walk.owner(walk.new_id(beat), ref), 0)
                return
            skipped(beat, why)
            capped.append(f"owner reference {ref.id!r}")
        if beat.id in opening:
            source_opening(beat)
            return
        if beat.subject_kind in REUSING_KINDS:
            previous = walk.nearest()
            if previous is not None and walk.blocked(beat, previous) is None:
                walk.show(beat, previous, 0)
            else:
                walk.gradient(beat)
            return
        # 071: only number and quote beats carry on the previous picture. A planned
        # reuse whose image is capped is sourced afresh (056 (3)); an open one takes the
        # nearest earlier image, of the same entity on a named-entity beat.
        if beat.source_intent == "reuse" and capped:
            log(
                f"sourcing: {beat.id}: planned reuse of {', '.join(capped)} is capped; "
                f"searched afresh with its own query {beat.query!r} (071)"
            )
        elif beat.source_intent == "reuse":
            previous = walk.nearest(entity=beat)
            if previous is not None and walk.blocked(beat, previous) is None:
                walk.show(beat, previous, 0)
                return
        tried_generation = False
        if beat.subject_kind == "concept" and beat.source_intent == "generate":
            tried_generation = generating.generator is not None
            record = generated(beat)
            if record is not None:
                walk.show(beat, record, 2)
                return
        found = None
        for rung, query in ((0, beat.query), (1, beat.query_fallback)):
            hit = search(beat, query)
            if hit is not None:
                found = (rung, hit)
                break
        if found is not None:
            rung, (fetched, origin) = found
            record = walk.add(
                walk.new_id(beat), fetched.path, origin=origin,
                fetched_at=fetched.fetched_at, candidate=fetched.candidate,
                judge=fetched.verdict,
            )  # fmt: skip
            walk.show(beat, record, rung, judge_skipped=fetched.judge_skipped)
            return
        record = None if tried_generation else generated(beat)
        if record is not None:
            walk.show(beat, record, 2)
            return
        earlier = walk.nearest(beat.subject_kind, free_for=beat, stills_only=True, entity=beat)
        if earlier is not None:
            walk.show(beat, earlier, 3, redressed=True)
            return
        walk.gradient(beat)

    for beat in picture.beats:
        if beat.kind in NOT_SOURCED or (beat.subject_kind is None and beat.id not in replaced):
            continue
        try:
            source_beat(beat)
        except (BudgetExceeded, LedgerError):
            raise  # the hard cap and a missing price stop the job (11.3)
        except Exception as exc:  # 096: one beat's failure never fails the step
            log(f"sourcing: {beat.id}: {str(exc) or type(exc).__name__}; shown over the "
                "gradient (plain fallback)")  # fmt: skip
            if all(shown.beat_id != beat.id for shown in walk.beats):
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
        reuse_max=spec.broll.reuse_max,
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
    # 058: the stock video sources by name, tried in `clip_order` for a `clip` beat;
    # none means every clip beat takes the still ladder.
    clips: Mapping[str, ClipSource] = field(default_factory=lambda: {})
    clip_order: Sequence[str] = CLIP_ORDER
    # 062: where the plan's stickers are fetched from (the catalogue, the fetcher, the
    # cache); None drops every sticker with a job.log line, as a failed fetch does.
    stickers: StickerShelf | None = None
    # 078: finds a highlight's sentence on the owner's screenshot (the judge model); None
    # drops every highlight with a job.log line.
    lines: LineFinder | None = None
    # Why a configured source has no adapter, one line each, written by
    # `from_settings` and logged by the pipeline before the step runs.
    notes: Sequence[str] = ()

    def missing(self) -> list[str]:
        return [n for n in source_order(self.order, self.policy) if n not in self.sources]

    def run(self, job: Job, spec: StyleSpec, *, clock: Clock = _utc_now) -> AssetManifest:
        """Source every beat of `work/plan.validated.json`, write `work/assets.json`,
        `out/rights.json` and `out/credits.md`. Every candidate rejected, every judge
        note and the spent judge budget are `job.log` lines. The beats the job record
        lists as `replaced` (096) take the replacement ladder."""
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
            clips=self.clips,
            clip_order=self.clip_order,
            topic=topic_line(job_dir),
            log=lambda line: jobs.note(job, line, now=clock),
            clock=clock,
            # 096: read afresh, the editor may have marked beats since `job` was loaded
            replaced=frozenset(jobs.load(job_dir).record.replaced),
        )
        manifest.stickers = self._stickers(job, validated.picture, clock=clock)
        manifest.highlights = find_highlights(
            validated.picture, manifest, job_dir=job_dir,
            finder=self.lines.bind(job) if self.lines is not None else None,
            log=lambda line: jobs.note(job, line, now=clock),
        )  # fmt: skip
        write_manifest(job_dir, manifest)
        rights.write(job_dir, manifest, validated.picture)
        return manifest

    def _stickers(self, job: Job, plan: PicturePlan, *, clock: Clock) -> list[StickerRecord]:
        """062 (2): the plan's stickers fetched at job time (never at render time) and
        copied into the job; each one that cannot be is dropped with a job.log line."""
        def log(line: str) -> None:
            jobs.note(job, line, now=clock)

        if self.stickers is None:
            for beat in plan.beats:
                for sticker in beat.stickers:
                    log(f"sticker: {beat.id}: {sticker.name!r} dropped, no sticker source is "
                        "configured (062)")  # fmt: skip
            return []
        fetched_at = clock().isoformat(timespec="seconds")
        return self.stickers.source(plan, job_dir=job.path, log=log, fetched_at=fetched_at)


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


def lines_from_settings(settings: Settings, ledger: Callable[[], Ledger]) -> LineFinder | None:
    """078: the highlight's line finder rides the judge `RELEVANCE_JUDGE` names - `none`
    finds nothing (every highlight is dropped, logged), `fake` the fake, `api` one vision
    call on `RELEVANCE_JUDGE_MODEL`."""
    if settings.relevance_judge == "none":
        return None
    if settings.relevance_judge == "fake":
        return FakeLineFinder()
    return VisionLineFinder(
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
    `owner` and `generate` in the order are the fixed bookends and build nothing.

    058: the same two keys build the clip sources (Pexels video, then Pixabay video)
    for the `clip` beats, for whichever of the two is in the order with its key set."""
    order = parse_order(settings.asset_sources)
    wanted = source_order(order, settings.asset_policy)
    sources: dict[str, ImageSource] = {}
    clips: dict[str, ClipSource] = {}
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
            clips["pexels"] = PexelsClipSource(api_key=settings.pexels_api_key)
        elif name == "pixabay" and settings.pixabay_api_key is not None:
            sources["pixabay"] = PixabayImageSource(api_key=settings.pixabay_api_key)
            clips["pixabay"] = PixabayClipSource(api_key=settings.pixabay_api_key)
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
        lines=lines_from_settings(settings, ledger),
        clips={name: clips[name] for name in CLIP_ORDER if name in clips},
        stickers=live_shelf(settings.shortsmith_data_dir),  # 062: free, no key
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
