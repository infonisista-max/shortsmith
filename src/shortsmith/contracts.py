"""Shared Pydantic models (PRD "Global contracts").

Transcript family, the planner-facing PlanRequest / PicturePlan / SoundStory (2.3,
8.1), CaptionPage (6.1), the validator's ValidatedPlan with its clamps (8.2, ticket
009), the retry feedback a rejected call is re-sent with, the asset step's
AssetManifest and the RightsRow of the rights log (016), and the RenderSpec (004).
Planner-facing models use `extra="forbid"` so the JSON schema generated from them is
the single source of truth embedded in the planner prompt; plan JSON is
engine-agnostic (no render-engine terms in field names or values). QaReport lives in
`qa.technical`; CriticReport (033) is here, and so are the job record's ledger row,
phone rating, critic summary and audience (`CostRow`, `Rating`, `CriticSummary`,
`Performance`; `jobs` re-exports them) so that `Meta`, the `out/meta.json` record of
035 (10.4), can carry them without a cycle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Word(StrictModel):
    """One spoken word with final times in seconds (decision 6.1: never touched by the planner)."""

    text: str
    start: float
    end: float
    segment: int

    @model_validator(mode="after")
    def _end_after_start(self) -> Word:
        if self.end < self.start:
            raise ValueError(
                f"word {self.text!r} ends ({self.end}) before it starts ({self.start})"
            )
        return self


class Segment(StrictModel):
    """ASR segment with its confidence flags (research §6 fix pass reads these)."""

    start: float
    end: float
    avg_logprob: float
    low_confidence: bool = False
    no_speech: bool = False

    @model_validator(mode="after")
    def _end_after_start(self) -> Segment:
        if self.end < self.start:
            raise ValueError(f"segment ends ({self.end}) before it starts ({self.start})")
        return self


class Transcript(StrictModel):
    language: str = "und"
    duration_s: float
    segments: list[Segment]
    words: list[Word]


ReferenceKind = Literal["image", "clip"]


class ReferenceRecord(StrictModel):
    """One row of `input/refs.json` (decision 2.2): the first rows of the rights log.

    `file` is relative to the job's `input/` directory. Reference clips are stills in
    v1 (1.3); their `kind` is `clip` here and `clip_frame` once a frame is extracted.
    """

    id: str
    file: str
    kind: ReferenceKind
    caption: str
    original_name: str
    width: int
    height: int
    size_bytes: int
    rights: Literal["owner_supplied"] = "owner_supplied"


# --- planner input (decision 2.3) ---------------------------------------------------


class PlanStyle(StrictModel):
    """The loaded style spec as the planner sees it: numbers + prose (1.2).

    `numbers` is the spec's front matter as plain data (`styles.StyleSpec.numbers()`)
    and `prose` its five sections; `status` is `draft` only when a draft is being
    smoke-rendered (1.4), never for a user job.
    """

    name: str
    status: Literal["shipped", "draft"] = "shipped"
    numbers: dict[str, object] = {}
    prose: str = ""


PlanReferenceKind = Literal["image", "clip_frame"]


class PlanReference(StrictModel):
    """A user reference as a captioned line, never pixels (1.3, 2.3)."""

    id: str
    kind: PlanReferenceKind
    caption: str
    width: int
    height: int


class Constraints(StrictModel):
    max_duration_s: float
    target_duration_s: float


AssetPolicy = Literal["any", "rights_safe"]


class ExampleRow(StrictModel):
    """One shot of a worked example (077): a v2 card's beat row as the planner reads it,
    its `effect` already a registered component, "(no equivalent: skip)" or empty."""

    start_s: float
    end_s: float
    said: str
    shows: str
    match: str
    part: str
    layout: str
    effect: str = ""
    sound: str = ""


class WorkedExample(StrictModel):
    """A top short's beat table (077), chosen by style, topic, then Tier B first."""

    video_id: str
    tier: str
    topic: str
    tone: str = ""
    rows: list[ExampleRow] = []


class PlanRequest(StrictModel):
    """Everything the planner receives; nothing from disk, no pixels (2.3). 077: the
    job's `topic` (None: style only) and the two worked examples code picked."""

    brief: str
    style: PlanStyle
    style_note: str
    transcript: Transcript
    references: list[PlanReference]
    constraints: Constraints
    asset_policy: AssetPolicy
    topic: str | None = None
    examples: list[WorkedExample] = []
    # 076: one line per reference v2 card - topic, tone, mood per part, changes and how -
    # for the sound call's "Music in top shorts" (`reference.music`).
    music: list[str] = []


# --- picture plan (decisions 3.1, 3.2, 3.4, 4.1, 4.2, 8.1, 9.2, 9.4) ----------------

Mode = Literal["full", "pip", "off"]
# 055: `cold_open` left with the lift; a `full` beat is an emotional line or an argument turn.
ReasonTag = Literal["emotional_line", "argument_turn"]

# 055: `hook_cards` left the tier with the hook; the short opens in `pip` over images.
# 058 (4.1 as amended): `clip` is a full-screen moving shot from a free stock video
# library, always muted, under the PIP circle and the captions like `photo`; only on
# concept beats, never for a named entity.
Tier1Kind = Literal[
    "photo",
    "card",
    "clip",
    "stamp",
    "lower_third",
    "finale",
    "presenter_full",
    "presenter_pip",
    "list",
    "chart",
    "split",
    "wall",
    "map",
    "infographic",
    "pin_drop",
    "route_arrow",
    "label_flyin",
    "counter",
    "object_path",
]
Tier2Kind = Literal["parallax", "vector_illustration"]
Kind = Tier1Kind | Tier2Kind
TIER1_KINDS: tuple[Tier1Kind, ...] = get_args(Tier1Kind)
TIER2_KINDS: tuple[Tier2Kind, ...] = get_args(Tier2Kind)

# Motion-graphics kinds that animate on top of a base kind (9.3: pin drops, route
# arrows and moving objects live on a map; label fly-ins on an infographic; counters
# on a chart or a number).
OverlayKind = Literal["pin_drop", "route_arrow", "object_path", "label_flyin", "counter"]

# One motion per non-presenter beat (4.1); names are engine-agnostic.
Motion = Literal[
    "ken_burns_in",
    "ken_burns_out",
    "pan_left",
    "pan_right",
    "push_in",
    "reveal",
    "draw_on",
    "count_up",
    "fly_in",
    "travel",
]
SubjectKind = Literal["entity", "concept", "number", "quote"]
Depicts = Literal["named_entity", "scene"]
Render = Literal["illustration", "photoreal"]  # 4.2: a named entity is never photoreal
SourceIntent = Literal["search", "generate", "reuse"]
# 9.4 as amended by 060: `flash` is the seventh enter, a full-frame colour flash peaking
# on the cut (the picture layers only; the PIP circle and the captions never blink).
Transition = Literal["cut", "fade", "whip", "zoom", "spring", "wipe", "flash"]
EventKind = Literal["stamp", "ring", "lower_third", "none"]


class Span(StrictModel):
    start: float
    end: float

    @model_validator(mode="after")
    def _end_after_start(self) -> Span:
        if self.end < self.start:
            raise ValueError(f"span ends ({self.end}) before it starts ({self.start})")
        return self


class Event(StrictModel):
    """At most one landed event per beat (3.1); `text` for stamps and lower-thirds."""

    kind: EventKind = "none"
    text: str | None = None


class SetPieceItem(StrictModel):
    """One row, pane or cell of a `list`, `split` or `wall` beat (4.1, 5.2; ticket 027).

    `asset_id` points at an asset another beat sources, so an item adds nothing to the
    asset count and spends no reuse (4.3). A `list` row may be text only; a `split`
    pane and a `wall` cell always name one."""

    text: str = ""
    asset_id: str | None = None


ChartForm = Literal["bar", "line", "comparison"]
LabelAnchor = Literal["left", "center", "right"]


class SeriesPoint(StrictModel):
    """One point of a `chart` beat's series (9.2): its axis label and its value. The
    chart is drawn in code from these numbers; the planner never sends a picture of a
    chart and never puts the numbers inside a generated image."""

    label: str
    value: float


class PlanLabel(StrictModel):
    """One label of an `infographic` beat (9.3): the text and where it sits on the base
    picture as percentages of that picture, with the edge `x` pins. Labels are rendered
    in code over a label-free base (5.5), never generated into it."""

    text: str
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)
    anchor: LabelAnchor = "center"


MapObject = Literal["plane", "ship", "arrow"]


class MapMarker(StrictModel):
    """One marker of a `map` beat (9.3), by name. `lat` / `lon` are accepted so a planner
    that writes them is not rejected, and ignored: the point comes from the gazetteer or
    the geocoding fallback, never from the plan (ticket 020)."""

    name: str
    lat: float | None = None
    lon: float | None = None


class MapPlan(StrictModel):
    """What a `map` beat asks for (9.3, ticket 020): the region by name ("India",
    "South Asia", "Maharashtra") or a `bbox` of west, south, east, north degrees; the
    markers; the route as place names in order (028 draws it on); and the object that
    travels the route (028)."""

    region: str = ""
    bbox: tuple[float, float, float, float] | None = None
    markers: list[MapMarker] = []
    route: list[str] = []
    object: MapObject | None = None


PopFill = Literal["yellow", "white", "accent"]


class TextPop(StrictModel):
    """One text pop (061; 4.1 as amended): 1-4 bold words pinned on the picture near
    the thing they name, at `{x, y, anchor}` in percent of the frame, popping in on the
    spoken word `word` (a transcript word index inside the beat). `fill` is the style's
    pop yellow, white, or the palette accent (for years and numbers). `at_s` is that
    word's start on the output timeline, written by the grammar when the plan is
    validated (as beat times are mapped onto the cut); the planner leaves it empty.
    Code keeps the pop inside the safe area, off the PIP circle, the captions and any
    detected face, and on screen to the end of its beat or `broll.motion.text_pop.
    hold_max_s`, whichever is first."""

    text: str
    word: int = Field(ge=0)
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)
    anchor: LabelAnchor = "center"
    fill: PopFill = "yellow"
    at_s: float | None = None


BubbleShape = Literal["speech", "thought"]


class Bubble(StrictModel):
    """One comic bubble (063; 4.1 as amended): a `speech` bubble (a rounded box with a
    tail) or a `thought` bubble (a cloud with a trail of dots) of words from the
    recording - what the speaker says someone said or thought, or his own question,
    shortened or put in the caption language, never a quote the recording does not
    carry. `first`-`last` are the transcript words (inclusive) the text came from; they
    are written to job.log beside the text. The tail points at `{x, y}` in percent of
    the frame: a person in the picture, or the PIP circle when the presenter is the one
    asking. `at_s` is the landing on the output timeline, written by the grammar (the
    first source word's time, the beat's start when the words came earlier; a second
    bubble on the beat lands `broll.motion.bubble.dialogue_gap_min_s`-`_max_s` after the
    first); the planner leaves it empty. Code keeps the body inside the safe area, off
    the captions, the PIP circle and any face (the tail points at it instead)."""

    shape: BubbleShape = "speech"
    text: str
    first: int = Field(ge=0)
    last: int = Field(ge=0)
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)
    at_s: float | None = None

    @model_validator(mode="after")
    def _run_in_order(self) -> Bubble:
        if self.last < self.first:
            raise ValueError(
                f"bubble {self.text!r}: last word {self.last} before first {self.first}"
            )
        return self


class Sticker(StrictModel):
    """One sticker (062; 4.1 as amended): a 3D emoji from the committed Fluent Emoji
    catalogue (`assets/stickers/catalog.yaml`) popping in on the spoken word `word` (a
    transcript word index inside the beat). The planner picks by `intent`, a catalogue
    tag, and may name one of that tag's rows in `name`, never a file; the grammar
    writes the tag's first row when `name` is empty. With no `{x, y}` it sits above the
    PIP circle (the "over his head" spot); otherwise near its subject at `{x, y}` in
    percent of the frame. `at_s` is the word's start on the output timeline, written by
    the grammar; the planner leaves it empty. Code keeps it inside the safe area, off
    the circle, the captions, the stamp and any face."""

    intent: str
    name: str = ""
    word: int = Field(ge=0)
    x: float | None = Field(default=None, ge=0.0, le=100.0)
    y: float | None = Field(default=None, ge=0.0, le=100.0)
    at_s: float | None = None

    @model_validator(mode="after")
    def _both_or_neither(self) -> Sticker:
        if (self.x is None) != (self.y is None):
            raise ValueError(
                f"sticker {self.intent!r}: give both x and y, or neither (above the PIP circle)"
            )
        return self


class Highlight(StrictModel):
    """The article highlighter (078; 4.1 as amended): a marker sweeps across `sentence`
    on the owner's uploaded article or document screenshot `asset_id` - the picture the
    beat shows - while the transcript words `words` (first, last, inclusive) say it.
    Owner screenshots only, never a made-up article. `at_s` and `end_s` are the first
    word's start and the last word's end on the output timeline, written by the grammar;
    the planner leaves them empty. The line boxes are found on the image by the judge
    model at sourcing (`assets.lines`)."""

    asset_id: str
    sentence: str = Field(min_length=1)
    words: tuple[int, int]
    at_s: float | None = None
    end_s: float | None = None

    @model_validator(mode="after")
    def _words_in_order(self) -> Highlight:
        first, last = self.words
        if first < 0 or last < first:
            raise ValueError(
                f"highlight {self.sentence!r}: last word {last} before first {first}"
            )
        return self


class CounterPlan(StrictModel):
    """The numbers of a `counter` overlay (029; 4.2, 9.2): the digits count from `start`
    to `target` over the beat and land on it. `unit` is written as a chart's is ("%",
    "crore"), `decimals` is the number's own precision; the style's digit grouping
    writes the rest."""

    start: float = 0.0
    target: float
    unit: str = ""
    decimals: int = Field(default=0, ge=0, le=3)


class Beat(StrictModel):
    id: str
    start: float
    end: float
    mode: Mode
    reason: ReasonTag | None = None
    kind: Kind
    overlays: list[OverlayKind] = []
    # 027: the set pieces only. `set_piece_title` is the list's header and the split's
    # title strip; `items` are its rows, panes or cells. 021: a `chart` may carry the
    # title too (its title strip).
    set_piece_title: str = ""
    items: list[SetPieceItem] = []
    # 021: the two infographic kinds carry their own data. `chart_form`, `series` and
    # `value_unit` belong to a `chart` beat, `labels` to an `infographic` beat.
    chart_form: ChartForm | None = None
    series: list[SeriesPoint] = []
    value_unit: str = ""
    labels: list[PlanLabel] = []
    # 020: a `map` beat's recipe; the map is drawn from bundled geodata (9.3).
    map: MapPlan | None = None
    # 029: the `counter` overlay's from/to values, unit and decimals.
    counter: CounterPlan | None = None
    # 061: text pops on a picture beat (photo, card, presenter full), at most
    # `broll.motion.text_pop.max_per_beat`, under `broll.text_pops_max_per_60s`.
    text_pops: list[TextPop] = []
    # 063: speech and thought bubbles on a picture beat, at most
    # `broll.motion.bubble.max_per_beat` (a dialogue pair), under `broll.bubbles_max_per_60s`.
    bubbles: list[Bubble] = []
    # 062: at most `broll.motion.sticker.max_per_beat` sticker on a picture beat, under
    # `broll.stickers_max_per_60s`.
    stickers: list[Sticker] = []
    # 078: the marker sweep over the owner's screenshot this beat shows, at most one, under
    # `broll.highlights_max_per_60s`.
    highlight: Highlight | None = None
    motion: Motion | None = None
    subject_kind: SubjectKind | None = None
    depicts: Depicts | None = None
    query: str = ""
    query_fallback: str = ""
    source_intent: SourceIntent | None = None
    asset_id: str | None = None
    enter: Transition = "cut"
    event: Event = Field(default_factory=Event)
    money_reveal: bool = False

    @model_validator(mode="after")
    def _end_after_start(self) -> Beat:
        if self.end <= self.start:
            raise ValueError(f"beat {self.id} ends ({self.end}) at or before its start")
        return self


class CutPlan(StrictModel):
    """Kept and dropped spans of the recording (8.1 as amended by 055): `drop` removes
    only silence, breaths and dead air, so every spoken word stays, once, in the
    speaker's order; the grammar rejects a cut that re-orders or drops speech. Pauses
    over the style's `cut.max_pause_s` are tightened by code, and the validated plan's
    `keep` is the tightened list."""

    keep: list[Span]
    drop: list[Span] = []


class CutList(StrictModel):
    """`work/cut.json` (031): the source spans the renderer cut, in output order, as
    `presenter.cut_list` derived them, so gate T10 reads the boundaries that were cut."""

    spans: list[Span]


class Finale(StrictModel):
    beat_id: str
    text: str


class WordRun(StrictModel):
    """A name or number the planner marks so no caption page splits it (6.1): word
    indices `first` to `last`, both included."""

    first: int
    last: int

    @model_validator(mode="after")
    def _last_not_before_first(self) -> WordRun:
        if self.last < self.first:
            raise ValueError(f"word run ends ({self.last}) before it starts ({self.first})")
        return self


# 10.3: the reference library's categories. The planner names one per short from this
# list (the grammar checks it, 033); the critic reads that category's pattern data and
# frames (039). `other` is for a short none of the seeded categories fits.
CATEGORIES: tuple[str, ...] = (
    "history",
    "geopolitics",
    "finance",
    "product",
    "motivation",
    "science",
    "technology",
    "health",
    "other",
)


class PicturePlan(StrictModel):
    """The picture call's output (8.1). Beat times are seconds on the recording's
    timeline as the planner wrote them; the grammar maps them onto the cut (055), so a
    validated plan's beats are output seconds. The short opens with the speaker's first
    words over the strongest images of the subject (3.4 as amended by 055): there is no
    hook object, no lifted line and no title card."""

    prompt_version: str
    cut: CutPlan
    beats: list[Beat]
    finale: Finale
    keywords: list[int] = []  # word indices, priority order (6.1)
    name_runs: list[WordRun] = []  # names and numbers never split across pages (6.1)
    title: str
    description: str
    hashtags: list[str] = []
    # 10.3 / 033: the short's subject category, one of `CATEGORIES`; the critic compares
    # the short against that category's reference shorts. A plan from before 033 reads
    # `other`.
    category: str = Field(
        default="other",
        description=f"the short's subject category, one of: {', '.join(CATEGORIES)}",
    )
    # 059: the fixed title strip's words - the topic in at most the style's
    # `broll.title_strip.words_max` words - where the style draws one; empty elsewhere.
    title_strip: str = Field(
        default="",
        description="only where the style carries broll.title_strip: the topic in at most "
        "its words_max words, shown at the top of the frame for the whole short; else empty",
    )


# --- sound story (decisions 7.1, 7.2, 8.1) ------------------------------------------


class MoodPoint(StrictModel):
    t: float
    level: float  # dB relative to the bed target; clipped to +4/-8 by 009 (7.3)


class BedQuery(StrictModel):
    theme: str
    mood: str
    energy: int = Field(ge=1, le=5)


# 070 (7.1 as amended at run04 QA): the closed cue palette. A tick marks a pop-in, a
# whoosh a transition, a ding an `idea` sticker; bass, drum and thump are the floor
# classes. The schema the planner reads lists them; the grammar refuses any other name
# (7.1) so the usual one retry applies, and the style says where each may sit.
CUE_KINDS: tuple[str, ...] = ("tick", "whoosh", "bass", "drum", "thump", "ding")


class Cue(StrictModel):
    beat_id: str
    intent: str = Field(
        json_schema_extra={"enum": list(CUE_KINDS)},
        description="one kind of the sound palette; section 1's sound rows say where each "
        "may sit",
    )
    at: Literal["start", "event", "end"]


# 076: the story parts the reference cards (073) score music by, and how the one bed change
# a short may carry sounds (the cards' `music_changes[].how`).
StoryPart = Literal["hook", "build_up", "reveal", "ending"]
STORY_PARTS: tuple[StoryPart, ...] = get_args(StoryPart)
BedHow = Literal["crossfade", "hard_cut", "drop_to_silence"]


class PartSpan(StrictModel):
    """One story part of this script as a beat range, first and last beat included."""

    part: StoryPart
    first_beat: str
    last_beat: str


class BedSegment(StrictModel):
    """076: the music from `part_from` on - one mood (and an optional flavour) of the
    closed list, never free words; code picks the bed from the approved library."""

    part_from: StoryPart
    mood: str = Field(description="one active mood of the list in the Music section")
    flavour: str | None = Field(
        default=None, description="one active flavour of that list, or null"
    )


class BedChange(StrictModel):
    """076: where the second segment's bed takes over (the first beat of its part) and
    how it sounds there."""

    at_beat: str
    how: BedHow


class SoundStory(StrictModel):
    prompt_version: str
    theme: str
    mood_curve: list[MoodPoint]
    # 7.2 as amended by 076: the words a Freesound fallback bed is searched with, and the
    # energy an approved bed is ranked by.
    bed_query: BedQuery
    cues: list[Cue]
    # 076: the script's story parts, the bed per part (1 segment, or 2 with a change).
    parts: list[PartSpan] = []
    bed: list[BedSegment] = []
    change: BedChange | None = None


# --- the audio catalogue (decision 7.2; ticket 022) ----------------------------------

AudioKind = Literal["bed", "sfx"]


class AudioTags(StrictModel):
    """The hand-written tags of one catalogue entry (7.2): `theme` and `mood` are what
    a bed is selected by, `intent` what a cue is matched by."""

    theme: list[str] = []
    mood: list[str] = []
    intent: list[str] = []
    # 075: a bed's regional colour, from `moods.yaml`'s `flavours` (approved library only).
    flavour: list[str] = []
    # 087: what a bed stands in for, from `BED_ROLES` (the operator's yes on the page).
    role: list[str] = []


# 087: the bed the director falls back to on a flavour or mood miss, before any search.
FACTS_DEFAULT = "facts_default"
BED_ROLES: tuple[str, ...] = (FACTS_DEFAULT,)


class AudioEntry(StrictModel):
    """One file of the tagged free library, in the 7.2 shape. `file` is relative to the
    catalogue, tags are hand-written at seed time and `duration_s` / `bpm` / `key` /
    `energy` are measured by a script; the planner reads the tags as text and never
    names a track."""

    id: str
    kind: AudioKind
    file: str
    source: str
    source_url: str = ""
    # 068: what the source itself calls the sound, kept as it answered; the planner-facing
    # tags are derived from these, never from the words it was searched with.
    source_name: str | None = None
    source_tags: list[str] = []
    licence: str
    author: str | None = None
    # 075: the credits line the source asks for (Openverse's attribution sentence, a
    # drop-folder file's sidecar), kept with the approved entry.
    credit: str | None = None
    duration_s: float
    bpm: float | None = None
    key: str | None = None
    tags: AudioTags = Field(default_factory=AudioTags)
    drop_points_s: list[float] = []
    loop_ok: bool = False
    energy: int = Field(ge=1, le=5)


class Catalogue(StrictModel):
    """`assets/audio/catalog.yaml`: the whole library as one list (7.2)."""

    entries: list[AudioEntry] = []


class AudioCandidate(StrictModel):
    """One hit of the runtime audio search (7.2; ticket 024) before it is fetched: what
    the source says about it (5.4: recorded; 054: only CC0 / CC BY is adopted), the page
    it lives on, the preview the adapter downloads and the original's download URL for
    the log. `id` is the source's own id; the catalogue entry it becomes is keyed by it."""

    id: str
    name: str
    kind: AudioKind
    tags: list[str] = []
    licence: str
    licence_url: str = ""
    author: str | None = None
    page_url: str
    preview_url: str
    download_url: str = ""
    duration_s: float = 0.0


class BalanceWindow(StrictModel):
    """076: one stretch of a two-bed short measured on its own - a bed's segment (its
    median under the voice, its speech-band margin) or the crossfade between them."""

    name: str
    start_s: float
    end_s: float
    bed_under_voice_db: float | None = None
    speech_band_margin_db: float | None = None


class BalanceReport(StrictModel):
    """`work/stems/balance.json` (7.3): what the mix measured, and what the style asked
    for. `problems` is empty when the mix is inside the acceptance band."""

    voice_db: float
    bed_median_db: float | None = None
    bed_under_voice_db: float | None = None
    duck_db: float | None = None
    speech_band_margin_db: float | None = None
    bed_accept_db: tuple[float, float]
    speech_band_margin_min_db: float
    # 069: the ceiling a bed the phone speaker can play stays under; None on a job
    # measured before it existed.
    speech_band_margin_max_db: float | None = None
    duck_max_db: float
    cues: int = 0
    problems: list[str] = []
    # 056 (1): every repair the mix made on its way to this report (the dip depths in
    # dB, the lower bed, the beds dropped), the dip the shipped bed carries, and - when
    # no bed passed and the short went out voice-and-hits - which bed was dropped why.
    repairs: list[str] = []
    dip_db: float | None = None
    bed_dropped: str | None = None
    # 076: with a bed change, each segment and the crossfade measured on its own.
    windows: list[BalanceWindow] = []


class CueRecord(StrictModel):
    """One cue on the SFX stem, from where it fires to where its file ends."""

    beat_id: str
    intent: str
    entry_id: str
    start_s: float
    end_s: float


class CueSheet(StrictModel):
    """`work/stems/cues.json` (023): the cues the SFX stem holds, so gate T6 can name
    the cue a sweep hit falls in."""

    cues: list[CueRecord] = []


# --- the validated plan (decision 8.2; ticket 009) -----------------------------------


class Clamp(StrictModel):
    """One silent fix the validator made (8.2): the decision whose number it applied,
    the beat it touched (None for a plan-level field) and what changed."""

    rule: str
    beat_id: str | None = None
    message: str


class Violation(StrictModel):
    """One rejection: beat id (None for a plan-level rule), the decision number and
    the message the planner gets back verbatim on the retry."""

    rule: str
    beat_id: str | None = None
    message: str

    def __str__(self) -> str:
        return f"{self.beat_id or 'plan'} ({self.rule}): {self.message}"


class ValidatedPlan(StrictModel):
    """The picture plan with its boundaries snapped and its fields clamped, the sound
    story clamped, every clamp logged and the 3.4 / 4.3 warnings for the contact sheet.
    077: the job's `topic` and the video ids of the worked examples the planner saw."""

    picture: PicturePlan
    sound: SoundStory
    clamps: list[Clamp] = []
    warnings: list[str] = []
    topic: str | None = None
    examples: list[str] = []


class PlanFeedback(StrictModel):
    """What a rejected call is re-sent with (8.2): the previous output as JSON text
    and the violation list, one line each with beat id and rule."""

    previous: str
    violations: list[str]


# --- the critic report (decisions 10.2, 10.3; ticket 033) ------------------------------

# The E1-E10 rubric lines, in order: name and label.
CRITIC_LINES: tuple[tuple[str, str], ...] = (
    ("E1", "hook"),
    ("E2", "broll_relevance"),
    ("E3", "mode_variation"),
    ("E4", "density"),
    ("E5", "captions"),
    ("E6", "pip_framing"),
    ("E7", "sound"),
    ("E8", "payoff"),
    ("E9", "integrity"),
    ("E10", "embarrassment"),
)
CRITIC_NOTES_MAX = 5  # 10.3: up to five "fix in 5 minutes" notes
CriticStatus = Literal["scored", "unavailable"]


class CriticLine(StrictModel):
    """One rubric line: its name (E1-E10), its label, the 1-10 score and one reason."""

    name: str
    label: str
    score: int = Field(ge=1, le=10)
    reason: str


class CriticReport(StrictModel):
    """The editorial gate's verdict on one job (10.2): the ten lines in rubric order
    with one reason each, the overall 1-10, up to five fix notes, the model that scored
    it and whether it is advisory (10.2: advisory until the calibration streak of 034
    flips it). `unavailable` is a critic that could not answer - an API failure, a reply
    that was not the report - with the reason in `notes`; delivery is never blocked by
    it while advisory. `category` is the plan's (10.3); `notes` also carries what the
    inputs lacked (no reference data for the category, no opening strip)."""

    status: CriticStatus = "scored"
    lines: list[CriticLine] = []
    overall: int | None = Field(default=None, ge=1, le=10)
    fix_notes: list[str] = Field(default_factory=list, max_length=CRITIC_NOTES_MAX)
    model: str
    advisory: bool = True
    category: str = "other"
    notes: list[str] = []

    @model_validator(mode="after")
    def _shape_follows_status(self) -> CriticReport:
        if self.status == "unavailable":
            if self.lines or self.overall is not None:
                raise ValueError("an unavailable report carries no lines and no overall")
            return self
        expected = [name for name, _ in CRITIC_LINES]
        names = [line.name for line in self.lines]
        if names != expected:
            raise ValueError(f"lines must be {expected} in order, got {names}")
        if self.overall is None:
            raise ValueError("a scored report needs an overall")
        return self


# --- assets and rights (decisions 4.2, 4.4, 5.1, 5.3, 5.4, 5.6; ticket 016) ----------

# Where an asset came from (5.4). `library` is the audio catalogue (022).
# 062: `fluent_emoji` is Microsoft's Fluent Emoji set (MIT), the stickers' one source.
Origin = Literal[
    "owner_supplied", "web", "commons", "openverse", "pexels", "pixabay", "generated", "library",
    "fluent_emoji",
]
SearchOrigin = Literal["web", "commons", "openverse", "pexels", "pixabay"]
# 058: the free stock video libraries a `clip` may come from (5.1 as amended).
ClipOrigin = Literal["pexels", "pixabay"]
# 058: `clip` is a moving asset (a stock video file), beside the stills.
AssetKind = Literal["image", "clip_frame", "clip"]
RightsKind = Literal["image", "clip_frame", "clip", "music", "sfx", "sticker"]
# How a beat's asset is drawn (5.3): full-bleed photo, framed card, a full-screen
# moving clip (058), or no asset at all (rung 4: the presenter PIP over the style
# gradient with a stamp; 4.4).
Treatment = Literal["photo", "card", "clip", "gradient"]


class Candidate(StrictModel):
    """One search hit from an `ImageSource` (5.1): where it lives and its reported size.
    The fetched file's real dimensions are what classification reads (5.3). 058: a video
    candidate carries its `duration_s` too (0 on a still), so a clip shorter than its
    beat is skipped before anything is downloaded."""

    url: str
    page_url: str = ""
    thumb_url: str = ""  # the small preview the relevance judge looks at (5.2)
    width: int
    height: int
    author: str | None = None
    licence: str = "unknown"
    duration_s: float = 0.0


class Generated(StrictModel):
    """The generation record of a generated asset (5.4, 5.5)."""

    model: str
    prompt: str
    render: Render
    depicts: Depicts


class JudgeVerdict(StrictModel):
    """The relevance judge's verdict on the chosen candidate (5.2; ticket 017):
    `score` 0-3, `reasons` only from the fixed list in `assets.judge.REASONS`."""

    model: str
    score: int
    reasons: list[str] = []


class AssetRecord(StrictModel):
    """One unique asset the short uses; the rights row (5.4) is derived from it.
    `file` is relative to the job directory. 058: a `clip` record is a muted stock
    video file with its `duration_s` (0 on a still)."""

    id: str
    kind: AssetKind = "image"
    origin: Origin
    source_url: str = ""
    page_url: str = ""
    licence: str = "unknown"
    author: str | None = None
    generated: Generated | None = None
    judge: JudgeVerdict | None = None
    file: str
    sha256: str
    width: int
    height: int
    fetched_at: str
    duration_s: float = 0.0


class Crop(StrictModel):
    """The framing of an asset on a beat: `zoom` over the fitted image around the
    focus point (fractions of the image). A re-dressed reuse never repeats a framing
    (4.4)."""

    zoom: float = 1.0
    focus_x: float = 0.5
    focus_y: float = 0.5


class BeatAsset(StrictModel):
    """What the asset step decided for one sourced beat (4.4, 5.3).

    `asset_id` is the asset actually shown (None on rung 4). `fallback_rung`: 0 found
    with `query` (or an owner reference, or the planned reuse), 1 with
    `query_fallback`, 2 generated, 3 re-dressed reuse of an earlier asset, 4 PIP over
    the gradient. Rungs 3 and 4 are rescues and carry the `stamp` word."""

    beat_id: str
    asset_id: str | None
    treatment: Treatment
    fallback_rung: int = Field(ge=0, le=4)
    treatment_downgraded: bool = False
    redressed_from: str | None = None
    crop: Crop = Field(default_factory=Crop)
    stamp: str | None = None
    # 5.2: nothing judged this beat's candidates - no judge configured, the style's
    # `judge_max_calls` spent, or the judge could not answer. The ladder ran on the
    # source's own order instead; the beat is never rejected for it.
    judge_skipped: bool = False
    # 021 / 9.3: the base of a labelled diagram, asked for with "no text, no labels" and
    # shown only under the code-rendered labels, never as a bare photo.
    diagram_base: bool = False

    @property
    def rescued(self) -> bool:
        return self.fallback_rung >= 3


class StickerRecord(StrictModel):
    """One sticker the short shows (062): the catalogue row's `name`, the PNG copied
    into the job folder (`file`, relative to it) from the fetched cache, and the raw
    GitHub URL it came from. Its rights row and credits line are derived from it."""

    name: str
    file: str
    source_url: str
    sha256: str
    width: int
    height: int
    fetched_at: str


class LineBox(StrictModel):
    """One line of text on a screenshot (078), as fractions of the image's width and
    height, as the judge model found it."""

    left: float = Field(ge=0.0, le=1.0)
    top: float = Field(ge=0.0, le=1.0)
    right: float = Field(ge=0.0, le=1.0)
    bottom: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _not_empty(self) -> LineBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError(
                f"line box {self.left}-{self.right} x {self.top}-{self.bottom} is empty"
            )
        return self


class HighlightRecord(StrictModel):
    """A highlight the sourcing step found the lines for (078): the beat, the owner's
    screenshot it shows, the sentence and its line boxes in reading order. A highlight
    with no record is not drawn (its drop is a job.log line)."""

    beat_id: str
    asset_id: str
    sentence: str
    lines: list[LineBox]


class AssetManifest(StrictModel):
    """`work/assets.json`: every unique asset, every sourced beat, and the planned
    asset ids resolved to the ids actually used (`aliases`; None = no asset) so set
    pieces and the finale can find theirs. `rescued_max` is the style's
    `rescued_max_per_60s` scaled to `runtime_s` (ceil, as the grammar scales maxima)."""

    assets: list[AssetRecord]
    beats: list[BeatAsset]
    aliases: dict[str, str | None] = {}
    runtime_s: float
    rescued_max: int
    # 056 (3): the style's `broll.reuse_max`, the showings one image (one `sha256`, however
    # many ids point at it) may have; 0 on a manifest written before the rule.
    reuse_max: int = 0
    # 5.2 / 5.6: relevance-judge calls made and the style's `judge_max_calls` ceiling.
    judge_calls: int = 0
    judge_max: int = 0
    # 5.6: queries actually sent to a source (cache hits cost nothing and are not
    # counted) and the style's `search_max_queries` allowance. Every source shipped so
    # far is free, so passing the allowance is a note, never a skipped beat (11.3).
    search_queries: int = 0
    search_max: int = 0
    # 5.5 / 5.6: images generated (a cached prompt generates nothing and is not
    # counted) and the style's `gen_max_per_short` cap; the cap sends the beat on to
    # rung 3 of the ladder, it never fails the job.
    generated_images: int = 0
    gen_max: int = 0
    # 062: the stickers fetched for the plan, one per catalogue row shown; a sticker whose
    # fetch failed has none and is left out of the picture.
    stickers: list[StickerRecord] = []
    # 078: the highlights whose lines were found on their screenshot; the rest were dropped.
    highlights: list[HighlightRecord] = []

    def asset(self, asset_id: str) -> AssetRecord | None:
        return next((a for a in self.assets if a.id == asset_id), None)

    def beat(self, beat_id: str) -> BeatAsset | None:
        return next((b for b in self.beats if b.beat_id == beat_id), None)

    def sticker(self, name: str) -> StickerRecord | None:
        return next((s for s in self.stickers if s.name == name), None)

    def highlight(self, beat_id: str) -> HighlightRecord | None:
        return next((h for h in self.highlights if h.beat_id == beat_id), None)

    @property
    def rescued(self) -> int:
        return sum(1 for b in self.beats if b.rescued)


class RightsRow(StrictModel):
    """One row of `out/rights.json` in the 5.4 shape; one per unique asset."""

    id: str
    beat_ids: list[str]
    kind: RightsKind
    origin: Origin
    source_url: str = ""
    page_url: str = ""
    licence: str
    author: str | None = None
    generated: Generated | None = None
    judge: JudgeVerdict | None = None
    file: str
    sha256: str
    width: int
    height: int
    fetched_at: str


# --- captions (decision 6.1) -------------------------------------------------------


class WordBox(StrictModel):
    """One caption word in its fixed-advance box (6.2): `x`,`y` top-left in composition
    pixels, `width` the 1.08-scaled width (plus the keyword padding when boxed)."""

    text: str
    start: float
    end: float
    x: float
    y: float
    width: float
    height: float
    keyword: bool = False


class CaptionPage(StrictModel):
    """One caption page (6.1, 6.2): the indices of its words in the transcript word
    list, their display texts (trailing punctuation stripped), its times on the cut
    timeline per research S4, at most one keyword (a transcript word index) and the
    laid-out word boxes, whose times are on the cut timeline too."""

    index: int
    word_indices: list[int]
    texts: list[str]
    start: float
    end: float
    keyword: int | None = None
    lines: int = 1
    words: list[WordBox] = []


class Captions(StrictModel):
    """`work/captions.json`: the pages, and the beats a two-line page shows over so
    lower-thirds are suppressed there (6.3)."""

    pages: list[CaptionPage]
    beats_with_two_lines: list[str] = []


# --- render spec (ticket 004; decisions 6.2, 6.3, 9.1) -------------------------------
#
# The engine-specific input the Remotion composition reads as its props. Everything
# is resolved: frames not seconds for beats, pixel boxes for words, one palette. The
# composition draws what it is given and measures nothing.


class CaptionPageSpec(StrictModel):
    index: int
    start: float
    end: float
    lines: int
    words: list[WordBox]


class MarkerLine(StrictModel):
    """One stroke of the highlighter (078) in the card image's own pixels, padded around
    the text line, and when it sweeps left to right, in seconds from the beat's start."""

    left: float
    top: float
    width: float
    height: float
    start_s: float
    end_s: float


class HighlightSpec(StrictModel):
    """The marker over a screenshot card (078): its lines in reading order, each swept
    after the one before, in the style's `broll.motion.highlight` colour and opacity."""

    lines: list[MarkerLine]
    color: str
    opacity: float


class CardSpec(StrictModel):
    """The framed archival card (4.1, 5.3) in composition pixels: the outer box
    (white border and caption strip included) before tilt and push, the image inside
    it, and the blurred darkened cover of the same image behind. 078: the push is about
    `origin_x`, `origin_y` (fractions of the box; the centre on every other card), and a
    screenshot card carries its `highlight` drawn inside the image."""

    left: float
    top: float
    width: float
    height: float
    image_width: float
    image_height: float
    border_px: int
    rotate_deg: float
    strip_text: str
    strip_px: int
    strip_font_px: int
    cover_scale_from: float
    cover_scale_to: float
    cover_blur_px: int
    cover_brightness: float
    ring: bool
    ring_color: str
    ring_diameter_px: float
    ring_px: int
    ring_at_s: float
    origin_x: float = 0.5
    origin_y: float = 0.5
    highlight: HighlightSpec | None = None


class VisualSpec(StrictModel):
    """A beat's asset as drawn (016): `src` is the file (the driver serves it), `width`
    and `height` its real size. `scale_from` -> `scale_to` is the Ken Burns over the
    beat (the full-bleed photo, or the card body), `pan_px` the horizontal drift, and
    `zoom` / `focus_*` the framing (a re-dress differs here, 4.4). `dim` is the black
    scrim over it: 0 for a photo or card beat, the style's `broll.motion.<kind>.dim`
    where the still is only the base of a set piece (027). 058: a `clip` is the video
    file covering the frame, muted, played from `start_s` seconds into it at `speed`
    (the style's `broll.motion.clip.speed`), with the same slow push numbers."""

    treatment: Literal["photo", "card", "clip"]
    src: str
    width: int
    height: int
    zoom: float
    focus_x: float
    focus_y: float
    scale_from: float
    scale_to: float
    pan_px: float
    dim: float = 0.0
    card: CardSpec | None = None
    speed: float = 1.0
    start_s: float = 0.0


class CardBox(StrictModel):
    """One placed card of a set piece (3.4; ticket 026), in composition pixels: the
    outer white box, the image that covers its window, the label strip under it, and
    the offset it springs in from. The image is `src` at its real `width`/`height`.
    `scale_from` -> `scale_to` is the Ken Burns inside the window: 1 to 1 (still) on
    the finale's cards, the style's photo motion on a wall cell (027)."""

    src: str
    width: int
    height: int
    left: float
    top: float
    box_width: float
    box_height: float
    image_width: float
    image_height: float
    border_px: int
    rotate_deg: float
    label: str = ""
    strip_px: int = 0
    strip_font_px: int = 0
    from_x: float = 0.0
    from_y: float = 0.0
    delay_s: float = 0.0
    scale_from: float = 1.0
    scale_to: float = 1.0


class FinaleCardSpec(StrictModel):
    """The finale set piece (3.4): the presenter cut in the centre circle, the payoff
    word under it and the short's first images (the opening's, 055) around it, over the
    style gradient."""

    text: str
    text_font_px: int
    text_top: float
    text_color: str
    circle_left: float
    circle_top: float
    circle_diameter: float
    ring_px: int
    ring_color: str
    cards: list[CardBox]
    fade_s: float


class StampSpec(StrictModel):
    """A landed stamp (4.1): rotated text that lands from `scale_from` in `land_s`
    with a shake, drawn in the top `broll.stamp_max_y_fraction` of the frame and clear
    of the platform's right rail."""

    text: str
    left: float
    top: float
    width: float
    height: float
    rotate_deg: float
    font_px: int
    border_px: int
    radius_px: int
    color: str
    fill: str
    scale_from: float
    land_s: float
    shake_s: float


class TextPopSpec(StrictModel):
    """A text pop placed and timed (061): the words in their box (composition pixels,
    before the tilt), popping in from `scale_from` over `pop_s` at `at_s` seconds into
    the beat and leaving at `until_s`; Poppins `font_weight` in `color` with a
    `stroke_px` dark outline and a `drop_px` shadow. Placed by `render.text_pop_spec`
    inside the safe area, off the PIP circle, the caption band and any detected face."""

    text: str
    left: float
    top: float
    width: float
    height: float
    rotate_deg: float
    font_px: int
    font_weight: int
    color: str
    stroke_px: int
    drop_px: int
    scale_from: float
    at_s: float
    pop_s: float
    until_s: float


class BubbleDot(StrictModel):
    """One dot of a thought bubble's trail (063), in composition pixels."""

    cx: float
    cy: float
    r: float


class BubbleSpec(StrictModel):
    """A bubble placed, wrapped and timed (063): the body box (composition pixels) with
    its `lines` of text, the outline `path` (an SVG path in composition pixels: the
    rounded body, with the tail to `tip_x`, `tip_y` on a speech bubble), the thought
    trail `dots`, and the pop-in from `scale_from` over `pop_s` at `at_s` seconds into
    the beat, leaving at `until_s`. Poppins `font_weight` in `ink` on `fill` with a
    `stroke_px` outline. Placed by `render.bubble_spec` inside the safe area, off the
    PIP circle, the caption band, the stamp, any detected face and the beat's other
    bubble; the tail tip is the planner's anchor."""

    shape: BubbleShape
    text: str
    lines: list[str]
    left: float
    top: float
    width: float
    height: float
    radius_px: float
    tip_x: float
    tip_y: float
    path: str
    dots: list[BubbleDot]
    font_px: int
    font_weight: int
    fill: str
    ink: str
    stroke_px: int
    scale_from: float
    at_s: float
    pop_s: float
    until_s: float


class StickerSpec(StrictModel):
    """A sticker placed and timed (062): the PNG `src` (the driver serves it) drawn in a
    `size` px square at `left`, `top` (composition pixels), popping in with an overshoot
    from `scale_from` over `pop_s` at `at_s` seconds into the beat, then floating
    `float_px` up and down every `float_period_s`, under a soft `shadow_px` shadow,
    leaving at `until_s`. Placed by `render.sticker_spec` inside the safe area, off the
    PIP circle, the caption band, the stamp, any detected face and the beat's text pops
    and bubbles."""

    name: str
    src: str
    left: float
    top: float
    size: float
    scale_from: float
    at_s: float
    pop_s: float
    until_s: float
    float_px: float
    float_period_s: float
    shadow_px: float


class CounterSpec(StampSpec):
    """The `counter` overlay (029; 4.2, 9.2): the stamp's box, measured on the widest
    text it will show and clamped as a stamp is, with the digits it shows on each frame
    of the beat (`texts`, already written in the style's grouping). From `land_frame`
    the target lands: a pop from `scale_from` over `land_s` with the stamp's shake.
    `text` is the target."""

    texts: list[str]
    land_frame: int


class LowerThirdSpec(StrictModel):
    """A name-and-role label in the style's `lower_third` band (6.3), faded in over
    `fade_s`. Suppressed where a two-line caption page shows, or where the beat's card
    strip already carries the same text."""

    name: str
    role: str
    left: float
    top: float
    width: float
    height: float
    bar_px: int
    accent: str
    fill: str
    name_font_px: int
    role_font_px: int
    fade_s: float


class ListRow(StrictModel):
    """One row of the `list` set piece (4.1; ticket 027), in composition pixels: the
    pill it draws in, the text inside it at the size that fitted, the optional circular
    icon on its left, and the x it springs in from."""

    text: str
    font_px: int
    left: float
    top: float
    width: float
    height: float
    text_left: float
    icon_src: str = ""
    icon_width: int = 0
    icon_height: int = 0
    icon_left: float = 0.0
    icon_size: float = 0.0
    from_x: float = 0.0
    delay_s: float = 0.0


class ListSpec(StrictModel):
    """The `list` set piece (nkb_04): a header over up to `broll.motion.list.items_max`
    rows springing in one after another, over the beat's dimmed base still."""

    header: str
    header_font_px: int
    header_left: float
    header_top: float
    header_color: str
    rows: list[ListRow]
    row_fill: str
    row_radius_px: int
    spring_s: float


class TitleWord(StrictModel):
    """One word of a set piece's title strip, measured: `highlight` boxes it in the
    style's accent (5.2: the key words of the news-card strip)."""

    text: str
    left: float
    width: float
    highlight: bool = False


class SplitPane(StrictModel):
    """One half of the `split` composite: the image window and the label under it.
    `from_x` is the x it slides in from (nkb_08: the right half slides in)."""

    src: str
    width: int
    height: int
    left: float
    top: float
    pane_width: float
    pane_height: float
    label: str = ""
    from_x: float = 0.0


class BadgeSpec(StrictModel):
    """The circular logo badge overlapping a corner of the split card (5.2)."""

    src: str
    width: int
    height: int
    left: float
    top: float
    diameter: float
    ring_px: int
    ring_color: str


class SplitSpec(StrictModel):
    """The `split` news-card composite (5.2): two re-dressed portraits side by side in
    one framed card, a circular badge overlapping a corner, and a title strip along the
    bottom with the pane words boxed in the accent."""

    left: float
    top: float
    width: float
    height: float
    border_px: int
    rotate_deg: float
    seam_px: int
    panes: list[SplitPane]
    label_px: int
    label_font_px: int
    title_px: int
    title_font_px: int
    title_color: str
    title_words: list[TitleWord]
    # 059: the title band's top edge inside the card: along the bottom of a side-by-side
    # card, between the two pictures of a stacked one.
    title_top: float
    highlight_fg: str
    highlight_bg: str
    highlight_pad_px: int
    highlight_radius_px: int
    badge: BadgeSpec | None = None
    slide_s: float


class WallSpec(StrictModel):
    """The `wall` set piece (nkb_09): a 2x2 to 3x3 grid of cards over the beat's dimmed
    base still, each cell flying in from an alternating side with its own Ken Burns."""

    cells: list[CardBox]
    columns: int
    spring_s: float


class ChartMark(StrictModel):
    """One mark of a chart (ticket 021), in composition pixels: the column it owns, the
    bar drawn inside it up from the baseline (a dot at the value height on a `line`
    chart), the point the value label hangs off, and the axis label under it."""

    label: str
    value: float
    value_text: str
    left: float
    width: float
    bar_left: float
    bar_top: float
    bar_width: float
    bar_height: float
    point_x: float
    point_y: float
    color: str
    delay_s: float


class ChartLayout(StrictModel):
    """The `chart` set piece drawn in code from the planner's series (9.2): the title
    over a plot box inside the safe area, one mark per series point with the axes scaled
    to the real numbers, and the axis labels under the baseline, outside the plot."""

    form: ChartForm
    title: str
    title_font_px: int
    title_top: float
    title_color: str
    plot_left: float
    plot_top: float
    plot_width: float
    plot_height: float
    baseline_y: float
    baseline_px: int
    axis_color: str
    label_top: float
    label_font_px: int
    value_font_px: int
    dot_px: int
    marks: list[ChartMark]
    grow_s: float


class DiagramLabel(StrictModel):
    """One code-rendered label of a labelled diagram (9.3), placed in composition
    pixels: the pill it draws in, the size the text fitted at, and the edge the
    planner's percentage pinned (`anchor`, the point the fly-in grows from). 029:
    `from_x` / `from_y` is the offset past the nearest frame edge it springs in from,
    `delay_s` its place in the stagger."""

    text: str
    left: float
    top: float
    width: float
    height: float
    font_px: int
    anchor: LabelAnchor
    delay_s: float
    from_x: float = 0.0
    from_y: float = 0.0


class DiagramLayout(StrictModel):
    """The `infographic` set piece (9.2, 9.3): the label-free base picture in its box
    with the style's Ken Burns and scrim, and the labels drawn over it in code - text
    never goes inside a generated image (5.5)."""

    src: str
    width: int
    height: int
    left: float
    top: float
    box_width: float
    box_height: float
    zoom: float
    focus_x: float
    focus_y: float
    scale_from: float
    scale_to: float
    dim: float
    labels: list[DiagramLabel]
    fill: str
    radius_px: int
    text_color: str
    fly_s: float


class MapMarkerLayout(StrictModel):
    """One marker of a map (ticket 020), in composition pixels: the real coordinate the
    geocoder gave it, the dot, and the label pill beside the dot (inside the safe area,
    flipped to the left where the right rail is near). `delay_s` is 028's pin-drop
    stagger, 0 while markers are static; `source` names the geocoder for the log."""

    name: str
    lat: float
    lon: float
    x: float
    y: float
    label_left: float
    label_top: float
    label_width: float
    label_height: float
    label_font_px: int
    delay_s: float = 0.0
    source: str = "gazetteer"


class RouteSegment(StrictModel):
    """One straight leg of the map's route in composition pixels (ticket 028): its two
    ends, where it starts and ends as fractions of the whole route's length (`t0`,
    `t1`), and the tangent heading in screen degrees (0 east, 90 south, since y grows
    downward) that the arrowhead and the moving object turn to."""

    x0: float
    y0: float
    x1: float
    y1: float
    t0: float
    t1: float
    heading_deg: float


class MapLayout(StrictModel):
    """The `map` set piece (9.3, ticket 020): the base drawn from the bundled Natural
    Earth layers as SVG paths in composition pixels (land fill, coast and border
    strokes, already projected, clipped and simplified by `infographics.resolve_map`),
    the markers placed by real coordinates, and the route polyline 028 animates. The
    projection numbers (`scale`, the centre) are here so 028 can put anything else on
    the same maths; `bbox` is the crop as drawn, `left/top/width/height` the band the
    crop was fitted into.

    Ticket 028: the three map animations, each switched on by its overlay on the beat
    and timed by `infographics.map_timeline` from the beat's length, in order - the
    pins drop (each marker's `delay_s`, then `pin_drop_s` to settle from `pin_drop_px`
    above, the label popping over `label_pop_s` once it lands), the route draws on
    (`route_path` with its `route_length_px`, from `route_start_s` over
    `route_draw_s`, the arrowhead at the tip), then the object travels the `segments`
    (from `object_start_s` over `object_travel_s`, heading along the tangent).
    `landed_s` is when the last of them has landed; everything is 0 or empty on a
    static map."""

    region: str
    bbox: tuple[float, float, float, float]
    left: float
    top: float
    width: float
    height: float
    scale: float
    center_lon: float
    center_merc: float
    center_x: float
    center_y: float
    land: list[str]
    coast: list[str]
    borders: list[str]
    land_color: str
    coast_color: str
    border_color: str
    coast_px: float
    border_px: float
    markers: list[MapMarkerLayout]
    route: list[tuple[float, float]]
    object: MapObject | None
    marker_color: str
    dot_px: int
    ring_px: int
    label_fill: str
    label_radius_px: int
    text_color: str
    draw_s: float
    # 028: the three animations and their timing (see the class docstring).
    pin_drop: bool = False
    route_arrow: bool = False
    object_path: bool = False
    pin_drop_s: float = 0.0
    pin_drop_px: float = 0.0
    label_pop_s: float = 0.0
    route_path: str = ""
    route_length_px: float = 0.0
    segments: list[RouteSegment] = []
    route_start_s: float = 0.0
    route_draw_s: float = 0.0
    route_px: float = 0.0
    arrow_px: float = 0.0
    object_start_s: float = 0.0
    object_travel_s: float = 0.0
    object_px: float = 0.0
    landed_s: float = 0.0


class PunchIn(StrictModel):
    """The full-frame presenter punch-in (research S2): scale `scale_from` easing to
    `settle_to` by `settle_s`, then to 1 over the rest of the beat, with the grade."""

    scale_from: float
    settle_to: float
    settle_s: float
    origin_y: float
    contrast: float
    saturate: float


class BeatSpec(StrictModel):
    """A plan beat as frame range; `end_frame` is exclusive. A rung-4 rescue arrives
    here as `pip` with no visual (4.4). The set pieces and the two overlay kinds (026,
    027, 021, 020) ride along resolved: at most one of `finale` / `list` / `split` /
    `wall` / `chart` / `infographic` / `map`, and at most one landed event (`stamp`,
    `lower_third` or, 029, `counter`; 3.1).

    `list` shadows the builtin inside this class body only; no annotation below it
    needs `list[...]`, and the field name matches its kind as `finale` does."""

    id: str
    start_frame: int
    end_frame: int
    mode: Mode
    kind: Kind
    enter: Transition = "cut"
    visual: VisualSpec | None = None
    punch_in: PunchIn | None = None
    stamp: StampSpec | None = None
    lower_third: LowerThirdSpec | None = None
    # 061: the beat's text pops, placed and timed; empty on every other beat. A tuple
    # because the `list` field shadows the builtin inside this class body.
    text_pops: tuple[TextPopSpec, ...] = ()
    # 063: the beat's bubbles, placed and timed; a tuple for the same reason.
    bubbles: tuple[BubbleSpec, ...] = ()
    # 062: the beat's sticker, placed and timed; a tuple for the same reason.
    stickers: tuple[StickerSpec, ...] = ()
    finale: FinaleCardSpec | None = None
    split: SplitSpec | None = None
    wall: WallSpec | None = None
    list: ListSpec | None = None
    # 021: the two infographic kinds, laid out by `infographics`.
    chart: ChartLayout | None = None
    infographic: DiagramLayout | None = None
    # 020: the map, drawn from the bundled geodata with markers at real coordinates.
    map: MapLayout | None = None
    # 029: the counter overlay, the beat's landed event in place of a stamp.
    counter: CounterSpec | None = None


class PipGeometry(StrictModel):
    """The presenter circle (composition pixels) and the square crop window it shows
    (pixels of the presenter cut). Measured once per job from the face (3.3, ticket
    013); `render.fixed_pip` is the 004 geometry a spec built without a measurement
    falls back to."""

    left: int
    top: int
    diameter: int
    ring_px: int
    ring_color: str
    window_left: int
    window_top: int
    window_size: int


class FaceBox(StrictModel):
    """A detected face, in pixels of the presenter cut (the 9:16 window of the source
    scaled to the composition, so the box lands where the render reads it)."""

    left: int
    top: int
    width: int
    height: int

    @property
    def chin_y(self) -> int:
        return self.top + self.height


class PresenterMeasurement(StrictModel):
    """`job.json.presenter` (3.3, ticket 013): the eight research strip times on the
    recording, the face the detector found on each still (None where it found none),
    the median box, the cut's size and the PIP geometry derived from them. Measured once
    per job, never tracked (14.1)."""

    source_width: int
    source_height: int
    times_s: list[float]
    faces: list[FaceBox | None]
    face: FaceBox
    pip: PipGeometry


class Palette(StrictModel):
    """The style's gradient for `off` beats and rescued beats (4.4) plus the accent."""

    gradient: list[str]
    angle_deg: int
    accent: str


class Timed(StrictModel):
    """A transition with a length and nothing else (`fade`, `wipe`)."""

    duration_s: float


class WhipNumbers(Timed):
    blur_px: int


class ZoomNumbers(Timed):
    scale_from: float


class SpringNumbers(StrictModel):
    damping: float
    stiffness: float
    mass: float


class FlashNumbers(Timed):
    """060 (9.4 as amended): the flash's whole length, centred on the cut, and its
    colour (a style's accent, or white)."""

    color: str


class Transitions(StrictModel):
    """9.4: the global enter vocabulary's numbers, one row per transition that has any
    (`cut` has none), read from every style's `broll.transitions` front matter (030;
    060 adds `flash`)."""

    fade: Timed
    whip: WhipNumbers
    zoom: ZoomNumbers
    spring: SpringNumbers
    wipe: Timed
    flash: FlashNumbers


class TransitionStyle(Transitions):
    """What the composition reads (030): the style's enabled subset and the numbers.
    The renderer refuses a beat whose `enter` is outside `enabled` (9.4, defence in
    depth behind the grammar)."""

    enabled: list[Transition]


class CaptionStyle(StrictModel):
    """The 6.2 typography numbers the composition applies verbatim."""

    font_family: str
    font_weight: int
    size_px: int
    line_height: float
    letter_spacing_px: float
    anchor_y: int
    max_lines: int
    max_width_px: int
    word_gap_px: int
    unspoken_alpha: float
    active_color: str
    active_scale: float
    active_scale_s: float
    keyword_fg: str
    keyword_bg: str
    keyword_pad_px: int
    keyword_radius_px: int
    enter_scale_from: float
    enter_s: float
    enter_opacity_s: float
    stroke_px: int
    drop_px: int
    glow_px: int


class TitleStripSpec(StrictModel):
    """The fixed title strip (059): the plan's `title_strip` in a `fill` bar of the frame
    (composition pixels) from the first frame to `until_frame` (the finale's first frame,
    exclusive), the words in `ink` at `font_px` (fitted from the style's `size_px`), the
    bar sliding down over `slide_s`. Placed by `render.title_strip_spec` inside the safe
    area; T12 judges its box."""

    text: str
    left: float
    top: float
    width: float
    height: float
    font_px: int
    font_weight: int
    fill: str
    ink: str
    slide_s: float
    until_frame: int


class RenderSpec(StrictModel):
    width: int = 1080
    height: int = 1920
    fps: int
    frames: int
    presenter: str
    source_width: int
    source_height: int
    beats: list[BeatSpec]
    captions: list[CaptionPageSpec]
    beats_with_two_lines: list[str] = []
    pip: PipGeometry
    palette: Palette
    caption_style: CaptionStyle
    # 030: the style's enter list and the 9.4 numbers; the composition animates each
    # beat's `enter` from these.
    transitions: TransitionStyle
    # 059: the style's fixed title strip, where it has one.
    title_strip: TitleStripSpec | None = None


# --- the job record's shared pieces (decisions 5.6, 8.3, 10.2, 10.3, 14.1; tickets 011, 034) --

RATING_MIN, RATING_MAX = 1, 10  # 10.3: the phone slider
ViewsSource = Literal["manual", "youtube"]


class CostRow(StrictModel):
    """One paid call (decision 5.6), priced by the ledger; adapters report `units` only.
    `inr` is cash and counts toward the caps. A subscription call (8.3) carries its
    tokens as `tokens_estimated` with `inr` zero and `inr_equivalent` the display-only
    value at the api-equivalent rate (11.3)."""

    step: str
    provider: str
    model: str
    units: dict[str, float]
    inr: float
    tokens_estimated: int = 0
    inr_equivalent: float = 0.0
    at: datetime


class Rating(StrictModel):
    """The phone verdict (10.3, 034): 1-10 and a note, when it was given."""

    score: int = Field(ge=RATING_MIN, le=RATING_MAX)
    note: str = ""
    rated_at: datetime


class Performance(StrictModel):
    """The published short's real audience (10.2, 14.1(a)): typed in by hand, or the
    views read from the YouTube Data API for the stored URL. `note` is the last pull's
    outcome in one line. Never an upload."""

    published_url: str = ""
    views: int | None = Field(default=None, ge=0)
    retention_pct: float | None = Field(default=None, ge=0, le=100)
    views_source: ViewsSource = "manual"
    note: str = ""
    updated_at: datetime


class CriticSummary(StrictModel):
    """What the critic said, on job.json (034): the overall and whether it was advisory
    when it ran, so the verdict and the calibration read one file. The full report
    (the ten lines, the notes) stays in out/qa.json."""

    status: CriticStatus
    overall: int | None = Field(default=None, ge=1, le=10)
    advisory: bool = True
    model: str


# --- meta.json (decision 10.4; ticket 035) ------------------------------------------------


class TechnicalResult(StrictModel):
    """One T1-T13 line as `out/qa.json` recorded it: `pass`, `fail`, or the pre-032
    `not_implemented` placeholder."""

    name: str
    status: Literal["pass", "fail", "not_implemented"]
    detail: str


class ComparisonRow(StrictModel):
    """One row of the self-inventory table (074): our number beside the median and the
    range (min-max) of the style's v2 reference cards, `outside` (red) when it falls out
    of the range. A row that is not a number (the bed, a part's mood, the music change)
    carries our value, the references' tally in `refs`, and `plan` for a mood row (076
    fills the plan's side; until then "—"); it is never red."""

    name: str
    ours: float | str | None = None
    median: float | None = None
    low: float | None = None
    high: float | None = None
    refs: str = ""
    plan: str | None = None
    outside: bool = False


class InventoryComparison(StrictModel):
    """Our card against the v2 cards whose `styles` include the job's style; fewer than
    two cards is "not enough references" and no range is drawn."""

    style: str
    references: int
    enough: bool
    note: str = ""
    rows: list[ComparisonRow] = []


class OwnInventory(StrictModel):
    """`meta.json`'s record of the advisory `inventory` step (074): the comparison once
    the short was analysed, or the reason it was not."""

    status: Literal["analysed", "not_analysed"]
    reason: str = ""
    comparison: InventoryComparison | None = None


class Meta(StrictModel):
    """`out/meta.json`: the proof of the bar for one short (10.4), the file the day-14
    gate reads (14.1). `delivered` is the 10.4 rule (every technical check passed and
    the four deliverables exist); `status` is where the verdict left the job. The
    versions name what produced the short: the planner prompt (8.3), the style spec's
    front matter (1.2) and the reference pack the critic was calibrated on (10.3).
    `ledger` is every row of `job.json.cost`; the totals beside it are the page's."""

    job_id: str
    status: str
    delivered: bool
    style: str
    style_version: str | None = None
    prompt_version: str | None = None
    category: str = "other"
    # 077: the topic code picked before planning (None: style only) and the worked
    # examples' video ids the planner saw.
    topic: str | None = None
    examples: list[str] = []
    reference_pack_version: str | None = None
    technical: list[TechnicalResult] = []
    technical_passed: bool = False
    critic: CriticReport | None = None
    rating: Rating | None = None
    performance: Performance | None = None
    ledger: list[CostRow] = []
    cash_inr: float = 0.0
    tokens_estimated: int = 0
    inr_equivalent: float = 0.0
    over_soft_cap: bool = False
    clamps: int = 0
    rescued: int = 0
    inventory: OwnInventory | None = None  # 074: absent until the step has run
    written_at: datetime
