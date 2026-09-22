"""Shared Pydantic models (PRD "Global contracts").

Transcript family, the planner-facing PlanRequest / PicturePlan / SoundStory (2.3,
8.1) and CaptionPage (6.1). Planner-facing models use `extra="forbid"` so the JSON
schema generated from them is the single source of truth embedded in the planner
prompt; plan JSON is engine-agnostic (no render-engine terms in field names or
values). ValidatedPlan (009), AssetManifest and RightsRow (016), RenderSpec (004),
QaReport, CriticReport and Meta arrive with their tickets.
"""

from __future__ import annotations

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


class PlanRequest(StrictModel):
    """Everything the planner receives; nothing from disk, no pixels (2.3)."""

    brief: str
    style: PlanStyle
    style_note: str
    transcript: Transcript
    references: list[PlanReference]
    constraints: Constraints
    asset_policy: AssetPolicy


# --- picture plan (decisions 3.1, 3.2, 3.4, 4.1, 4.2, 8.1, 9.2, 9.4) ----------------

Mode = Literal["full", "pip", "off"]
ReasonTag = Literal["cold_open", "emotional_line", "argument_turn"]

Tier1Kind = Literal[
    "photo",
    "card",
    "stamp",
    "lower_third",
    "hook_cards",
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
SourceIntent = Literal["search", "generate", "reuse"]
Transition = Literal["cut", "fade", "whip", "zoom", "spring", "wipe"]
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


class Beat(StrictModel):
    id: str
    start: float
    end: float
    mode: Mode
    reason: ReasonTag | None = None
    kind: Kind
    overlays: list[OverlayKind] = []
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
    """Kept and dropped spans of the recording (8.1); the cold-open lift is in `hook`."""

    keep: list[Span]
    drop: list[Span] = []


class Hook(StrictModel):
    """The two-beat hook (3.4): cold open lifted from anywhere, then title + cards."""

    title: str
    cold_open_span: Span
    original_position: Literal["keep", "drop"]
    card_asset_ids: list[str]


class Finale(StrictModel):
    beat_id: str
    text: str


class PicturePlan(StrictModel):
    prompt_version: str
    cut: CutPlan
    beats: list[Beat]
    hook: Hook
    finale: Finale
    keywords: list[int] = []  # word indices, priority order (6.1)
    title: str
    description: str
    hashtags: list[str] = []


# --- sound story (decisions 7.1, 7.2, 8.1) ------------------------------------------


class MoodPoint(StrictModel):
    t: float
    level: float  # dB relative to the bed target; clipped to +4/-8 by 009 (7.3)


class BedQuery(StrictModel):
    theme: str
    mood: str
    energy: int = Field(ge=1, le=5)


class Cue(StrictModel):
    beat_id: str
    intent: str
    at: Literal["start", "event", "end"]


class SoundStory(StrictModel):
    prompt_version: str
    theme: str
    mood_curve: list[MoodPoint]
    bed_query: BedQuery
    cues: list[Cue]


# --- captions (decision 6.1) -------------------------------------------------------


class CaptionPage(StrictModel):
    """One caption page: 2-4 word indices into the final word list, timed per
    research S4, with at most one keyword (a word index) boxed. Layout boxes and line
    count arrive with ticket 010."""

    index: int
    word_indices: list[int]
    texts: list[str]
    start: float
    end: float
    keyword: int | None = None


# --- render spec (ticket 004; decisions 6.2, 6.3, 9.1) -------------------------------
#
# The engine-specific input the Remotion composition reads as its props. Everything
# is resolved: frames not seconds for beats, pixel boxes for words, one palette. The
# composition draws what it is given and measures nothing.


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


class CaptionPageSpec(StrictModel):
    index: int
    start: float
    end: float
    lines: int
    words: list[WordBox]


class BeatSpec(StrictModel):
    """A plan beat as frame range; `end_frame` is exclusive."""

    id: str
    start_frame: int
    end_frame: int
    mode: Mode
    kind: Kind
    enter: Transition = "cut"


class PipGeometry(StrictModel):
    """The presenter circle (composition pixels) and the square crop window it shows
    (source pixels). Fixed geometry until ticket 013 measures the face."""

    left: int
    top: int
    diameter: int
    ring_px: int
    ring_color: str
    window_left: int
    window_top: int
    window_size: int


class Palette(StrictModel):
    """The style's gradient for `off` beats and rescued beats (4.4) plus the accent."""

    gradient: list[str]
    angle_deg: int
    accent: str


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
    pip: PipGeometry
    palette: Palette
    caption_style: CaptionStyle
