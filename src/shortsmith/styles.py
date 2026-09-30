"""Style specs: loader, validation and the free-text resolver (decisions 1.1, 1.2, 1.4).

A spec is `styles/<name>.md`: YAML front matter followed by the five prose sections
(`## Beat grammar`, `## B-roll`, `## Captions`, `## Sound`, `## Finale`). The front
matter carries the eight key groups (`aliases`, `beats`, `presenter`, `broll`,
`captions`, `sound`, `finale`, `cut`) plus `version`, `status`, `requires_components`,
`budget`, `pip` and `palette`; every number a later ticket reads (the grammar validator, the pager,
the renderer, the sound director, the gate) comes from here, never from code. The
renderer and QA read only the numbers; the planner reads numbers and prose.

`load_all(registry)` validates every spec at startup and fails with the spec name
and what is wrong: a missing key group, a stray or mistyped key, a missing prose
section, a PIP circle that would reach into the caption block (6.3), a caption width
wider than the safe band (067), or a shipped
spec that requires a component the renderer registry does not export (9.2). Drafts
may require components still to be built.

`resolve(line, specs)` maps the upload form's style line to one spec (1.1): alias
hits are counted per spec (059: a multi-word alias such as "vishva gyan" counts as a
phrase), the highest count wins, zero hits or a tie fall back to `explainer`. An alias
of a draft spec resolves to `explainer` with a visible notice (1.4). The full line is
the style note the planner gets for what the spec leaves open. No LLM is involved.

YAML note: PyYAML reads a bare `off`, `on`, `yes` or `no` as a boolean, so the
presenter mode `off` is quoted in every spec.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, ValidationError, field_validator

from shortsmith.contracts import (
    CAMERA_MOVES,
    CaptionStyle,
    Palette,
    PictureTreatment,
    StrictModel,
    Transition,
    Transitions,
)
from shortsmith.safe_area import BAND_LEFT, BAND_RIGHT, BAND_WIDTH

STYLES_DIR = Path(__file__).resolve().parents[2] / "styles"
DEFAULT = "explainer"
KEY_GROUPS: tuple[str, ...] = (
    "aliases",
    "beats",
    "presenter",
    "broll",
    "captions",
    "sound",
    "finale",
    "cut",
)
PROSE_SECTIONS: tuple[str, ...] = ("Beat grammar", "B-roll", "Captions", "Sound", "Finale")

Status = Literal["shipped", "draft"]


class StyleError(ValueError):
    """A spec failed to load; the message names the spec and the problem."""


# --- front matter models (1.2) ---------------------------------------------------------


class Beats(StrictModel):
    """3.1 beat lengths plus the opening's shape (3.4 as amended by 055): the short's
    first `opening_beats_min` to `opening_beats_max` beats are quick beats over
    full-screen images of the main subject, the `opening_beats_min`-th ending by
    `opening_max_s`. All in seconds. Every style sets `opening_beats_min` to 2; 0
    switches the opening rules off, which only a test's spec copy does."""

    min_s: float
    max_s: float
    set_piece_max_s: float
    target_mean_s: float
    mean_min_s: float
    mean_max_s: float
    density_gap_max_s: float
    snap_window_s: float
    opening_beats_min: int = Field(ge=0)
    opening_beats_max: int = Field(ge=1)
    opening_max_s: float


class Presenter(StrictModel):
    """3.2 presenter modes and run limits; `opening_mode` is the mode of the opening
    beats (055: the speaker in the circle over the images, `pip`)."""

    modes: list[str]
    full_max_fraction: float
    full_never_consecutive: bool
    full_reasons: list[str]
    pip_max_run: int
    off_max_run: int
    opening_mode: str
    finale_mode: str


class Cut(StrictModel):
    """055 (3.4 as amended): the cut removes only silence. A pause between two kept
    words longer than `max_pause_s` is tightened to it by code, half kept on each
    side; the head before the first word keeps at most `beats.snap_window_s`."""

    max_pause_s: float = Field(gt=0.0)


class Pip(StrictModel):
    """3.3 / 6.3 circle geometry in composition pixels; `top` is for the normal
    diameter, the large-face circle grows upward from the same bottom edge."""

    left: int
    top: int
    diameter: int
    large_face_diameter: int
    large_face_ratio: float
    chin_anchor: float
    ring_px: int
    ring_color: str


class TitleStrip(StrictModel):
    """059: the fixed title strip a recipe style (`fastfacts`) keeps at the top of the
    frame for the whole short - the plan's `title_strip`, the topic in at most
    `words_max` words - as a `height_px` bar starting at `top_y` (at or below the 6.3
    top zone), its type `size_px` shrinking to `min_size_px` to fit, `fill` behind `ink`,
    sliding in over `duration_s`. A style without the row has no strip."""

    words_max: int = Field(ge=1)
    top_y: int
    height_px: int = Field(gt=0)
    size_px: int = Field(gt=0)
    min_size_px: int = Field(gt=0)
    fill: str
    ink: str
    duration_s: float = Field(ge=0.0)


class BannerRow(StrictModel):
    """107 (083; banner_slide_down, date_banner_slide, text_banner_pop): the banner a style
    offers - at most `max_per_60s` per 60 s of runtime (rounded up), 1-`words_max` words of
    the recording, sliding in over `slide_s` and held to the beat's end or `hold_max_s`.
    A `height_px` bar across the safe band: at `top_y` for a top banner, else its bottom
    `gap_px` above the PIP circle (a `pip` beat) or the caption block; the words in `ink`
    fitted from `size_px` to `min_size_px` on `fill`, a `bar_px` edge in `bar` on the
    side it slides in from. A style without the row offers no banner."""

    max_per_60s: int = Field(ge=0)
    words_max: int = Field(ge=1)
    slide_s: float = Field(ge=0.0)
    hold_max_s: float = Field(gt=0.0)
    top_y: int
    height_px: int = Field(gt=0)
    gap_px: int = Field(ge=0)
    size_px: int = Field(gt=0)
    min_size_px: int = Field(gt=0)
    fill: str
    ink: str
    bar: str
    bar_px: int = Field(ge=0)


class CalendarRow(StrictModel):
    """108 (083; calendar_flip, calendar_page_peel): the calendar page a style offers for a
    year or date beat in place of a stamp - at most `max_per_60s` per 60 s of runtime
    (rounded up), each text at most `chars_max` characters. It appears `lead_s` before the
    flip, peels over `flip_s` to land on the spoken word, and holds `hold_max_s` (or to the
    beat's end). A `width_px` x `height_px` page with a `header_px` strip, the text fitted
    from `size_px` to `min_size_px`; `page` / `ink`, `header` / `header_ink`."""

    max_per_60s: int = Field(ge=0)
    chars_max: int = Field(ge=1)
    lead_s: float = Field(ge=0.0)
    flip_s: float = Field(ge=0.0)
    hold_max_s: float = Field(gt=0.0)
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    header_px: int = Field(ge=0)
    size_px: int = Field(gt=0)
    min_size_px: int = Field(gt=0)
    page: str
    ink: str
    header: str
    header_ink: str


class MoveRow(StrictModel):
    """102: one camera move on a full-screen still - the push `scale_from` -> `scale_to`
    over the beat, the picture's travel over it as a fraction of the frame (`pan_x` of the
    width, + right; `pan_y` of the height, + down; the renderer keeps it inside the margin
    the smaller scale leaves), and what the push is centred on: `subject` (the beat's
    subject face - the one the card's ring circles) or `frame` (the framing's focus)."""

    scale_from: float = Field(gt=0.0)
    scale_to: float = Field(gt=0.0)
    pan_x: float = 0.0
    pan_y: float = 0.0
    aim: Literal["subject", "frame"] = "frame"


class Broll(StrictModel):
    """4.1 / 9.2 kinds and per-kind motion numbers, 9.4 transitions, 4.3 asset counts."""

    kinds: list[str]
    tier2_kinds: list[str]
    motion: dict[str, dict[str, float | int | bool | str]]
    enter_transitions: list[Transition]
    whip_max_per_3_beats: int
    # 060 (9.4 as amended): at most this many `flash` enters per 60 s of runtime (the
    # references use at most 4), and never on two consecutive beats.
    flash_max_per_60s: int = Field(ge=0)
    # 061 (4.1 as amended): at most this many text pops per 60 s of runtime, rounded up;
    # 0 turns them off. The pop's own numbers are the `motion.text_pop` row, which the
    # renderer requires of every spec (`render.broll_numbers`) as it does the other rows.
    text_pops_max_per_60s: int = Field(ge=0)
    # 063 (4.1 as amended): at most this many speech / thought bubbles per 60 s of
    # runtime, rounded up; 0 turns them off. The bubble's numbers (the overshoot, the
    # hold, the per-beat cap, the word cap, the dialogue gap, the type sizes, the body
    # width, fill and ink) are the `motion.bubble` row, required of every spec too.
    bubbles_max_per_60s: int = Field(ge=0)
    # 062 (4.1 as amended): at most this many Fluent Emoji stickers per 60 s of runtime,
    # rounded up; 0 turns them off. The sticker's numbers (the overshoot, the hold, the
    # per-beat cap, the square size, the float) are the `motion.sticker` row, required
    # of every spec too.
    stickers_max_per_60s: int = Field(ge=0)
    # 078 (4.1 as amended): at most this many article highlights (a marker sweeping a
    # sentence of the owner's uploaded screenshot) per 60 s of runtime, rounded up; 0 turns
    # them off. The marker's numbers (colour, opacity, padding, the card's push toward the
    # lines) are the `motion.highlight` row, required of every spec too.
    highlights_max_per_60s: int = Field(ge=0)
    # 058 (4.1 as amended): the share of the runtime `clip` beats (full-screen moving
    # stock footage) may take, 0-1; 0 turns clips off. The clip's own numbers (the slow
    # push, the playback speed) are the `motion.clip` row, required of every spec too.
    clip_max_fraction: float = Field(ge=0.0, le=1.0)
    # 030: the 9.4 vocabulary's numbers. Every spec carries all six rows, enabled or
    # not, so the renderer reads one shape; `enter_transitions` is the subset it may use.
    transitions: Transitions
    unique_assets_min_per_60s: int
    unique_assets_max_per_60s: int
    reuse_max: int
    rescued_max_per_60s: int
    # 057 (5.3 as amended): a portrait or square image the planner asked `photo` or
    # `auto` for is drawn full-bleed when it covers 1080x1920 at no more than this
    # upscale, whatever its origin; anything else is a card.
    full_bleed_max_upscale: float = Field(gt=0.0)
    card_max_bottom_y: int
    stamp_max_y_fraction: float
    photo_look: str
    illustration_look: str
    # 5.5: the rest of the generated-scene prompt, in the style's own words; the
    # generator builds the sentence, the words are never in code.
    scene_mood: str
    scene_lighting: str
    # 059: the fixed title strip; only a style that draws one carries the row.
    title_strip: TitleStrip | None = None
    # 107: the banner; only a style whose references use one carries the row.
    banner: BannerRow | None = None
    # 108: the calendar page; only a style whose references use one carries the row.
    calendar: CalendarRow | None = None
    # 103: the picture treatments the planner may pick per still, in the renderer's
    # fallback order (a pick the image cannot take becomes the first allowed one); every
    # one but `photo` and `card` has its `motion.<name>` row. A spec from before 103 offers
    # the two it always had.
    treatments: list[PictureTreatment] = Field(default_factory=lambda: ["photo", "card"])
    # 103: the treatments never drawn on two consecutive beats (a grammar soft rule; the
    # renderer falls back past a repeat).
    no_repeat_treatments: list[PictureTreatment] = Field(default_factory=lambda: [])
    # 103: at most this many red cards per 60 s of runtime, rounded up; None: no cap.
    card_max_per_60s: int | None = Field(default=None, ge=0)
    # 102: the camera move each planner `motion` names on a full-screen still (photo,
    # crop_fill); a motion with no row keeps the `motion.photo` Ken Burns. Only the
    # `contracts.CAMERA_MOVES` names may have a row.
    motion_moves: dict[str, MoveRow] = Field(default_factory=lambda: {})

    @field_validator("motion_moves")
    @classmethod
    def _known_moves(cls, rows: dict[str, MoveRow]) -> dict[str, MoveRow]:
        unknown = sorted(set(rows) - set(CAMERA_MOVES))
        if unknown:
            raise ValueError(f"broll.motion_moves names {unknown}, not camera moves "
                             f"{list(CAMERA_MOVES)} (102)")  # fmt: skip
        return rows


class Captions(CaptionStyle):
    """The 6.2 typography (`CaptionStyle`) plus the 6.1 pager numbers."""

    words_per_page: tuple[int, int]
    prefer: int
    emphasis_max_ratio: float
    gap_break_s: float


WHOOSH = "whoosh"
TICK = "tick"
DING = "ding"
FLOOR_CLASSES: tuple[str, ...] = ("bass", "drum", "thump")
# 070: the triggers a mark row may name besides the style's own non-cut enters.
POP = "pop"  # the enter of a 061 text pop, a 062 sticker or a 063 bubble
IDEA_STICKER = "idea_sticker"  # the pop-in of a 062 sticker tagged `idea`


class Mark(StrictModel):
    """060 / 070 (7.3 as amended): where a soft mark may sit. A cue of the row's kind is
    allowed only on one of the `on` triggers, at most `max_per_60s` of them (scaled to
    the runtime, rounded up), `min_gap_s` apart, each file no longer than `max_len_s`.
    `sound.whoosh.on` names the style's non-cut enters and `pop`, `sound.tick.on` names
    `pop`, `sound.ding.on` names `idea_sticker`; the loader refuses any other trigger.
    Sweeps, risers and rumble crescendos stay banned everywhere."""

    max_per_60s: int = Field(ge=0)
    min_gap_s: float = Field(default=0.0, ge=0.0)
    max_len_s: float = Field(gt=0.0)
    on: list[str] = Field(min_length=1)


Whoosh = Mark  # 060's name for the whoosh row


class Sound(StrictModel):
    """7.3 bed, envelope and cue numbers; the 7.1 floor hits; the forbidden list; the
    7.2 bed-score line under which the audio search is asked (024) and the plain words
    that search falls back to last (`default_bed_query`, 054); the whoosh allowance a
    style may carry (060). 069: `bed_query_anchor` rides on every bed search rung, and
    `speech_band_margin_max_db` bounds the speech-band margin from above - a bed further
    under the voice than that in the band a phone speaker plays is not heard."""

    bed_score_threshold: float
    default_bed_query: str = Field(min_length=1)
    bed_query_anchor: str = Field(min_length=1)
    bed_db_under_voice: float
    bed_accept_db: tuple[float, float]
    speech_band_hz: tuple[int, int]
    speech_band_margin_db: float
    speech_band_margin_max_db: float
    duck_max_db: float
    swell_max_db: float
    drop_min_db: float
    ramp_min_s: float
    fade_in_s: float
    fade_out_s: float
    floor_hits: dict[str, list[str]]
    cues_max_per_60s: int
    cues_per_beat_max: int
    cue_db_min: float
    cue_db_max: float
    forbidden: list[str]
    # 060: present only where `whoosh` is out of `forbidden` (`check` asserts both).
    whoosh: Mark | None = None
    # 070: the closed palette's other marks, and the longest file each floor class may
    # play (every kind has a length; the tick, whoosh and ding rows carry their own).
    tick: Mark
    ding: Mark
    floor_max_len_s: dict[str, float]
    # 076: at most this many bed changes per short, each on a story-part boundary, and how
    # long each `how` takes - the crossfade, the silence of a drop, the fade either side
    # of a hard cut (and around the silence).
    bed_changes_max: int = Field(ge=0)
    bed_crossfade_s: float = Field(gt=0.0)
    bed_silence_s: float = Field(gt=0.0)
    bed_cut_fade_s: float = Field(gt=0.0)
    # 087: a flavour or mood miss takes an approved `facts_default` bed before a same-mood
    # bed of another flavour (true), or after it (false, 076's order).
    facts_default_first: bool


def allows_whoosh(nums: Sound) -> bool:
    """060 (3): a style allows whooshes by leaving `whoosh` out of `sound.forbidden`
    and carrying `sound.whoosh`; the loader refuses one without the other."""
    return WHOOSH not in nums.forbidden and nums.whoosh is not None


def is_whoosh(intent: str) -> bool:
    """A cue intent that names a whoosh (060): the tag the library and the planner use."""
    return intent.strip().lower() == WHOOSH


class FinaleSpec(StrictModel):
    kind: str
    mode: str
    min_s: float
    max_s: float
    cta: bool


class Budget(StrictModel):
    """5.5 / 5.6 per-step allowances; the ledger prices them (011)."""

    judge_max_calls: int
    search_max_queries: int
    gen_max_per_short: int


class FrontMatter(StrictModel):
    # 035 / 1.2: the spec's own version, recorded on every job it judged (`meta.json`);
    # bumped by hand whenever a number or a prose section changes.
    version: str
    status: Status
    aliases: list[str] = Field(min_length=1)
    requires_components: list[str]
    beats: Beats
    presenter: Presenter
    pip: Pip
    broll: Broll
    captions: Captions
    sound: Sound
    finale: FinaleSpec
    cut: Cut
    budget: Budget
    palette: Palette


class StyleSpec(FrontMatter):
    """One loaded spec: the front matter numbers plus the prose sections."""

    name: str
    prose: str
    sections: dict[str, str]

    def numbers(self) -> dict[str, Any]:
        """The front matter as plain data: what the planner prompt embeds (1.2)."""
        return self.model_dump(exclude={"name", "prose", "sections"})

    def caption_style(self) -> CaptionStyle:
        """Only the 6.2 typography fields, as the render spec carries them."""
        return CaptionStyle.model_validate(
            self.captions.model_dump(include=set(CaptionStyle.model_fields))
        )


# --- parsing ---------------------------------------------------------------------------

_FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)
_SECTION = re.compile(r"^## (.+?)\s*$", re.MULTILINE)


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """The YAML mapping between the `---` fences and the markdown body after them."""
    match = _FRONT.match(text)
    if match is None:
        raise StyleError("no YAML front matter between --- fences")
    loaded: object = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise StyleError("front matter is not a mapping")
    front: dict[str, Any] = {str(k): v for k, v in loaded.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return front, match.group(2)


def split_sections(body: str) -> dict[str, str]:
    """`## Heading` sections of the body, in file order, heading -> text."""
    found = list(_SECTION.finditer(body))
    sections: dict[str, str] = {}
    for i, match in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(body)
        sections[match.group(1)] = body[match.end() : end].strip()
    return sections


def parse(text: str, *, name: str) -> StyleSpec:
    """One spec from its file text; `StyleError` names `name` in every message."""
    try:
        front, body = split_front_matter(text)
    except StyleError as exc:
        raise StyleError(f"{name}: {exc}") from None
    for group in KEY_GROUPS:
        if group not in front:
            raise StyleError(f"{name}: missing key group {group!r}")
    try:
        matter = FrontMatter.model_validate(front)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise StyleError(f"{name}: invalid front matter: {problems}") from None
    sections = split_sections(body)
    if list(sections) != list(PROSE_SECTIONS):
        raise StyleError(
            f"{name}: prose sections must be exactly {list(PROSE_SECTIONS)}, "
            f"found {list(sections)}"
        )
    for heading, content in sections.items():
        if not content:
            raise StyleError(f"{name}: prose section {heading!r} is empty")
    return StyleSpec(**matter.model_dump(), name=name, prose=body.strip(), sections=sections)


# --- validation across a spec and the registry ----------------------------------------


def caption_block_top(captions: CaptionStyle) -> float:
    """The y of the caption block's top edge when every line is used (6.3)."""
    return captions.anchor_y - captions.max_lines * captions.size_px * captions.line_height


def check(spec: StyleSpec, registry: Sequence[str]) -> None:
    """The cross-field asserts: 6.3 collision, 9.2 components for shipped specs, the
    069 speech-band window (the ceiling not under the floor), and the 060 whoosh
    allowance (the row and the forbidden list agree)."""
    if spec.captions.max_width_px > BAND_WIDTH:
        raise StyleError(
            f"{spec.name}: captions.max_width_px {spec.captions.max_width_px} is wider than "
            f"the safe band {BAND_WIDTH:g} px (067: x {BAND_LEFT:g} to {BAND_RIGHT:g}, 6.3)"
        )
    block_top = caption_block_top(spec.captions)
    bottom = spec.pip.top + spec.pip.diameter
    if bottom > block_top:
        raise StyleError(
            f"{spec.name}: pip.top + pip.diameter = {bottom} passes the caption block top "
            f"{block_top:g} (6.3: pip.top + pip.diameter <= captions.anchor_y - "
            "captions.max_lines x line height)"
        )
    if spec.sound.speech_band_margin_max_db < spec.sound.speech_band_margin_db:
        raise StyleError(
            f"{spec.name}: sound.speech_band_margin_max_db "
            f"{spec.sound.speech_band_margin_max_db:g} is below sound.speech_band_margin_db "
            f"{spec.sound.speech_band_margin_db:g}; no bed could pass (069)"
        )
    forbidden = WHOOSH in spec.sound.forbidden
    if forbidden and spec.sound.whoosh is not None:
        raise StyleError(
            f"{spec.name}: sound.whoosh is set while {WHOOSH!r} is in sound.forbidden; a "
            "style allows whooshes by leaving it out of the list (060)"
        )
    if not forbidden and spec.sound.whoosh is None:
        raise StyleError(
            f"{spec.name}: {WHOOSH!r} is out of sound.forbidden but there is no sound.whoosh "
            "row (max_per_60s, min_gap_s, max_len_s, on) to bound it (060)"
        )
    _check_marks(spec)
    _check_treatments(spec)
    _check_offered(spec)
    if spec.status == "shipped":
        missing = [c for c in spec.requires_components if c not in registry]
        if missing:
            raise StyleError(
                f"{spec.name}: shipped but requires_components {missing} are not in the "
                f"renderer registry {list(registry)} (9.2)"
            )


def _check_treatments(spec: StyleSpec) -> None:
    """103: a treatment the style offers is a component it requires (a shipped spec), and
    only an offered one may be kept from running twice in a row."""
    b = spec.broll
    stray = [t for t in b.no_repeat_treatments if t not in b.treatments]
    if stray:
        raise StyleError(
            f"{spec.name}: broll.no_repeat_treatments {stray} are not in broll.treatments "
            f"{b.treatments} (103)"
        )
    if spec.status != "shipped":
        return
    missing = [t for t in b.treatments if t not in spec.requires_components]
    if missing:
        raise StyleError(
            f"{spec.name}: broll.treatments {missing} are not in requires_components; every "
            "treatment the planner may pick is a registered component the style requires (103)"
        )


def offered_components(spec: StyleSpec) -> list[str]:
    """107-109: the components a style offers by carrying their row or enabling them -
    each one a shipped spec must require."""
    b = spec.broll
    offered = ["banner"] if b.banner is not None else []
    if b.calendar is not None:
        offered.append("calendar")
    if "light_flare" in b.enter_transitions:
        offered.append("light_flare")
    return offered


def _check_offered(spec: StyleSpec) -> None:
    """107: an enabled `light_flare` carries its `broll.transitions.light_flare` row, and a
    shipped spec requires every component it offers."""
    b = spec.broll
    if "light_flare" in b.enter_transitions and b.transitions.light_flare is None:
        raise StyleError(
            f"{spec.name}: broll.enter_transitions enables light_flare but there is no "
            "broll.transitions.light_flare row (duration_s, core, glow, from_x, to_x, y, "
            "max_per_60s; 107)"
        )
    if spec.status != "shipped":
        return
    missing = [c for c in offered_components(spec) if c not in spec.requires_components]
    if missing:
        raise StyleError(
            f"{spec.name}: offers {missing} but they are not in requires_components; a "
            "shipped style requires every component it offers (107)"
        )


def mark_triggers(spec: StyleSpec) -> dict[str, tuple[str, ...]]:
    """070: the triggers each mark row may name - a whoosh any non-cut enter the style
    allows or a pop-in, a tick a pop-in, a ding an `idea` sticker's pop-in."""
    moving = tuple(t for t in spec.broll.enter_transitions if t != "cut")
    return {WHOOSH: (*moving, POP), TICK: (POP,), DING: (IDEA_STICKER,)}


def _check_marks(spec: StyleSpec) -> None:
    """070: every mark row names only triggers it may sit on, and every floor class the
    style earns has a length."""
    nums = spec.sound
    rows = {WHOOSH: nums.whoosh, TICK: nums.tick, DING: nums.ding}
    for kind, allowed in mark_triggers(spec).items():
        row = rows[kind]
        if row is None:
            continue
        unknown = [t for t in row.on if t not in allowed]
        if unknown:
            raise StyleError(
                f"{spec.name}: sound.{kind}.on names {unknown}, not a trigger a {kind} may "
                f"sit on here ({list(allowed)}; 070)"
            )
    for hit in nums.floor_hits:
        if hit not in FLOOR_CLASSES:
            raise StyleError(
                f"{spec.name}: sound.floor_hits class {hit!r} is not one of the palette's "
                f"floor classes {list(FLOOR_CLASSES)} (070)"
            )
        if hit not in nums.floor_max_len_s:
            raise StyleError(
                f"{spec.name}: sound.floor_max_len_s has no length for the floor class "
                f"{hit!r} (070: every kind has a length)"
            )


def load_all(registry: Sequence[str], styles_dir: Path = STYLES_DIR) -> dict[str, StyleSpec]:
    """Every `<name>.md` under `styles_dir`, validated; the default must be shipped."""
    specs: dict[str, StyleSpec] = {}
    for path in sorted(styles_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        spec = parse(path.read_text(encoding="utf-8"), name=path.stem)
        check(spec, registry)
        specs[spec.name] = spec
    if DEFAULT not in specs:
        raise StyleError(f"{DEFAULT}: no styles/{DEFAULT}.md; the resolver falls back to it (1.1)")
    if specs[DEFAULT].status != "shipped":
        raise StyleError(f"{DEFAULT}: must be shipped, it is the fallback style (1.4)")
    return specs


def shipped(specs: Mapping[str, StyleSpec]) -> list[str]:
    """Names the upload form offers as chips (2.1)."""
    return [name for name, spec in specs.items() if spec.status == "shipped"]


# --- resolver (1.1, 1.4) ---------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass(frozen=True)
class Resolution:
    name: str
    note: str
    notice: str = ""


def tokens(line: str) -> list[str]:
    return _TOKEN.findall(line.lower())


def _hits(words: Sequence[str], alias: str) -> int:
    """How often `alias` occurs in the line's tokens: a one-word alias per token, a
    multi-word alias (059: "vishva gyan", "fast facts") as a run of tokens."""
    phrase = tokens(alias)
    n = len(phrase)
    if n == 0:
        return 0
    return sum(1 for i in range(len(words) - n + 1) if list(words[i : i + n]) == phrase)


def resolve(line: str, specs: Mapping[str, StyleSpec]) -> Resolution:
    words = tokens(line)
    scores = {
        name: sum(_hits(words, a) for a in {a.lower() for a in spec.aliases})
        for name, spec in specs.items()
    }
    best = max(scores.values(), default=0)
    winners = [name for name, score in scores.items() if score == best]
    if best == 0 or len(winners) != 1:
        return Resolution(name=DEFAULT, note=line)
    (winner,) = winners
    if specs[winner].status != "shipped":
        return Resolution(
            name=DEFAULT, note=line, notice=f"{winner} not available yet, using {DEFAULT}"
        )
    return Resolution(name=winner, note=line)
