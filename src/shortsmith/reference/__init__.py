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

Card v2 (ticket 073) is the default prompt; `--prompt v1` stays possible. It keeps every
v1 field and adds what the rest of the learning work reads: the `script` (about, topic,
tone, language), its story `parts` with the music mood (and flavour) under each, the
`music_changes` between them, one `beats` row per shot (a `said` gist of at most
`SAID_WORDS_MAX` words, never a transcript; what it `shows`; how the two `match`), a
`motion` per effect and an `event`, `loudness` and length per sound effect, and the
shipped `styles` it informs (the trace table in `styles/README.md`, or `--style`).
Moods, flavours and topics are data (`shortsmith.vocab`), listed into the prompt and
checked after the schema; an unknown one takes the same one retry, then the reference
stops naming the field. `load_card` reads each card as its own version, and a reader of
v2 fields skips a v1 card with a log line (`v2_cards`).

Prompt v3 (ticket 086) is the default; `--prompt v2` stays possible and both write the
v2 schema, so every reader of v2 fields takes v2 and v3 cards alike (`uses_v2_schema`).
A card's `music_changes` must cover every boundary between neighbouring parts whose
mood or flavour differs (`uncovered_boundaries`): a miss is an invalid answer at write
time (the one retry, told to keep the parts), and a stored card that misses one is
skipped by `v2_cards` with a log line.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from string import Template
from typing import Any, Literal, cast, get_args

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from shortsmith import vocab
from shortsmith.contracts import BedHow, StoryPart
from shortsmith.reference.gemini import AnalyserError, Answer, ReferenceAnalyser, Usage

PromptVersion = Literal["v1", "v2", "v3"]
PROMPT_VERSION: PromptVersion = "v3"
PROMPT_VERSIONS: tuple[PromptVersion, ...] = get_args(PromptVersion)
V2_SCHEMA_VERSIONS = frozenset({"v2", "v3"})  # 086: v3 changed the text, not the schema
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
REPO_ROOT = Path(__file__).resolve().parents[3]
COMPONENTS_MD = REPO_ROOT / "docs" / "components.md"
REFERENCES_MD = REPO_ROOT / "docs" / "references.md"
# 036: the facts set lives beside the operator-edited references file until he pastes it
# in (his permission settings deny the agent that file); the tool reads both.
FACTS_MD = REPO_ROOT / "docs" / "reference" / "references-facts.md"
REFERENCES_FILES: tuple[Path, ...] = (REFERENCES_MD, FACTS_MD)
INVENTORY_DIR = REPO_ROOT / "docs" / "reference" / "inventory"
STYLES_README = REPO_ROOT / "styles" / "README.md"
UNREGISTERED = "unregistered"
WATCH_URL = "https://www.youtube.com/watch?v={id}"
ATTEMPTS = 2  # the call, then one retry with the reasons, then stop
UNKNOWN_CATEGORY = "unknown"
DEFAULT_TIER: Tier = "A"

# 074: `own` is our own delivered short run through the same tool; never a reference.
Tier = Literal["A", "B", "own"]
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
# v2 (073): the closed lists that live in code; moods, flavours and topics are data
# (`shortsmith.vocab`), checked after the schema.
Match = Literal["literal", "named_entity", "number", "illustrative", "metaphor"]
SfxEvent = Literal["text_pop", "sticker", "bubble", "flash", "cut", "stamp", "reveal", "other"]
Loudness = Literal["soft", "medium", "loud"]
MusicHow = BedHow  # 076: the plan's bed change speaks the cards' words
Entrance = Literal["pop_overshoot", "slide", "fade", "wipe", "draw", "scale", "other"]
Region = Literal["top", "middle", "bottom", "left", "right", "full"]
SAID_WORDS_MAX = 12

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = frozenset({"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"})
_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)
_COMPONENT_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|([^\n]*)$")
_HEADING_TIER = re.compile(r"\bTier ([AB])\b")
_HEADING_CATEGORY = re.compile(r"category `([a-z_]+)`")
_LINK_LINE = re.compile(r"^- (https?://\S+)\s*(.*)$")
_CREATOR_TITLE = re.compile(r'^[—–-]?\s*(.+?),\s*"(.+)"\s*$')
_TRACE_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|([^|]*)\|")
_TICKED = re.compile(r"`([A-Za-z0-9_-]{11})`")


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


# --- v2: the script, its parts, the music in each part, the beat table (073) ----------------


class Motion(BaseModel):
    """How an effect moves in: the data later effects are built from (083)."""

    model_config = ConfigDict(extra="forbid")

    entrance: Entrance
    entrance_s: float = Field(ge=0)
    size: float = Field(ge=0, le=1, description="share of the frame width")
    region: Region


class EffectV2(Effect):
    motion: Motion


class SoundEffectV2(SoundEffect):
    event: SfxEvent
    loudness: Loudness
    length_s: float = Field(ge=0)


class SoundV2(Sound):
    effects: list[SoundEffectV2] = Field(default_factory=lambda: [])  # pyright: ignore[reportIncompatibleVariableOverride]


class Script(BaseModel):
    model_config = ConfigDict(extra="forbid")

    about: str
    topic: str = Field(description="one name from the topic list")
    tone: str = Field(description="one to three words")
    language: str


class Part(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part: StoryPart
    start_s: float
    end_s: float
    music_mood: str | None = Field(
        description="one name from the mood list; null when no music plays in the part"
    )
    music_flavour: str | None = Field(default=None, description="one name from the flavours")


class MusicChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_s: float
    from_part: StoryPart
    to_part: StoryPart
    how: MusicHow


class Beat(BaseModel):
    """One shot: what was said over it (a gist, never a transcript) and what it shows."""

    model_config = ConfigDict(extra="forbid")

    start_s: float
    end_s: float
    said: str = Field(description=f"a gist in English, at most {SAID_WORDS_MAX} words")
    shows: str
    match: Match
    part: StoryPart
    layout: Layout
    effect: str | None = Field(description="a component name, `unregistered`, or null")
    sound: SfxKind | None

    @field_validator("said")
    @classmethod
    def _a_gist(cls, said: str) -> str:
        words = len(said.split())
        if words > SAID_WORDS_MAX:
            raise ValueError(
                f"said is {words} words; at most {SAID_WORDS_MAX} words, a gist, never a "
                "transcript"
            )
        return said


class InventoryAnswerV2(InventoryAnswer):
    """The v2 answer: v1's lists with motion and sound-event detail, plus the script."""

    effects: list[EffectV2]  # pyright: ignore[reportIncompatibleVariableOverride]
    sound: SoundV2  # pyright: ignore[reportIncompatibleVariableOverride]
    script: Script
    parts: list[Part]
    music_changes: list[MusicChange]
    beats: list[Beat]


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
        styles: Sequence[str] = (),
        version: PromptVersion | None = None,
    ) -> ReferenceInventory:
        """The card for the answer: a v2-schema card (with the `styles` it informs) for a
        v2 answer, a v1 card otherwise. `prompt_version` is the prompt that made it
        (`version`; `PROMPT_VERSION` for a v2 answer when not given)."""
        card: dict[str, Any] = answer.model_dump() | dict(
            video_id=link.video_id, url=link.url, category=link.category, tier=link.tier,
            creator=link.creator, title=link.title, model=model, fps=fps,
            analysed_on=analysed_on, usage=usage, counts=counts(answer),
        )  # fmt: skip
        if isinstance(answer, InventoryAnswerV2):
            return ReferenceInventoryV2.model_validate(
                card | {"prompt_version": version or PROMPT_VERSION, "styles": list(styles)}
            )
        return ReferenceInventory.model_validate(card | {"prompt_version": "v1"})


# v2's `effects` and `sound` narrow v1's; the card is read by its own version (`load_card`)
class ReferenceInventoryV2(InventoryAnswerV2, ReferenceInventory):  # pyright: ignore[reportIncompatibleVariableOverride]
    """A v2 card: every v1 field, the v2 answer, and the shipped styles it informs."""

    styles: list[str] = Field(default_factory=lambda: [])


def load_card(text: str) -> ReferenceInventory:
    """A card's JSON as its own version: a v1 card simply has no v2 fields."""
    data: object = json.loads(text)
    fields = cast(dict[str, object], data) if isinstance(data, dict) else {}
    if uses_v2_schema(fields.get("prompt_version")):
        return ReferenceInventoryV2.model_validate_json(text)
    return ReferenceInventory.model_validate_json(text)


def uses_v2_schema(version: object) -> bool:
    """Whether a card or answer of this prompt version has the v2 fields (v2 or v3)."""
    return version in V2_SCHEMA_VERSIONS


def v2_cards(
    cards: Iterable[ReferenceInventory], *, log: Log = print
) -> list[ReferenceInventoryV2]:
    """The cards a reader of v2 fields can use; each v1 card, and each card whose
    `music_changes` miss a boundary its parts show (086), is skipped with a log line."""
    found: list[ReferenceInventoryV2] = []
    for card in cards:
        if not isinstance(card, ReferenceInventoryV2):
            log(f"{card.video_id}: a v1 card has no v2 fields; skipped")
        elif missed := uncovered_boundaries(card):
            log(f"{card.video_id}: music_changes misses {_boundaries(missed)}; skipped")
        else:
            found.append(card)
    return found


Boundary = tuple[StoryPart, StoryPart]


def uncovered_boundaries(answer: InventoryAnswerV2) -> list[Boundary]:
    """Each pair of neighbouring parts whose music differs (mood or flavour, music
    starting or stopping included) with no change from the earlier to the later in
    `music_changes`. A change where nothing differs is allowed: a bed can change inside
    one mood."""
    covered = {(change.from_part, change.to_part) for change in answer.music_changes}
    return [
        (before.part, after.part)
        for before, after in pairwise(answer.parts)
        if (before.music_mood, before.music_flavour) != (after.music_mood, after.music_flavour)
        and (before.part, after.part) not in covered
    ]


def _boundaries(missed: Sequence[Boundary]) -> str:
    return ", ".join(f"{before} -> {after}" for before, after in missed)


def styles_for(video: str, readme: Path = STYLES_README) -> list[str]:
    """The shipped styles whose row in the trace table of `styles/README.md` names the
    reference among its sources."""
    if not readme.is_file():
        return []
    named: list[str] = []
    for line in readme.read_text(encoding="utf-8").splitlines():
        row = _TRACE_ROW.match(line.strip())
        if row is not None and video in _TICKED.findall(row.group(2)):
            named.append(row.group(1))
    return named


Log = Callable[[str], None]


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


def build_prompt(
    registry: Collection[str],
    *,
    components_md: Path = COMPONENTS_MD,
    version: PromptVersion = PROMPT_VERSION,
    vocabulary: vocab.Vocabulary | None = None,
) -> str:
    """The versioned instruction file with the registry names, their meanings from
    `docs/components.md`, the vocabulary and the schema generated from the answer model.
    v2 adds the closed lists: moods, flavours and topics read from the data files
    (`vocabulary`, loaded when not given), the rest from the schema's literals."""
    meanings = component_meanings(components_md)
    transitions = {"cut", "fade", "whip", "zoom", "spring", "wipe", "flash"}  # 060 adds flash
    names = sorted(registry)
    components = "\n".join(
        f"- `{name}`: {meanings.get(name) or 'a renderer component'}"
        for name in names
        if name not in transitions
    )
    transition_names = ", ".join(f"`{n}`" for n in names if n in transitions)
    template = Template((PROMPTS_DIR / f"inventory_{version}.md").read_text("utf-8"))
    common = dict(
        prompt_version=version,
        components=components + f"\n- `{UNREGISTERED}`: none of the above draws it",
        transitions=transition_names + f", or `{UNREGISTERED}`",
        layouts=_words(Layout),
        backgrounds=_words(Background),
        footage_kinds=_words(FootageKind),
        treatments=_words(Treatment),
        emphases=_words(Emphasis),
        sfx_kinds=_words(SfxKind),
    )
    if version == "v1":
        return template.substitute(
            common, schema=json.dumps(InventoryAnswer.model_json_schema(), indent=2)
        )
    lists = vocabulary if vocabulary is not None else vocab.load()
    return template.substitute(
        common,
        moods=_meanings(lists.moods.moods),
        flavours=_meanings(lists.moods.flavours),
        topics=_meanings(lists.topics.topics),
        parts=_words(StoryPart),
        matches=_words(Match),
        events=_words(SfxEvent),
        loudnesses=_words(Loudness),
        hows=_words(MusicHow),
        entrances=_words(Entrance),
        regions=_words(Region),
        said_words_max=SAID_WORDS_MAX,
        schema=json.dumps(InventoryAnswerV2.model_json_schema(), indent=2),
    )


def _words(literal: object) -> str:
    return ", ".join(f"`{value}`" for value in get_args(literal))


def _meanings(entries: Mapping[str, vocab.Entry | vocab.Topic]) -> str:
    return "\n".join(f"- `{name}`: {entry.meaning}" for name, entry in entries.items())


def retry_prompt(prompt: str, invalid: AnswerInvalid) -> str:
    reasons = "\n".join(f"- {line}" for line in invalid.reasons)
    return (
        f"{prompt.rstrip()}\n\n## Your previous reply was rejected\n\n"
        "Fix every problem below and send the whole corrected object again.\n\n"
        f"Problems:\n{reasons}\n\nPrevious reply:\n\n```\n{invalid.reply[:4000]}\n```\n"
    )


# --- the answer -----------------------------------------------------------------------------


def parse_answer(
    reply: str,
    *,
    registry: Collection[str],
    version: PromptVersion = PROMPT_VERSION,
    vocabulary: vocab.Vocabulary | None = None,
) -> InventoryAnswer:
    """The reply's JSON (bare or fenced) validated as the version's answer model, every
    component label checked against the registry: an unknown one becomes `unregistered`.
    A v2 answer's moods, flavours and topic must be in the data files (`vocabulary`,
    loaded when not given); an unknown one is invalid, naming the field."""
    model = InventoryAnswerV2 if uses_v2_schema(version) else InventoryAnswer
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
        answer = model.model_validate(data)
    except ValidationError as exc:
        lines = [
            (".".join(str(p) for p in error["loc"]) or "(root)") + f": {error['msg']}"
            for error in exc.errors()
        ]
        raise AnswerInvalid(reply, lines) from exc
    known = set(registry)
    update: dict[str, object] = {
        "effects": [_labelled(e, known) for e in answer.effects],
        "transitions": [_labelled(t, known) for t in answer.transitions],
    }
    if isinstance(answer, InventoryAnswerV2):
        unknown = _unknown_labels(answer, vocabulary if vocabulary is not None else vocab.load())
        missed = uncovered_boundaries(answer)
        if missed:
            unknown.append(
                f"music_changes: the parts' music differs at {_boundaries(missed)} but no "
                "change is listed there; keep `parts` as they are; add the missing "
                "`music_changes` entry"
            )
        if unknown:
            raise AnswerInvalid(reply, unknown)
        update["beats"] = [
            b if b.effect is None or b.effect in known else b.model_copy(
                update={"effect": UNREGISTERED}
            )
            for b in answer.beats
        ]  # fmt: skip
    return answer.model_copy(update=update)


def _unknown_labels(answer: InventoryAnswerV2, lists: vocab.Vocabulary) -> list[str]:
    """One line per mood, flavour or topic the data files do not list, naming the field."""
    moods, flavours = lists.moods.moods, lists.moods.flavours
    lines: list[str] = []
    if answer.script.topic not in lists.topics.topics:
        lines.append(
            f"script.topic: {answer.script.topic!r} is not a topic in topics.yaml "
            f"({', '.join(lists.topics.topics)})"
        )
    for i, part in enumerate(answer.parts):
        if part.music_mood is not None and part.music_mood not in moods:
            lines.append(
                f"parts.{i}.music_mood: {part.music_mood!r} is not a mood in moods.yaml "
                f"({', '.join(moods)})"
            )
        if part.music_flavour is not None and part.music_flavour not in flavours:
            lines.append(
                f"parts.{i}.music_flavour: {part.music_flavour!r} is not a flavour in "
                f"moods.yaml ({', '.join(flavours)})"
            )
    return lines


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
    version: PromptVersion = PROMPT_VERSION,
    vocabulary: vocab.Vocabulary | None = None,
    styles: Sequence[str] | None = None,
    topic: str | None = None,
    styles_readme: Path = STYLES_README,
    video: Path | None = None,
    name: str | None = None,
) -> ReferenceInventory:
    """One reference: the call, its one retry on a malformed answer, the JSON written
    only when the answer parsed. Raises `ReferenceError` naming the video otherwise.
    A v2 card's `styles` are the operator's (`styles`) or the trace table's, and an
    operator `topic` replaces the model's. 074: `video` is a local file analysed in
    place of the link's URL (our own short), and `name` the JSON's file name in
    `out_dir` (`<video_id>.json` when not given)."""
    lists = vocabulary if vocabulary is not None or version == "v1" else vocab.load()
    if topic is not None and lists is not None and topic not in lists.topics.topics:
        raise ReferenceError(f"{topic!r} is not a topic in topics.yaml")
    informs = list(styles) if styles is not None else styles_for(link.video_id, styles_readme)
    prompt = build_prompt(
        registry, components_md=components_md, version=version, vocabulary=lists
    )
    sent = prompt
    last: AnswerInvalid | None = None
    for _ in range(ATTEMPTS):
        try:
            answer = (
                analyser.analyse(link.url, sent)
                if video is None
                else analyser.analyse_file(video, sent)
            )
        except AnalyserError as exc:
            status = f"answered {exc.status}" if exc.status is not None else "could not answer"
            raise ReferenceError(
                f"{link.video_id} ({link.url}): the analyser {status}: {exc}"
            ) from exc
        log(_usage_line(link, answer, analyser.fps))
        try:
            parsed = parse_answer(
                answer.text, registry=registry, version=version, vocabulary=lists
            )
        except AnswerInvalid as invalid:
            last = invalid
            log(f"{link.video_id}: the answer did not parse: {invalid}")
            sent = retry_prompt(prompt, invalid)
            continue
        if topic is not None and isinstance(parsed, InventoryAnswerV2):
            parsed = parsed.model_copy(
                update={"script": parsed.script.model_copy(update={"topic": topic})}
            )
        made = ReferenceInventory.from_answer(
            parsed, link=link, model=answer.model, fps=analyser.fps, usage=answer.usage,
            analysed_on=today(), styles=informs, version=version,
        )  # fmt: skip
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / (name or f"{link.video_id}.json")
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
    version: PromptVersion = PROMPT_VERSION,
    vocabulary: vocab.Vocabulary | None = None,
) -> int:
    """Every link, one request each; a failing one is logged and the next is tried.
    Returns how many failed."""
    if vocabulary is None and uses_v2_schema(version):
        vocabulary = vocab.load()
    failed = 0
    for link in links:
        try:
            inventory(
                link, analyser, out_dir=out_dir, registry=registry, components_md=components_md,
                log=log, today=today, version=version, vocabulary=vocabulary,
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
