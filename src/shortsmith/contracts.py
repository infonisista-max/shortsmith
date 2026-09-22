"""Shared Pydantic models (PRD "Global contracts").

Transcript family, the planner-facing PlanRequest / PicturePlan / SoundStory (2.3,
8.1), CaptionPage (6.1), the validator's ValidatedPlan with its clamps (8.2, ticket
009), the retry feedback a rejected call is re-sent with, the asset step's
AssetManifest and the RightsRow of the rights log (016), and the RenderSpec (004).
Planner-facing models use `extra="forbid"` so the JSON schema generated from them is
the single source of truth embedded in the planner prompt; plan JSON is
engine-agnostic (no render-engine terms in field names or values). QaReport lives in
`qa.technical`; CriticReport and Meta arrive with their tickets.
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


class PicturePlan(StrictModel):
    prompt_version: str
    cut: CutPlan
    beats: list[Beat]
    hook: Hook
    finale: Finale
    keywords: list[int] = []  # word indices, priority order (6.1)
    name_runs: list[WordRun] = []  # names and numbers never split across pages (6.1)
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
    story clamped, every clamp logged and the 3.4 / 4.3 warnings for the contact sheet."""

    picture: PicturePlan
    sound: SoundStory
    clamps: list[Clamp] = []
    warnings: list[str] = []


class PlanFeedback(StrictModel):
    """What a rejected call is re-sent with (8.2): the previous output as JSON text
    and the violation list, one line each with beat id and rule."""

    previous: str
    violations: list[str]


# --- assets and rights (decisions 4.2, 4.4, 5.1, 5.3, 5.4, 5.6; ticket 016) ----------

# Where an asset came from (5.4). `library` is the audio catalogue (022).
Origin = Literal[
    "owner_supplied", "web", "commons", "openverse", "pexels", "pixabay", "generated", "library"
]
SearchOrigin = Literal["web", "commons", "openverse", "pexels", "pixabay"]
RightsKind = Literal["image", "clip_frame", "music", "sfx"]
# How a beat's asset is drawn (5.3): full-bleed photo, framed card, or no asset at all
# (rung 4: the presenter PIP over the style gradient with a stamp; 4.4).
Treatment = Literal["photo", "card", "gradient"]


class Candidate(StrictModel):
    """One search hit from an `ImageSource` (5.1): where it lives and its reported size.
    The fetched file's real dimensions are what classification reads (5.3)."""

    url: str
    page_url: str = ""
    width: int
    height: int
    author: str | None = None
    licence: str = "unknown"


class Generated(StrictModel):
    """The generation record of a generated asset (5.4, 5.5)."""

    model: str
    prompt: str
    render: Literal["illustration", "photoreal"]
    depicts: Depicts


class JudgeVerdict(StrictModel):
    """The relevance judge's verdict on the chosen candidate (5.2; ticket 017)."""

    model: str
    score: int
    reasons: list[str] = []


class AssetRecord(StrictModel):
    """One unique asset the short uses; the rights row (5.4) is derived from it.
    `file` is relative to the job directory."""

    id: str
    kind: Literal["image", "clip_frame"] = "image"
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

    @property
    def rescued(self) -> bool:
        return self.fallback_rung >= 3


class AssetManifest(StrictModel):
    """`work/assets.json`: every unique asset, every sourced beat, and the planned
    asset ids resolved to the ids actually used (`aliases`; None = no asset) so hook
    cards and the finale can find theirs. `rescued_max` is the style's
    `rescued_max_per_60s` scaled to `runtime_s` (ceil, as the grammar scales maxima)."""

    assets: list[AssetRecord]
    beats: list[BeatAsset]
    aliases: dict[str, str | None] = {}
    runtime_s: float
    rescued_max: int

    def asset(self, asset_id: str) -> AssetRecord | None:
        return next((a for a in self.assets if a.id == asset_id), None)

    def beat(self, beat_id: str) -> BeatAsset | None:
        return next((b for b in self.beats if b.beat_id == beat_id), None)

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


class CardSpec(StrictModel):
    """The framed archival card (4.1, 5.3) in composition pixels: the outer box
    (white border and caption strip included) before tilt and push, the image inside
    it, and the blurred darkened cover of the same image behind."""

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


class VisualSpec(StrictModel):
    """A beat's asset as drawn (016): `src` is the file (the driver serves it), `width`
    and `height` its real size. `scale_from` -> `scale_to` is the Ken Burns over the
    beat (the full-bleed photo, or the card body), `pan_px` the horizontal drift, and
    `zoom` / `focus_*` the framing (a re-dress differs here, 4.4)."""

    treatment: Literal["photo", "card"]
    src: str
    width: int
    height: int
    zoom: float
    focus_x: float
    focus_y: float
    scale_from: float
    scale_to: float
    pan_px: float
    card: CardSpec | None = None


class BeatSpec(StrictModel):
    """A plan beat as frame range; `end_frame` is exclusive. A rung-4 rescue arrives
    here as `pip` with no visual (4.4)."""

    id: str
    start_frame: int
    end_frame: int
    mode: Mode
    kind: Kind
    enter: Transition = "cut"
    visual: VisualSpec | None = None


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
    beats_with_two_lines: list[str] = []
    pip: PipGeometry
    palette: Palette
    caption_style: CaptionStyle
