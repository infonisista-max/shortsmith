"""The reference inventory tool (ticket 036; decision 10.3, user story 49).

    python -m shortsmith.reference inventory <url> [--category facts] [--tier A]
    python -m shortsmith.reference inventory --all
    python -m shortsmith.reference gaps

Every short so far is drawn from one hand-written style spec; nothing in the system
read a reference. This tool turns a reference link into a written inventory of
techniques (layouts, effects, transitions, text look, sound timing, the hook) and a gap
report against what the renderer can draw. It learns technique, never content: no video
is downloaded or stored, only JSON and Markdown are written.

The link is normalised to a plain watch URL (`normalise`) and sent, as a URL, to a
`ReferenceAnalyser` (`reference.gemini`: one direct REST call with the versioned prompt
`prompts/inventory_<PROMPT_VERSION>.md`, the video sampled at `REFERENCE_FPS`). The
answer is parsed into `InventoryAnswer` (`parse_answer`), every `component` label
checked against the renderer's registry - an unknown name becomes `unregistered`, the
model's own `name` for the technique is kept - and wrapped with what code knows
(`ReferenceInventory.from_answer`: the link's category and tier, the model, the fps,
the prompt version, the tokens used, and the per-10 s counts computed from the lists)
into `docs/reference/inventory/<video_id>.json`. Every figure is ESTIMATED: model-observed
on the frames, timestamps approximate; the JSON says so in `tag`.

A malformed answer is retried once with the reasons and the previous reply (the planner's
8.2 shape); a second failure stops with one message naming the video and writes no
partial JSON. Under `--all` a failing video (private, removed, refused) logs its HTTP
status and the tool moves on to the next link in `docs/references.md`, whose section
headings give each link its tier and category (`links_in`). Every request logs the
tokens it used, so a price change after the preview is visible in the log.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from typing import Literal, get_args

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shortsmith.reference.gemini import AnalyserError, Answer, ReferenceAnalyser, Usage

PROMPT_VERSION = "v1"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
REPO_ROOT = Path(__file__).resolve().parents[3]
COMPONENTS_MD = REPO_ROOT / "docs" / "components.md"
REFERENCES_MD = REPO_ROOT / "docs" / "references.md"
# 036: the facts set lives beside the operator-edited references file until he pastes it
# in (his permission settings deny the agent that file); the tool reads both.
FACTS_MD = REPO_ROOT / "docs" / "reference" / "references-facts.md"
REFERENCES_FILES: tuple[Path, ...] = (REFERENCES_MD, FACTS_MD)
INVENTORY_DIR = REPO_ROOT / "docs" / "reference" / "inventory"
UNREGISTERED = "unregistered"
WATCH_URL = "https://www.youtube.com/watch?v={id}"
ATTEMPTS = 2  # the call, then one retry with the reasons, then stop
UNKNOWN_CATEGORY = "unknown"
DEFAULT_TIER: Tier = "A"

Tier = Literal["A", "B"]
Layout = Literal[
    "full_still",
    "full_footage",
    "card",
    "split",
    "grid",
    "text_only",
    "presenter_full",
    "presenter_circle",
    "map",
    "chart",
    "other",
]
Background = Literal[
    "still_photo", "moving_footage", "generated_or_animated", "solid_or_gradient", "blur"
]
FootageKind = Literal["stock", "archival_or_news", "ai_generated", "screen_recording", "animation"]
Treatment = Literal["slow_motion", "speed_ramp", "zoom", "colour_grade", "overlay"]
Emphasis = Literal["word", "number", "image", "speaker"]
SfxKind = Literal["whoosh", "hit", "riser", "click", "ding", "other"]

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = frozenset({"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"})
_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)
_COMPONENT_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|([^\n]*)$")
_HEADING_TIER = re.compile(r"\bTier ([AB])\b")
_HEADING_CATEGORY = re.compile(r"category `([a-z_]+)`")
_LINK_LINE = re.compile(r"^- (https?://\S+)\s*(.*)$")
_CREATOR_TITLE = re.compile(r'^[—–-]?\s*(.+?),\s*"(.+)"\s*$')


class ReferenceError(Exception):
    """The tool stops on this video: a link that is not a YouTube video, an answer
    that did not parse after the retry, or an analyser that could not answer."""


class AnswerInvalid(Exception):
    """The reply is not an `InventoryAnswer`; `reasons` are one line per problem."""

    def __init__(self, reply: str, reasons: Sequence[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reply = reply
        self.reasons = list(reasons)


# --- the URL ------------------------------------------------------------------------------


def video_id(url: str) -> str:
    """The eleven-character id of a shorts, youtu.be or watch link, tracking dropped."""
    try:
        parsed = httpx.URL(url.strip())
    except (httpx.InvalidURL, TypeError):
        raise ReferenceError(f"{url!r} is not a URL") from None
    host = parsed.host.removeprefix("www.")
    if host not in _YOUTUBE_HOSTS:
        raise ReferenceError(f"{url} is not a YouTube link")
    segments = [s for s in parsed.path.split("/") if s]
    candidate = ""
    if host == "youtu.be":
        candidate = segments[0] if segments else ""
    elif segments[:1] == ["watch"]:
        candidate = parsed.params.get("v", "")
    elif len(segments) == 2 and segments[0] in {"shorts", "embed", "live", "v"}:
        candidate = segments[1]
    if not _VIDEO_ID.match(candidate):
        raise ReferenceError(f"{url} does not name a YouTube video")
    return candidate


def normalise(url: str) -> str:
    """`https://www.youtube.com/watch?v=<id>`: the one form every link takes."""
    return WATCH_URL.format(id=video_id(url))


# --- the inventory ----------------------------------------------------------------------------


class Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_s: float
    end_s: float
    layout: Layout
    background: Background
    footage_kind: FootageKind | None = None
    clip_s: float | None = None
    treatment: list[Treatment] = Field(default_factory=lambda: [])
    note: str = ""

    @property
    def length_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)


class Effect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_s: float
    duration_s: float
    emphasis: Emphasis
    name: str
    description: str
    component: str


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_s: float
    duration_s: float
    name: str
    description: str = ""
    component: str


class TextLook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption_position: str
    caption_size: str
    caption_colours: str
    active_word: str
    title_entry: str
    number_entry: str


class SoundEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_s: float
    kind: SfxKind
    synced_to: str


class Sound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bed: bool
    bed_mood: str = ""
    effects: list[SoundEffect] = Field(default_factory=lambda: [])


class Hook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on_screen: str
    heard: str


class InventoryAnswer(BaseModel):
    """What the model returns: the schema in the prompt is generated from this."""

    model_config = ConfigDict(extra="forbid")

    duration_s: float = Field(gt=0)
    shots: list[Shot]
    effects: list[Effect]
    transitions: list[Transition]
    text: TextLook
    sound: Sound
    hook: Hook


class Counts(BaseModel):
    """Code's arithmetic over the lists and the duration, per 10 s of runtime."""

    shots_per_10s: float
    effects_per_10s: float
    sfx_per_10s: float


@dataclass(frozen=True)
class ReferenceLink:
    """One reference as `docs/references.md` lists it: the plain watch URL and what the
    operator said about it. `tier` and `category` are never pooled (10.3)."""

    url: str
    video_id: str
    category: str = UNKNOWN_CATEGORY
    tier: Tier = DEFAULT_TIER
    creator: str = ""
    title: str = ""
    note: str = ""


class ReferenceInventory(InventoryAnswer):
    """The answer plus what code knows about the request; the committed JSON."""

    tag: Literal["ESTIMATED"] = "ESTIMATED"
    tag_meaning: str = (
        "every figure is model-observed on frames sampled from the YouTube link; "
        "timestamps and durations are approximate"
    )
    video_id: str
    url: str
    category: str
    tier: Tier
    creator: str = ""
    title: str = ""
    model: str
    fps: float
    prompt_version: str
    analysed_on: str
    usage: Usage
    counts: Counts

    @classmethod
    def from_answer(
        cls,
        answer: InventoryAnswer,
        *,
        link: ReferenceLink,
        model: str,
        fps: float,
        usage: Usage,
        analysed_on: str,
    ) -> ReferenceInventory:
        return cls(
            **answer.model_dump(),
            video_id=link.video_id,
            url=link.url,
            category=link.category,
            tier=link.tier,
            creator=link.creator,
            title=link.title,
            model=model,
            fps=fps,
            prompt_version=PROMPT_VERSION,
            analysed_on=analysed_on,
            usage=usage,
            counts=counts(answer),
        )


def counts(answer: InventoryAnswer) -> Counts:
    per = 10.0 / answer.duration_s
    return Counts(
        shots_per_10s=round(len(answer.shots) * per, 1),
        effects_per_10s=round(len(answer.effects) * per, 1),
        sfx_per_10s=round(len(answer.sound.effects) * per, 1),
    )


# --- the prompt -----------------------------------------------------------------------------


def component_meanings(components_md: Path = COMPONENTS_MD) -> dict[str, str]:
    """Each component's one-line note from the table in `docs/components.md`."""
    meanings: dict[str, str] = {}
    if not components_md.is_file():
        return meanings
    for line in components_md.read_text(encoding="utf-8").splitlines():
        match = _COMPONENT_ROW.match(line.strip())
        if match is None:
            continue
        cells = [c.strip() for c in match.group(2).split("|")]
        tier = cells[0] if cells else ""
        note = cells[-2] if len(cells) >= 2 else ""
        meaning = note or (f"{tier} component" if tier else "")
        meanings[match.group(1)] = meaning
    return meanings


def build_prompt(registry: Collection[str], *, components_md: Path = COMPONENTS_MD) -> str:
    """The versioned instruction file with the registry names, their meanings from
    `docs/components.md`, the vocabulary and the schema generated from `InventoryAnswer`."""
    meanings = component_meanings(components_md)
    transitions = {"cut", "fade", "whip", "zoom", "spring", "wipe"}
    names = sorted(registry)
    components = "\n".join(
        f"- `{name}`: {meanings.get(name) or 'a renderer component'}"
        for name in names
        if name not in transitions
    )
    transition_names = ", ".join(f"`{n}`" for n in names if n in transitions)
    template = Template((PROMPTS_DIR / f"inventory_{PROMPT_VERSION}.md").read_text("utf-8"))
    return template.substitute(
        prompt_version=PROMPT_VERSION,
        components=components + f"\n- `{UNREGISTERED}`: none of the above draws it",
        transitions=transition_names + f", or `{UNREGISTERED}`",
        layouts=_words(Layout),
        backgrounds=_words(Background),
        footage_kinds=_words(FootageKind),
        treatments=_words(Treatment),
        emphases=_words(Emphasis),
        sfx_kinds=_words(SfxKind),
        schema=json.dumps(InventoryAnswer.model_json_schema(), indent=2),
    )


def _words(literal: object) -> str:
    return ", ".join(f"`{value}`" for value in get_args(literal))


def retry_prompt(prompt: str, invalid: AnswerInvalid) -> str:
    reasons = "\n".join(f"- {line}" for line in invalid.reasons)
    return (
        f"{prompt.rstrip()}\n\n## Your previous reply was rejected\n\n"
        "Fix every problem below and send the whole corrected object again.\n\n"
        f"Problems:\n{reasons}\n\nPrevious reply:\n\n```\n{invalid.reply[:4000]}\n```\n"
    )


# --- the answer -----------------------------------------------------------------------------


def parse_answer(reply: str, *, registry: Collection[str]) -> InventoryAnswer:
    """The reply's JSON (bare or fenced) validated as `InventoryAnswer`, every component
    label checked against the registry: an unknown one becomes `unregistered`."""
    text = _json_text(reply)
    if text is None:
        raise AnswerInvalid(reply, ["the reply holds no JSON object"])
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnswerInvalid(reply, [f"the reply is not valid JSON: {exc}"]) from exc
    if not isinstance(data, dict):
        raise AnswerInvalid(reply, [f"the reply is JSON but not an object ({type(data).__name__})"])
    try:
        answer = InventoryAnswer.model_validate(data)
    except ValidationError as exc:
        lines = [
            (".".join(str(p) for p in error["loc"]) or "(root)") + f": {error['msg']}"
            for error in exc.errors()
        ]
        raise AnswerInvalid(reply, lines) from exc
    known = set(registry)
    return answer.model_copy(
        update={
            "effects": [_labelled(e, known) for e in answer.effects],
            "transitions": [_labelled(t, known) for t in answer.transitions],
        }
    )


def _labelled[T: Effect | Transition](item: T, known: set[str]) -> T:
    if item.component in known:
        return item
    return item.model_copy(update={"component": UNREGISTERED})


def _json_text(reply: str) -> str | None:
    fenced = _FENCE.search(reply)
    if fenced is not None:
        return fenced.group(1).strip()
    stripped = reply.strip()
    if stripped.startswith("{"):
        return stripped
    start, end = reply.find("{"), reply.rfind("}")
    return reply[start : end + 1] if 0 <= start < end else None


# --- docs/references.md -----------------------------------------------------------------------


def links_in(references: Path | Sequence[Path] = REFERENCES_FILES) -> list[ReferenceLink]:
    """Every YouTube link in the file(s), with the tier and category its `##` heading
    names (`Tier A`, ``category `facts` ``; no category named means `explainer`) and,
    where the line reads `Creator, "Title"`, those two. A file that is not there is
    skipped; a link listed twice keeps its first entry."""
    files = [references] if isinstance(references, Path) else list(references)
    links: list[ReferenceLink] = []
    seen: set[str] = set()
    for path in files:
        if not path.is_file():
            continue
        for link in _links_in_file(path):
            if link.video_id not in seen:
                seen.add(link.video_id)
                links.append(link)
    return links


def _links_in_file(references_md: Path) -> list[ReferenceLink]:
    links: list[ReferenceLink] = []
    tier: Tier = DEFAULT_TIER
    category = "explainer"
    for raw in references_md.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            found_tier = _HEADING_TIER.search(line)
            found_category = _HEADING_CATEGORY.search(line)
            tier = "B" if found_tier is not None and found_tier.group(1) == "B" else "A"
            category = found_category.group(1) if found_category is not None else "explainer"
            continue
        match = _LINK_LINE.match(line)
        if match is None:
            continue
        try:
            vid = video_id(match.group(1))
        except ReferenceError:
            continue
        rest = match.group(2).strip()
        named = _CREATOR_TITLE.match(rest)
        links.append(
            ReferenceLink(
                url=WATCH_URL.format(id=vid),
                video_id=vid,
                category=category,
                tier=tier,
                creator=named.group(1).strip() if named else "",
                title=named.group(2).strip() if named else "",
                note="" if named else rest.lstrip("—– -").strip(),
            )
        )
    return links


def link_for(
    url: str,
    references: Path | Sequence[Path] = REFERENCES_FILES,
    *,
    category: str | None = None,
    tier: Tier | None = None,
) -> ReferenceLink:
    """The link as the references file(s) know it (or a bare one when it is not
    listed), with the command-line category and tier overriding what the file says."""
    vid = video_id(url)
    listed = {link.video_id: link for link in links_in(references)}
    link = listed.get(vid) or ReferenceLink(url=WATCH_URL.format(id=vid), video_id=vid)
    if category is not None:
        link = replace(link, category=category)
    if tier is not None:
        link = replace(link, tier=tier)
    return link


# --- the commands ---------------------------------------------------------------------------

Log = Callable[[str], None]
Today = Callable[[], str]


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def inventory(
    link: ReferenceLink,
    analyser: ReferenceAnalyser,
    *,
    out_dir: Path,
    registry: Collection[str],
    components_md: Path = COMPONENTS_MD,
    log: Log = print,
    today: Today = _today,
) -> ReferenceInventory:
    """One reference: the call, its one retry on a malformed answer, the JSON written
    only when the answer parsed. Raises `ReferenceError` naming the video otherwise."""
    prompt = build_prompt(registry, components_md=components_md)
    sent = prompt
    last: AnswerInvalid | None = None
    for _ in range(ATTEMPTS):
        try:
            answer = analyser.analyse(link.url, sent)
        except AnalyserError as exc:
            status = f"answered {exc.status}" if exc.status is not None else "could not answer"
            raise ReferenceError(
                f"{link.video_id} ({link.url}): the analyser {status}: {exc}"
            ) from exc
        log(_usage_line(link, answer, analyser.fps))
        try:
            parsed = parse_answer(answer.text, registry=registry)
        except AnswerInvalid as invalid:
            last = invalid
            log(f"{link.video_id}: the answer did not parse: {invalid}")
            sent = retry_prompt(prompt, invalid)
            continue
        made = ReferenceInventory.from_answer(
            parsed, link=link, model=answer.model, fps=analyser.fps, usage=answer.usage,
            analysed_on=today(),
        )  # fmt: skip
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{link.video_id}.json"
        path.write_text(made.model_dump_json(indent=2) + "\n", encoding="utf-8")
        log(
            f"{link.video_id}: {len(made.shots)} shots, {len(made.effects)} effects, "
            f"{len(made.transitions)} transitions, {len(made.sound.effects)} sound effects "
            f"-> {path}"
        )
        return made
    assert last is not None
    raise ReferenceError(
        f"{link.video_id} ({link.url}): the answer did not parse after one retry: {last}; "
        "nothing written"
    )


def inventory_all(
    links: Iterable[ReferenceLink],
    analyser: ReferenceAnalyser,
    *,
    out_dir: Path,
    registry: Collection[str],
    components_md: Path = COMPONENTS_MD,
    log: Log = print,
    today: Today = _today,
) -> int:
    """Every link, one request each; a failing one is logged and the next is tried.
    Returns how many failed."""
    failed = 0
    for link in links:
        try:
            inventory(
                link, analyser, out_dir=out_dir, registry=registry, components_md=components_md,
                log=log, today=today,
            )  # fmt: skip
        except ReferenceError as exc:
            failed += 1
            log(f"{exc}; moving on")
    return failed


def _usage_line(link: ReferenceLink, answer: Answer, fps: float) -> str:
    usage = answer.usage
    return (
        f"{link.video_id}: {answer.model} at {fps:g} fps: {usage.prompt_tokens} prompt tokens "
        f"({usage.video_tokens} video), {usage.output_tokens} output"
        + (f" + {usage.thoughts_tokens} thinking" if usage.thoughts_tokens else "")
        + f", {usage.total_tokens} total"
    )
