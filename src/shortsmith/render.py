"""The Python half of the picture engine (decision 9.1, ticket 004).

`build_spec` is pure: from the PicturePlan and the laid-out captions (`captions.build`,
ticket 010: word boxes already measured, wrapped and anchored, times on the cut
timeline) it resolves everything the Remotion composition needs into a `RenderSpec`
(frames not seconds, the caption boxes and `beats_with_two_lines` as given, the PIP
circle and crop window, the palette, the 6.2 typography numbers). The composition
under `src/remotion/` draws what it is given and measures nothing.

`render_picture(job)` writes `work/render_spec.json`, runs `src/remotion/driver.mjs`
(which bundles once into `build/remotion/` and renders through `@remotion/renderer`
with concurrency 2 and bt709), streams the driver's `progress N/M` lines to the
caller, keeps the full driver output in `work/render.log` and leaves
`work/picture.mp4`, silent H.264.

The ffmpeg half (ticket 005, decision 9.1) wraps it. `cut_presenter` builds
`work/cut.mp4` from the plan's cut list (`presenter.cut_list`): one trim/concat graph,
the largest centred 9:16 window under the 1.5x rule scaled to 1080x1920, re-encoded
once to constant-frame-rate H.264 with `-bf 0` so the B-frame pyramid failure cannot
occur; the composition reads this cut, never the raw upload. `voice_stem` runs the same
span graph on the raw audio through the 7.3 voice chain verbatim (mono fold inside the
graph, high-pass 80 Hz, compressor -18 dB ratio 2.5, two-pass loudnorm -19 LUFS /
-3 dBTP) into `work/stems/voice.wav`. `sound_mix` then runs the sound director over the
job's plan and sound story (`sound.build_mix`, ticket 022): the bed and the cues from the
audio catalogue become `work/stems/music.wav` and `work/stems/sfx.wav`, and the premix is
what `mux` masters (two-pass loudnorm -14 LUFS / -1.5 dBTP less `AAC_HEADROOM_DB` so the
encoded file still meets -1.5 dBTP, then the 0.891 limiter with auto-level off so the
target holds) into `work/stems/mix.wav`, muxing it with the picture stream copied
bit-for-bit into `out/short.mp4` (revision proof (a), 10.1). The music and SFX files get
their rights rows here (5.4). An empty catalogue leaves the short as the voice alone.
Stems always sit beside the mix under `work/stems/`. `render_short` is the whole
`rendering` step.

Style numbers come from the style front matter (ticket 008, decision 1.2):
`numbers_for(spec)` narrows a loaded `StyleSpec` to the `StyleNumbers` the builder
reads (the 6.2 typography, the 3.3 / 6.3 PIP geometry, the palette), and
`style_numbers(name)` looks a style up in the specs loaded once per process.

Component registry (9.2): `src/remotion/registry.json` is the checked-in list the
Node test asserts against the component files; `registry()` reads the same file.

B-roll (ticket 016; decisions 4.1, 4.4, 5.3): `build_spec` takes the asset step's
manifest and gives every `photo` / `card` beat that shows an asset a `VisualSpec`.
A photo is full-bleed with the style's Ken Burns (`broll.motion.photo`, 1.10 -> 1.16
on explainer), in and out and the pan direction alternating per consecutive
photo/card beat. A card is the framed archival look from `broll.motion.card`: a card
min(980, 650 x aspect) wide border included (5.3; the reference card measures ~982 px
across), its image never over a 1.5x upscale, inside a white border, tilted, with a
caption strip when the beat carries a lower-third label and the red ring when it
carries a ring event; behind it the same image blurred and
darkened as the cover, which takes the card's push (1.45 -> 2.1), while the card body
takes the Ken Burns ratio of the photo motion (5.3: the Ken Burns is on the card, not
the cover). The card is centred horizontally with its bottom, at full push and tilt,
`PIP_GAP_PX` above the PIP circle as in the reference frames (dyson_05, nkb_06: a
card from y ~190 to ~925 over a PIP at 960), and never below
`broll.card_max_bottom_y`. The circle top it clears is the one the spec draws: the
measured geometry on a job (a large face lifts it to 920, 3.3), `fixed_pip` on an
unmeasured spec (051). A rung-4 rescue is drawn as `pip` over the gradient;
other kinds keep their visuals for their own tickets. The engine constants below
(strip, blur, ring) are not style numbers yet.

Set pieces and overlays (ticket 026; decisions 3.2, 3.4, 4.1, 4.2, 6.1, 6.3): every
`BeatSpec` also carries what lands on it, already measured and placed.

- `finale` on the finale beat: the presenter cut in a ringed centre circle with the
  short's first `broll.motion.finale.cards` distinct images around it (the opening's
  strongest images first, 055: the references close the loop with the faces they
  opened on), labelled with the lower-third of the beat that sourced them, and the
  payoff word under them. The beat's length must sit inside `finale.min_s`-`max_s`
  and no caption page may run into it, or the build fails here rather than on screen.
  There is no hook-cards beat any more (055): the short opens in `pip` over images.
- `stamp` wherever a beat lands one, or carries a rescue word (4.4): the text measured
  at 92 px, shrunk until it fits, and clamped into the style's top
  `broll.stamp_max_y_fraction` of the frame, clear of the platform's right rail. Over
  an image with a detected face (056 (4); the 3.3 detector on the image itself) the
  stamp or counter moves to the largest face-free band of the image - its upper third,
  its lower third, or below it (`stamp_clear_of`) - and stays where it was when there
  is no face or no free band; one `stamp:` line in job.log either way.
- `lower_third` on a beat whose event is one, unless a two-line caption page shows
  over it (6.3) or the beat's own card strip already carries the same text.
- `punch_in` on every `full` beat: the research section 2 push with its grade.

The three remaining tier-1 set pieces (ticket 027; decisions 4.1, 5.2, 5.3, 9.2) are
built the same way, from the beat's own `set_piece_title` and `items`, whose asset ids
resolve through the manifest's aliases exactly as the finale's cards do (an item is a
montage member, never a showing):

- `list` on a `list` beat: a header over one pill per item, each springing in from an
  alternating side over the beat's dimmed base still (nkb_04).
- `split` on a `split` beat: the 5.2 news-card composite - two panes in one framed card
  above the PIP, the right one sliding in, a circular badge (the beat's own asset)
  overlapping the top-left corner, and a title strip whose pane words are boxed in the
  accent.
- `wall` on a `wall` beat: a 2x2 to 3x3 grid filling the band above
  `broll.card_max_bottom_y`, cells flying in from alternating sides, each with its own
  Ken Burns, over the dimmed base still (nkb_09).

Ticket 020 adds the `map`: `infographics.resolve_map` projects the bundled Natural Earth
layers into pixels and places the markers by the geocoder's coordinates; `build_spec`
takes the geocoder (the bundled gazetteer by default) and binds it to the job's directory
for the fallback's cache. A map beat sources no picture (`assets.NOT_SOURCED`). Ticket
028 animates it: the beat's `pin_drop`, `route_arrow` and `object_path` overlays are
timed by `infographics.map_timeline` from the beat's length and drawn by the components
of the same names over the base; every pixel is the layout's.

Ticket 029 adds the two overlays: `label_flyin` is the diagram's labels flying in (their
stagger and edges are `infographics.resolve_diagram`'s), and `counter` on a beat whose plan
carries `counter` numbers - the digits of every frame written in
`broll.motion.counter.grouping`, landing in the stamp's time with its shake, in the stamp's
box measured on the widest text it shows (`counter_spec`).

Ticket 030 (decision 9.4) carries the style's enter vocabulary on the spec
(`RenderSpec.transitions`: the enabled subset from `broll.enter_transitions` and the
numbers from `broll.transitions`), and `build_spec` refuses a beat whose `enter` is
outside that list - the grammar already rejects it; this is the renderer's own guard.
The composition draws each beat's picture through its `enter` and holds the previous
beat beneath a `fade` or `wipe`, so the exit is always a cut or a fade.

Every number the style front matter carries (the four `broll.motion` rows, the two y
bands, the card count, the stamp palette name, `finale.min_s`/`max_s`, the transition
rows) is read from it; the geometry read off the reference frames stays in the
constants below.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Literal, cast

from shortsmith import (
    assets,
    ffmpeg,
    geo,
    infographics,
    jobs,
    presenter,
    rights,
    sound,
    styles,
    subproc,
)
from shortsmith.captions import measure
from shortsmith.contracts import (
    AssetManifest,
    AudioEntry,
    BadgeSpec,
    Beat,
    BeatSpec,
    Bubble,
    BubbleDot,
    BubbleSpec,
    CaptionPageSpec,
    Captions,
    CaptionStyle,
    CardBox,
    CardSpec,
    ChartLayout,
    CounterPlan,
    CounterSpec,
    Crop,
    DiagramLayout,
    FaceBox,
    FinaleCardSpec,
    Highlight,
    HighlightRecord,
    HighlightSpec,
    LineBox,
    ListRow,
    ListSpec,
    LowerThirdSpec,
    MapLayout,
    MarkerLine,
    Mode,
    Palette,
    PicturePlan,
    PipGeometry,
    PunchIn,
    RenderSpec,
    SoundStory,
    Span,
    SplitPane,
    SplitSpec,
    StampSpec,
    Sticker,
    StickerSpec,
    TextPop,
    TextPopSpec,
    TitleStripSpec,
    TitleWord,
    TransitionStyle,
    VisualSpec,
    WallSpec,
)
from shortsmith.jobs import Job
from shortsmith.safe_area import (  # 067: the one 6.2/6.3 definition
    HEIGHT,
    SAFE_BOTTOM_PX,
    SAFE_LEFT,
    SAFE_RIGHT_PX,
    SAFE_TOP_PX,
    WIDTH,
)
from shortsmith.sound import remembered
from shortsmith.styles import StyleSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTION_DIR = REPO_ROOT / "src" / "remotion"
DRIVER = REMOTION_DIR / "driver.mjs"
REGISTRY_PATH = REMOTION_DIR / "registry.json"
FPS = 30
CONCURRENCY = 2  # decision 9.1
DRIVER_TIMEOUT_S = 3600.0
FFMPEG_TIMEOUT_S = 1800.0

# Decision 7.3 (research §5) sound numbers.
VOICE_LUFS, VOICE_TP = -19.0, -3.0
MASTER_LUFS, MASTER_TP = -14.0, -1.5
# T4 (10.1) measures the delivered AAC, and the encoder overshoots the mastered WAV's
# true peak by a few tenths of a dB (the fixture: -1.50 -> -1.42 dBTP), so loudnorm is
# asked for the ceiling less this headroom and the delivered file meets MASTER_TP (006).
AAC_HEADROOM_DB = 0.5
LIMITER = 0.891
SAMPLE_RATE = 48000


class RenderError(RuntimeError):
    """The driver failed; the message carries the tail of its output."""


# --- style numbers (decision 1.2: read from front matter, never from code) --------------


@dataclass(frozen=True)
class PipNumbers:
    diameter: int
    large_face_diameter: int
    chin_anchor: float
    left: int
    ring_px: int
    ring_color: str


@dataclass(frozen=True)
class BackdropNumbers:
    """103: `broll.motion.backdrop` - the sharp image at most `width_px` wide and never
    over `max_upscale`, pushing `scale_from` -> `scale_to`, over its own copy blurred
    `blur_px` and darkened to `brightness`."""

    scale_from: float
    scale_to: float
    width_px: float
    max_upscale: float
    blur_px: int
    brightness: float


@dataclass(frozen=True)
class CropFillNumbers:
    """103: `broll.motion.crop_fill` - full screen round the face (its centre at `face_y`
    of the height), never over `max_upscale`, pushing `scale_from` -> `scale_to`."""

    scale_from: float
    scale_to: float
    max_upscale: float
    face_y: float


@dataclass(frozen=True)
class PolaroidNumbers:
    """103: `broll.motion.polaroid` - the print `width_px` wide, `border_px` white round
    the picture and `bottom_px` under it, the picture never over `max_upscale`; its tilt
    within `tilt_min_deg`-`tilt_max_deg`, dropping `drop_px` in `drop_s` under a
    `shadow_px` shadow, over its copy blurred `blur_px` and darkened to `brightness`."""

    width_px: float
    border_px: int
    bottom_px: int
    max_upscale: float
    tilt_min_deg: float
    tilt_max_deg: float
    drop_px: float
    drop_s: float
    shadow_px: float
    blur_px: int
    brightness: float


@dataclass(frozen=True)
class BrollNumbers:
    """`broll.motion.*` and the geometry limits of 4.1 / 6.3: the photo and card
    motions, the card's bottom limit, and (026) the stamp, lower-third and finale
    motion rows (the finale's card count included, 055) plus the stamp's y band."""

    photo_scale_from: float
    photo_scale_to: float
    photo_alternate: bool
    card_scale_from: float
    card_scale_to: float
    card_border_px: int
    card_rotate_deg: float
    card_ring_color: str
    card_max_bottom_y: int
    pip_top: int
    stamp_land_s: float
    stamp_shake: bool
    stamp_palette: str
    stamp_max_y_fraction: float
    lower_third_fade_s: float
    lower_third_top_y: int
    lower_third_bottom_y: int
    finale_cards: int
    finale_fade_s: float
    # 027: the three set pieces' counts, entry times and (list, wall) base still motion.
    list_items_max: int
    list_reveal_s: float
    list_scale_from: float
    list_scale_to: float
    list_dim: float
    split_panes: int
    split_slide_s: float
    # 059: `side` (the 5.2 news card, the panes side by side) or `stacked` (two pictures,
    # top and bottom: the Vishva Gyan panels); a row without `layout` is side by side.
    split_layout: str
    # 105: where a pane's detected face sits, as a fraction of the pane picture's height
    # (its centre); the pane is framed round it (`objectPosition`), never cut at the centre.
    split_face_y: float
    # 105: where a pane with no face found is framed (`objectPosition` y): a split pane is
    # a portrait (5.2), so the top, where a head the detector missed most likely is.
    split_faceless_y: float
    wall_cells_min: int
    wall_cells_max: int
    wall_spring_s: float
    wall_scale_from: float
    wall_scale_to: float
    wall_dim: float
    # 029: the counter's digit grouping; it lands in the stamp's time with its shake.
    counter_grouping: str
    # 061: the text pop row - the overshoot's length, how long a pop may stay, the
    # per-beat cap, the tilt, the type size and the style's pop yellow.
    pop_s: float
    pop_hold_max_s: float
    pop_max_per_beat: int
    pop_tilt_deg: float
    pop_font_px: int
    pop_fill: str
    # 063: the bubble row - the overshoot's length, how long a bubble may stay, the
    # per-beat cap, the word cap, the type size and its floor, the body width, the white
    # fill and the dark ink. The dialogue gap is the grammar's, not drawn.
    bubble_s: float
    bubble_hold_max_s: float
    bubble_max_per_beat: int
    bubble_words_max: int
    bubble_font_px: int
    bubble_min_font_px: int
    bubble_width_px: int
    bubble_fill: str
    bubble_ink: str
    # 062: the sticker row - the overshoot's length, how long a sticker may stay, the
    # per-beat cap, the square's size (180-320 px) and the gentle float's height and period.
    sticker_s: float
    sticker_hold_max_s: float
    sticker_max_per_beat: int
    sticker_size_px: int
    sticker_float_px: float
    sticker_float_period_s: float
    # 058: the clip row - the slow push over the beat (1.0 -> 1.0: the clip's own movement
    # is the motion) and the playback speed.
    clip_scale_from: float
    clip_scale_to: float
    clip_speed: float
    # 078: the highlight row - the marker's colour and opacity, its padding round a text
    # line, and how far the screenshot card pushes toward the lines over the beat.
    highlight_color: str
    highlight_opacity: float
    highlight_pad_px: float
    highlight_push_to: float
    # 103: the treatments the planner may pick per still (the fallback order), the ones
    # never drawn twice in a row, the card's cap per 60 s (None: none) and the rows of the
    # three new treatments (None where the style does not offer it).
    treatments: tuple[str, ...] = ("photo", "card")
    no_repeat: frozenset[str] = frozenset()
    card_max_per_60s: int | None = None
    backdrop: BackdropNumbers | None = None
    crop_fill: CropFillNumbers | None = None
    polaroid: PolaroidNumbers | None = None


@dataclass(frozen=True)
class FinaleNumbers:
    """The `finale` key group: the set piece's length band (3.4)."""

    min_s: float
    max_s: float


@dataclass(frozen=True)
class StyleNumbers:
    captions: CaptionStyle
    pip: PipNumbers
    palette: Palette
    broll: BrollNumbers
    finale: FinaleNumbers
    # 021: the `chart` and `infographic` rows, read by `infographics`.
    info: infographics.InfographicNumbers
    # 030: the 9.4 enter list and numbers, carried on the spec verbatim.
    transitions: TransitionStyle
    # 059: the fixed title strip's row, where the style draws one.
    title_strip: styles.TitleStrip | None = None


def broll_numbers(spec: StyleSpec) -> BrollNumbers:
    try:
        motion = spec.broll.motion
        photo, card = motion["photo"], motion["card"]
        stamp, lower, finale = motion["stamp"], motion["lower_third"], motion["finale"]
        rows, split, wall = motion["list"], motion["split"], motion["wall"]
        pop, bubble, clip = motion["text_pop"], motion["bubble"], motion["clip"]
        sticker, highlight = motion["sticker"], motion["highlight"]
        backdrop, crop_fill, polaroid = _treatment_rows(spec)
        size = int(sticker["size_px"])
        if not STICKER_SIZE_MIN_PX <= size <= STICKER_SIZE_MAX_PX:
            raise styles.StyleError(
                f"{spec.name}: broll.motion.sticker.size_px {size} is outside "
                f"{STICKER_SIZE_MIN_PX}-{STICKER_SIZE_MAX_PX} px (062)"
            )
        return BrollNumbers(
            photo_scale_from=float(photo["scale_from"]),
            photo_scale_to=float(photo["scale_to"]),
            photo_alternate=bool(photo["alternate"]),
            card_scale_from=float(card["scale_from"]),
            card_scale_to=float(card["scale_to"]),
            card_border_px=int(card["border_px"]),
            card_rotate_deg=float(card["rotate_deg"]),
            card_ring_color=str(card["ring_color"]),
            card_max_bottom_y=spec.broll.card_max_bottom_y,
            pip_top=spec.pip.top,
            stamp_land_s=float(stamp["duration_s"]),
            stamp_shake=bool(stamp["shake"]),
            stamp_palette=str(stamp["palette"]),
            stamp_max_y_fraction=spec.broll.stamp_max_y_fraction,
            lower_third_fade_s=float(lower["duration_s"]),
            lower_third_top_y=int(lower["top_y"]),
            lower_third_bottom_y=int(lower["bottom_y"]),
            finale_cards=int(finale["cards"]),
            finale_fade_s=float(finale["duration_s"]),
            list_items_max=int(rows["items_max"]),
            list_reveal_s=float(rows["duration_s"]),
            list_scale_from=float(rows["scale_from"]),
            list_scale_to=float(rows["scale_to"]),
            list_dim=float(rows["dim"]),
            split_panes=int(split["panes"]),
            split_slide_s=float(split["duration_s"]),
            split_layout=_split_layout(spec.name, split),
            split_face_y=float(split["face_y"]),
            split_faceless_y=float(split["faceless_y"]),
            wall_cells_min=int(wall["cells_min"]),
            wall_cells_max=int(wall["cells_max"]),
            wall_spring_s=float(wall["duration_s"]),
            wall_scale_from=float(wall["scale_from"]),
            wall_scale_to=float(wall["scale_to"]),
            wall_dim=float(wall["dim"]),
            counter_grouping=str(motion["counter"]["grouping"]),
            pop_s=float(pop["duration_s"]),
            pop_hold_max_s=float(pop["hold_max_s"]),
            pop_max_per_beat=int(pop["max_per_beat"]),
            pop_tilt_deg=float(pop["tilt_deg"]),
            pop_font_px=int(pop["size_px"]),
            pop_fill=str(pop["fill"]),
            bubble_s=float(bubble["duration_s"]),
            bubble_hold_max_s=float(bubble["hold_max_s"]),
            bubble_max_per_beat=int(bubble["max_per_beat"]),
            bubble_words_max=int(bubble["words_max"]),
            bubble_font_px=int(bubble["size_px"]),
            bubble_min_font_px=int(bubble["min_size_px"]),
            bubble_width_px=int(bubble["width_px"]),
            bubble_fill=str(bubble["fill"]),
            bubble_ink=str(bubble["ink"]),
            sticker_s=float(sticker["duration_s"]),
            sticker_hold_max_s=float(sticker["hold_max_s"]),
            sticker_max_per_beat=int(sticker["max_per_beat"]),
            sticker_size_px=size,
            sticker_float_px=float(sticker["float_px"]),
            sticker_float_period_s=float(sticker["float_period_s"]),
            clip_scale_from=float(clip["scale_from"]),
            clip_scale_to=float(clip["scale_to"]),
            clip_speed=float(clip["speed"]),
            highlight_color=str(highlight["color"]),
            highlight_opacity=float(highlight["opacity"]),
            highlight_pad_px=float(highlight["pad_px"]),
            highlight_push_to=float(highlight["push_to"]),
            treatments=tuple(spec.broll.treatments),
            no_repeat=frozenset(spec.broll.no_repeat_treatments),
            card_max_per_60s=spec.broll.card_max_per_60s,
            backdrop=backdrop,
            crop_fill=crop_fill,
            polaroid=polaroid,
        )
    except KeyError as exc:
        raise styles.StyleError(f"{spec.name}: broll.motion is missing {exc}") from None


def _treatment_rows(
    spec: StyleSpec,
) -> tuple[BackdropNumbers | None, CropFillNumbers | None, PolaroidNumbers | None]:
    """103: the rows of the new treatments the style offers; an offered one without its
    `broll.motion` row is a KeyError the caller reports."""
    offered, motion = set(spec.broll.treatments), spec.broll.motion
    backdrop = crop_fill = polaroid = None
    if "backdrop" in offered:
        r = motion["backdrop"]
        backdrop = BackdropNumbers(
            scale_from=float(r["scale_from"]), scale_to=float(r["scale_to"]),
            width_px=float(r["width_px"]), max_upscale=float(r["max_upscale"]),
            blur_px=int(r["blur_px"]), brightness=float(r["brightness"]),
        )  # fmt: skip
    if "crop_fill" in offered:
        r = motion["crop_fill"]
        crop_fill = CropFillNumbers(
            scale_from=float(r["scale_from"]), scale_to=float(r["scale_to"]),
            max_upscale=float(r["max_upscale"]), face_y=float(r["face_y"]),
        )  # fmt: skip
    if "polaroid" in offered:
        r = motion["polaroid"]
        polaroid = PolaroidNumbers(
            width_px=float(r["width_px"]), border_px=int(r["border_px"]),
            bottom_px=int(r["bottom_px"]), max_upscale=float(r["max_upscale"]),
            tilt_min_deg=float(r["tilt_min_deg"]), tilt_max_deg=float(r["tilt_max_deg"]),
            drop_px=float(r["drop_px"]), drop_s=float(r["drop_s"]),
            shadow_px=float(r["shadow_px"]), blur_px=int(r["blur_px"]),
            brightness=float(r["brightness"]),
        )  # fmt: skip
    return backdrop, crop_fill, polaroid


SPLIT_LAYOUTS = ("side", "stacked")  # 059


def _split_layout(name: str, row: Mapping[str, object]) -> str:
    layout = str(row.get("layout", "side"))
    if layout not in SPLIT_LAYOUTS:
        raise styles.StyleError(
            f"{name}: broll.motion.split.layout {layout!r} is not one of "
            f"{list(SPLIT_LAYOUTS)} (059)"
        )
    return layout


def numbers_for(spec: StyleSpec) -> StyleNumbers:
    """The subset of a loaded spec the render spec builder reads."""
    return StyleNumbers(
        broll=broll_numbers(spec),
        captions=spec.caption_style(),
        pip=PipNumbers(
            diameter=spec.pip.diameter,
            large_face_diameter=spec.pip.large_face_diameter,
            chin_anchor=spec.pip.chin_anchor,
            left=spec.pip.left,
            ring_px=spec.pip.ring_px,
            ring_color=spec.pip.ring_color,
        ),
        palette=spec.palette,
        finale=FinaleNumbers(min_s=spec.finale.min_s, max_s=spec.finale.max_s),
        info=infographics.numbers_for(spec),
        transitions=TransitionStyle(
            enabled=list(spec.broll.enter_transitions), **spec.broll.transitions.model_dump()
        ),
        title_strip=spec.broll.title_strip,
    )


@cache
def loaded_styles() -> dict[str, StyleSpec]:
    """The specs under `styles/`, validated against this project's registry, loaded
    once per process for the render path (the app and worker load their own copy)."""
    return styles.load_all(registry())


def style_numbers(name: str) -> StyleNumbers:
    return numbers_for(loaded_styles()[name])


# --- PIP geometry ----------------------------------------------------------------------


def fixed_pip(source_size: tuple[int, int], numbers: StyleNumbers) -> PipGeometry:
    """The 004 geometry, the fallback for a spec built without a measurement (the
    renderer's own tests): the style diameter, left at the style edge, bottom touching
    the caption block's top (6.3); the crop window is the largest square of full source
    width anchored at the top, centred horizontally on a landscape source. A job's spec
    carries `presenter.measure`'s geometry from `job.json` instead (013, 3.3)."""
    style = numbers.captions
    block_top = style.anchor_y - style.max_lines * style.size_px * style.line_height
    top = int(block_top) - numbers.pip.diameter
    src_w, src_h = source_size
    size = min(src_w, src_h)
    return PipGeometry(
        left=numbers.pip.left,
        top=top,
        diameter=numbers.pip.diameter,
        ring_px=numbers.pip.ring_px,
        ring_color=numbers.pip.ring_color,
        window_left=(src_w - size) // 2,
        window_top=0,
        window_size=size,
    )


# --- photo and card (ticket 016) -------------------------------------------------------

# 5.3: a card is at most 980 px wide and 650 px tall at its native aspect.
CARD_MAX_W, CARD_BASE_H, CARD_MAX_UPSCALE = 980.0, 650.0, 1.5
# Engine look constants the style front matter does not carry yet.
STRIP_PX, STRIP_FONT_PX = 64, 30
PIP_GAP_PX = 32  # the reference cards end ~35 px above the PIP circle
COVER_BLUR_PX, COVER_BRIGHTNESS = 36, 0.45
RING_FRACTION, RING_PX, RING_AT_S = 0.32, 8, 0.2  # the ring lands 0.2 s into the beat


def card_image_size(width: int, height: int, border_px: int) -> tuple[float, float]:
    """The card's image size: the card is min(980, 650 x aspect) wide border included,
    the image inside never over a 1.5x upscale (5.3)."""
    aspect = width / height
    card_w = min(CARD_MAX_W, CARD_BASE_H * aspect)
    image_w = min(card_w - 2 * border_px, CARD_MAX_UPSCALE * width)
    return image_w, image_w / aspect


def _ken_burns(index: int, low: float, high: float, alternate: bool) -> tuple[float, float]:
    return (high, low) if alternate and index % 2 else (low, high)


def _pan_sign(index: int) -> int:
    return -1 if index % 2 else 1


def photo_visual(src: str, width: int, height: int, *, index: int, crop: Crop,
                 numbers: StyleNumbers) -> VisualSpec:  # fmt: skip
    """The full-bleed photo: Ken Burns from the style, drifting across the margin the
    smaller scale leaves, direction alternating with `index` (4.1)."""
    b = numbers.broll
    scale_from, scale_to = _ken_burns(index, b.photo_scale_from, b.photo_scale_to,
                                      b.photo_alternate)  # fmt: skip
    margin = (min(scale_from, scale_to) - 1.0) * WIDTH / 2
    return VisualSpec(
        treatment="photo", src=src, width=width, height=height, zoom=crop.zoom,
        focus_x=crop.focus_x, focus_y=crop.focus_y, scale_from=scale_from, scale_to=scale_to,
        pan_px=_pan_sign(index) * margin,
    )  # fmt: skip


def base_visual(src: str, width: int, height: int, *, crop: Crop, scale_from: float,
                scale_to: float, dim: float) -> VisualSpec:  # fmt: skip
    """The still a `list` or `wall` set piece is built over (027): the full-bleed photo
    with the piece's own Ken Burns from the style and a black scrim at `dim`, so the
    rows or cells above it read (nkb_04: dim 0.45, nkb_09: 0.65). It never alternates
    and never drifts: the set piece on top carries the movement."""
    return VisualSpec(
        treatment="photo", src=src, width=width, height=height, zoom=crop.zoom,
        focus_x=crop.focus_x, focus_y=crop.focus_y, scale_from=scale_from, scale_to=scale_to,
        pan_px=0.0, dim=dim,
    )  # fmt: skip


def _half_extent(card: CardSpec, scale: float) -> float:
    """Half the height of the card's box once tilted and pushed to `scale`."""
    theta = math.radians(card.rotate_deg)
    return scale * (card.width * abs(math.sin(theta)) + card.height * math.cos(theta)) / 2


def _bottom_below_top(card: CardSpec, scale: float) -> float:
    """How far under the card's top edge its lowest point sits once pushed to `scale`
    about its origin (the centre, or a screenshot's lines, 078), tilt included."""
    origin = card.origin_y * card.height
    centre = origin + scale * (card.height / 2 - origin)
    return centre + _half_extent(card, scale)


def card_bottom(visual: VisualSpec) -> float:
    """The lowest y the card reaches over its beat (full push, tilt included)."""
    card = visual.card
    assert card is not None
    return card.top + max(_bottom_below_top(card, s) for s in (visual.scale_from, visual.scale_to))


def _card_limit(b: BrollNumbers, pip_top: int | None) -> float:
    """The lowest y a card or the split composite may reach: `PIP_GAP_PX` above the
    circle the render draws (051: the measured top, `pip_top`; the style's fixed
    `pip.top` when the spec was built without a measurement) and never below
    `broll.card_max_bottom_y` (6.3)."""
    top = b.pip_top if pip_top is None else pip_top
    return min(top - PIP_GAP_PX, b.card_max_bottom_y)


def card_visual(src: str, width: int, height: int, *, strip_text: str, ring: bool, index: int,
                crop: Crop, numbers: StyleNumbers,
                pip_top: int | None = None) -> VisualSpec:  # fmt: skip
    """The framed archival card (4.1, 5.3), placed so it ends `PIP_GAP_PX` above the
    circle top it is given (051) and above the style limit."""
    b = numbers.broll
    image_w, image_h = card_image_size(width, height, b.card_border_px)
    strip = STRIP_PX if strip_text else 0
    outer_w = image_w + 2 * b.card_border_px
    outer_h = image_h + 2 * b.card_border_px + strip
    ratio = b.photo_scale_to / b.photo_scale_from
    scale_from, scale_to = _ken_burns(index, 1.0, ratio, b.photo_alternate)
    card = CardSpec(
        left=(WIDTH - outer_w) / 2, top=0.0, width=outer_w, height=outer_h,
        image_width=image_w, image_height=image_h, border_px=b.card_border_px,
        rotate_deg=b.card_rotate_deg, strip_text=strip_text, strip_px=strip,
        strip_font_px=STRIP_FONT_PX, cover_scale_from=b.card_scale_from,
        cover_scale_to=b.card_scale_to, cover_blur_px=COVER_BLUR_PX,
        cover_brightness=COVER_BRIGHTNESS, ring=ring, ring_color=b.card_ring_color,
        ring_diameter_px=RING_FRACTION * min(image_w, image_h), ring_px=RING_PX,
        ring_at_s=RING_AT_S,
    )  # fmt: skip
    half = _half_extent(card, max(scale_from, scale_to))
    centre = _card_limit(b, pip_top) - half
    card = card.model_copy(update={"top": centre - outer_h / 2})
    return VisualSpec(
        treatment="card", src=src, width=width, height=height, zoom=crop.zoom,
        focus_x=crop.focus_x, focus_y=crop.focus_y, scale_from=scale_from, scale_to=scale_to,
        pan_px=0.0, card=card,
    )  # fmt: skip


def marker_lines(
    lines: Sequence[LineBox], *, image_width: float, image_height: float, pad_px: float,
    start_s: float, end_s: float,
) -> list[MarkerLine]:  # fmt: skip
    """078: the marker strokes over a card image of `image_width` x `image_height`: each
    text line padded by `pad_px` above and below, swept one after another from `start_s` to
    `end_s` (seconds from the beat's start) at one speed, so a line takes its share of the
    time by its width."""
    widths = [(box.right - box.left) * image_width for box in lines]
    total = sum(widths) or 1.0
    strokes: list[MarkerLine] = []
    at = start_s
    for box, width in zip(lines, widths, strict=True):
        until = at + (end_s - start_s) * width / total
        strokes.append(MarkerLine(
            left=box.left * image_width, top=box.top * image_height - pad_px, width=width,
            height=(box.bottom - box.top) * image_height + 2 * pad_px,
            start_s=at, end_s=until,
        ))  # fmt: skip
        at = until
    return strokes


def highlight_visual(
    src: str, width: int, height: int, *, highlight: Highlight, record: HighlightRecord,
    beat_start_s: float, beat_end_s: float, fps: int, numbers: StyleNumbers, pip_top: int,
) -> VisualSpec:  # fmt: skip
    """078: the owner's screenshot as a straight card (no tilt, no crop, no caption strip)
    pushing in from 1.0 to the style's `motion.highlight.push_to` about the centre of the
    highlighted lines, placed so that at full push it still ends `PIP_GAP_PX` above the
    circle and above the style limit. The marker sweeps from the sentence's first word to
    its last, and is done by the beat's last frame."""
    b = numbers.broll
    base = card_visual(src, width, height, strip_text="", ring=False, index=0, crop=Crop(),
                       numbers=numbers, pip_top=pip_top)  # fmt: skip
    card = base.card
    assert card is not None
    last_frame_s = (round(beat_end_s * fps) - 1 - round(beat_start_s * fps)) / fps
    said = highlight.at_s if highlight.at_s is not None else beat_start_s
    done = highlight.end_s if highlight.end_s is not None else beat_end_s
    start = max(said - beat_start_s, 0.0)
    end = max(min(done - beat_start_s, last_frame_s), start)
    strokes = marker_lines(
        record.lines, image_width=card.image_width, image_height=card.image_height,
        pad_px=b.highlight_pad_px, start_s=start, end_s=end,
    )  # fmt: skip
    left = min(box.left for box in record.lines) * card.image_width
    right = max(box.right for box in record.lines) * card.image_width
    top = min(box.top for box in record.lines) * card.image_height
    bottom = max(box.bottom for box in record.lines) * card.image_height
    card = card.model_copy(update={
        "rotate_deg": 0.0,
        "origin_x": (card.border_px + (left + right) / 2) / card.width,
        "origin_y": (card.border_px + (top + bottom) / 2) / card.height,
        "highlight": HighlightSpec(lines=strokes, color=b.highlight_color,
                                   opacity=b.highlight_opacity),
    })  # fmt: skip
    push = max(b.highlight_push_to, 1.0)
    reach = max(_bottom_below_top(card, s) for s in (1.0, push))
    card = card.model_copy(update={"top": _card_limit(b, pip_top) - reach})
    return base.model_copy(update={"card": card, "scale_from": 1.0, "scale_to": push})


def clip_visual(src: str, width: int, height: int, *, crop: Crop, numbers: StyleNumbers,
                start_s: float = 0.0) -> VisualSpec:  # fmt: skip
    """058: the full-screen muted clip, playing from `start_s` seconds into the file at
    the style's `broll.motion.clip.speed` with the row's slow push (1.0 -> 1.0 in every
    existing style: the clip's own movement is the motion); it never drifts."""
    b = numbers.broll
    return VisualSpec(
        treatment="clip", src=src, width=width, height=height, zoom=crop.zoom,
        focus_x=crop.focus_x, focus_y=crop.focus_y, scale_from=b.clip_scale_from,
        scale_to=b.clip_scale_to, pan_px=0.0, speed=b.clip_speed, start_s=start_s,
    )  # fmt: skip


# --- the picture treatments an editor picks (ticket 103) -----------------------------------

GOLDEN = (math.sqrt(5) - 1) / 2  # 103: spreads the polaroid tilts over their range


def pick_treatment(
    planned: str | None, allowed: Sequence[str], *, previous: str | None,
    no_repeat: frozenset[str], order: Sequence[str], cards_left: float,
) -> str:  # fmt: skip
    """103: the treatment drawn: the planner's pick when the image `allowed` it, it is not
    the `previous` beat's in `no_repeat`, and (a card) the cap has `cards_left`; else the
    first of `order` that passes the same test; else any allowed one that is not a repeat;
    else the first allowed one. Never fails: a treatment is never a reason to stop."""

    def ok(name: str) -> bool:
        if name not in allowed:
            return False
        if name in no_repeat and name == previous:
            return False
        return name != "card" or cards_left > 0

    if planned is not None and ok(planned):
        return planned
    for name in (*order, *allowed):
        if ok(name):
            return name
    for name in allowed:
        if not (name in no_repeat and name == previous):
            return name
    return allowed[0] if allowed else "card"


def _band_centre(pip_top: int | None, b: BrollNumbers) -> tuple[float, float]:
    """The band a framed picture is centred in: the safe top to the card line (051)."""
    return float(SAFE_TOP_PX), _card_limit(b, pip_top)


def backdrop_visual(src: str, width: int, height: int, *, ring: bool, crop: Crop,
                    numbers: StyleNumbers, pip_top: int | None = None) -> VisualSpec:  # fmt: skip
    """103: the image sharp across the frame - at most `width_px` wide, never over
    `max_upscale`, never taller than the band from the safe top to the card line at full
    push - centred in that band, over its own blurred, darkened copy filling 9:16 (the
    card's cover push). No border, no tilt; the ring lands on it like on a card."""
    b = numbers.broll
    bd = b.backdrop
    assert bd is not None, "the style does not offer the backdrop"
    top, limit = _band_centre(pip_top, b)
    aspect = width / height
    image_w = min(bd.width_px, bd.max_upscale * width, WIDTH)
    image_w = min(image_w, (limit - top) / bd.scale_to * aspect)
    image_h = image_w / aspect
    card = CardSpec(
        left=(WIDTH - image_w) / 2, top=(top + limit) / 2 - image_h / 2, width=image_w,
        height=image_h, image_width=image_w, image_height=image_h, border_px=0,
        rotate_deg=0.0, strip_text="", strip_px=0, strip_font_px=STRIP_FONT_PX,
        cover_scale_from=b.card_scale_from, cover_scale_to=b.card_scale_to,
        cover_blur_px=bd.blur_px, cover_brightness=bd.brightness, ring=ring,
        ring_color=b.card_ring_color, ring_diameter_px=RING_FRACTION * min(image_w, image_h),
        ring_px=RING_PX, ring_at_s=RING_AT_S,
    )  # fmt: skip
    return VisualSpec(
        treatment="backdrop", src=src, width=width, height=height, zoom=crop.zoom,
        focus_x=crop.focus_x, focus_y=crop.focus_y, scale_from=bd.scale_from,
        scale_to=bd.scale_to, pan_px=0.0, card=card,
    )  # fmt: skip


def polaroid_tilt(use: int, numbers: PolaroidNumbers) -> float:
    """103: the `use`-th polaroid's tilt, spread over the style's range (golden-ratio
    steps, so no two in a short sit at the same angle)."""
    frac = (0.5 + use * GOLDEN) % 1.0
    return round(numbers.tilt_min_deg + frac * (numbers.tilt_max_deg - numbers.tilt_min_deg), 2)


def polaroid_visual(src: str, width: int, height: int, *, label: str, ring: bool, use: int,
                    crop: Crop, numbers: StyleNumbers,
                    pip_top: int | None = None) -> VisualSpec:  # fmt: skip
    """103: the white-bordered print: `width_px` wide (narrower where the picture would
    pass `max_upscale`), `border_px` round the picture and `bottom_px` under it, where a
    lower-third label is written; its window keeps the image's aspect, cropped to fit the
    band. Tilted per use, pushing like a card, placed so it ends above the card line; it
    drops `drop_px` and settles in `drop_s` (the component animates it)."""
    b = numbers.broll
    pl = b.polaroid
    assert pl is not None, "the style does not offer the polaroid"
    aspect = width / height
    image_w = min(pl.width_px - 2 * pl.border_px, pl.max_upscale * width)
    strip = pl.bottom_px - pl.border_px
    top, limit = _band_centre(pip_top, b)
    ratio = b.photo_scale_to / b.photo_scale_from
    room = (limit - top) / ratio - pl.border_px - pl.bottom_px
    image_h = min(image_w / aspect, room)
    outer_w, outer_h = image_w + 2 * pl.border_px, image_h + pl.border_px + pl.bottom_px
    card = CardSpec(
        left=(WIDTH - outer_w) / 2, top=0.0, width=outer_w, height=outer_h,
        image_width=image_w, image_height=image_h, border_px=pl.border_px,
        rotate_deg=polaroid_tilt(use, pl), strip_text=label, strip_px=strip,
        strip_font_px=STRIP_FONT_PX, cover_scale_from=b.card_scale_from,
        cover_scale_to=b.card_scale_to, cover_blur_px=pl.blur_px,
        cover_brightness=pl.brightness, ring=ring, ring_color=b.card_ring_color,
        ring_diameter_px=RING_FRACTION * min(image_w, image_h), ring_px=RING_PX,
        ring_at_s=RING_AT_S, drop_px=pl.drop_px, drop_s=pl.drop_s, shadow_px=pl.shadow_px,
    )  # fmt: skip
    half = _half_extent(card, ratio)
    card = card.model_copy(update={"top": limit - half - outer_h / 2})
    return VisualSpec(
        treatment="polaroid", src=src, width=width, height=height, zoom=crop.zoom,
        focus_x=crop.focus_x, focus_y=crop.focus_y, scale_from=1.0, scale_to=ratio,
        pan_px=0.0, card=card,
    )  # fmt: skip


def crop_fill_visual(src: str, width: int, height: int, *, face: FaceBox,
                     numbers: StyleNumbers) -> VisualSpec:  # fmt: skip
    """103: full screen, the image cropped round the detected face - its centre across the
    middle and at `face_y` of the height, moved in just enough to keep a face that fits
    whole (`pane_focus`) - pushing slowly toward it."""
    cf = numbers.broll.crop_fill
    assert cf is not None, "the style does not offer crop_fill"
    fx, fy = pane_focus(face, width, height, float(WIDTH), float(HEIGHT), face_y=cf.face_y)
    return VisualSpec(
        treatment="crop_fill", src=src, width=width, height=height, zoom=1.0, focus_x=fx,
        focus_y=fy, scale_from=cf.scale_from, scale_to=cf.scale_to, pan_px=0.0,
    )  # fmt: skip


# 4.2: a number or quote beat stamps over the asset already on screen, so its motion
# carries on from the previous beat instead of restarting.
CONTINUING_SUBJECTS = frozenset({"number", "quote"})
# The kinds whose own asset is drawn behind them: the two B-roll treatments, the moving
# clip (058), and (027) the dimmed base still of a `list` or a `wall`. A `split` fills its
# card instead.
BASE_STILL_KINDS = frozenset({"photo", "card", "clip", "list", "wall"})


def continued(previous: VisualSpec, previous_s: float, own_s: float) -> VisualSpec:
    """`previous` carried on for `own_s` more seconds at the rate it was moving: the
    same framing, the Ken Burns picked up where it stopped, never restarted (4.2); a
    clip (058) plays on from the second the last beat stopped at."""
    span = max(previous_s, 1e-6)
    step = (previous.scale_to - previous.scale_from) * own_s / span
    updates: dict[str, object] = {
        "scale_from": previous.scale_to,
        "scale_to": max(1.0, previous.scale_to + step),
        "pan_px": previous.pan_px * own_s / span,
    }
    if previous.treatment == "clip":
        updates["start_s"] = round(previous.start_s + previous_s * previous.speed, 3)
    card = previous.card
    if card is not None:
        cover = (card.cover_scale_to - card.cover_scale_from) * own_s / span
        updates["card"] = card.model_copy(update={
            "cover_scale_from": card.cover_scale_to,
            "cover_scale_to": max(1.0, card.cover_scale_to + cover),
            "drop_px": 0.0,  # 103: a print carried on has already landed
        })  # fmt: skip
    return previous.model_copy(update=updates)


def _visuals(
    plan: PicturePlan, manifest: AssetManifest | None, job_dir: Path | None,
    numbers: StyleNumbers, *, pip_top: int, fps: int = FPS,
    face_of: Callable[[str], FaceBox | None] | None = None,
) -> dict[str, tuple[Mode, VisualSpec | None]]:  # fmt: skip
    """Per beat id: the mode to draw (a rung-4 rescue becomes `pip`) and its visual;
    `pip_top` is the top of the circle the spec draws, the cards' placement line.
    103: a still's treatment is the planner's pick among what the image allows
    (`face_of` finds its face, for `crop_fill`), never a framed one twice in a row and
    never more cards than the style's cap (`pick_treatment`)."""
    out: dict[str, tuple[Mode, VisualSpec | None]] = {}
    if manifest is None:
        return out
    if job_dir is None:
        raise ValueError("build_spec needs job_dir to resolve the manifest's asset files")
    b = numbers.broll
    runtime = plan.beats[-1].end if plan.beats else 0.0
    cards_left = (
        math.inf if b.card_max_per_60s is None
        else math.ceil(b.card_max_per_60s * runtime / 60.0 - EPS)
    )  # fmt: skip
    polaroids = 0
    drawn: str | None = None  # 103: the treatment the beat just before drew
    index = 0
    previous: tuple[Beat, VisualSpec, str] | None = None
    for beat in plan.beats:
        last, drawn = drawn, None
        decided = manifest.beat(beat.id)
        if decided is None:
            continue
        if decided.fallback_rung == 4 or decided.asset_id is None:
            out[beat.id] = ("pip", None)
            previous = None
            continue
        record = manifest.asset(decided.asset_id)
        if decided.diagram_base:
            # 021 / 9.3: a diagram base is drawn by its own layer, under the labels,
            # never as a bare photo or card.
            continue
        if beat.kind not in BASE_STILL_KINDS or record is None:
            continue
        src = str((job_dir / record.file).resolve())
        if beat.kind in ("list", "wall"):
            # 027: the beat's own asset is the set piece's dimmed base, never a card.
            b = numbers.broll
            low, high, dim = (
                (b.list_scale_from, b.list_scale_to, b.list_dim)
                if beat.kind == "list"
                else (b.wall_scale_from, b.wall_scale_to, b.wall_dim)
            )
            out[beat.id] = (beat.mode, base_visual(src, record.width, record.height,
                                                   crop=decided.crop, scale_from=low,
                                                   scale_to=high, dim=dim))  # fmt: skip
            previous = None
            continue
        carries_on = (
            beat.subject_kind in CONTINUING_SUBJECTS
            and previous is not None
            and previous[2] == decided.asset_id
        )
        found = manifest.highlight(beat.id)
        if (
            beat.highlight is not None and found is not None
            and found.asset_id == decided.asset_id and record.kind != "clip"
        ):  # fmt: skip
            # 078: the owner's screenshot as the straight card the marker sweeps.
            carries_on = False
            visual = highlight_visual(src, record.width, record.height,
                                      highlight=beat.highlight, record=found,
                                      beat_start_s=beat.start, beat_end_s=beat.end, fps=fps,
                                      numbers=numbers, pip_top=pip_top)  # fmt: skip
        elif carries_on and previous is not None:
            earlier, visual, _ = previous
            visual = continued(visual, earlier.end - earlier.start, beat.end - beat.start)
        elif decided.treatment == "clip":
            # 058: the moving clip, whatever kind the beat was planned as (a number beat
            # showing an earlier clip afresh plays it from its start).
            visual = clip_visual(src, record.width, record.height, crop=decided.crop,
                                 numbers=numbers)  # fmt: skip
        else:
            face = face_of(src) if face_of is not None else None
            allowed = assets.allowed_treatments(
                record.width, record.height, fits=decided.treatment == "photo",
                has_face=face is not None, offered=b.treatments,
                crop_fill_max_upscale=b.crop_fill.max_upscale if b.crop_fill else 0.0,
            )  # fmt: skip
            chosen = pick_treatment(
                beat.treatment or decided.treatment, allowed, previous=last,
                no_repeat=b.no_repeat, order=b.treatments, cards_left=cards_left,
            )  # fmt: skip
            label = (beat.event.text if beat.event.kind == "lower_third" else None) or ""
            ring = beat.event.kind == "ring"
            if chosen == "photo":
                visual = photo_visual(src, record.width, record.height, index=index,
                                      crop=decided.crop, numbers=numbers)  # fmt: skip
            elif chosen == "crop_fill" and face is not None:
                visual = crop_fill_visual(src, record.width, record.height, face=face,
                                          numbers=numbers)  # fmt: skip
            elif chosen == "backdrop":
                visual = backdrop_visual(src, record.width, record.height, ring=ring,
                                         crop=decided.crop, numbers=numbers,
                                         pip_top=pip_top)  # fmt: skip
            elif chosen == "polaroid":
                visual = polaroid_visual(src, record.width, record.height, label=label,
                                         ring=ring, use=polaroids, crop=decided.crop,
                                         numbers=numbers, pip_top=pip_top)  # fmt: skip
                polaroids += 1
            else:
                visual = card_visual(src, record.width, record.height, strip_text=label,
                                     ring=ring, index=index, crop=decided.crop,
                                     numbers=numbers, pip_top=pip_top)  # fmt: skip
                cards_left -= 1
        drawn = visual.treatment if beat.highlight is None or visual.treatment != "card" else None
        out[beat.id] = (beat.mode, visual)
        if not carries_on:
            index += 1
        previous = (beat, visual, decided.asset_id)
    return out


# --- set pieces and overlays (ticket 026; decisions 3.4, 4.1, 4.2, 6.3) -----------------
#
# The style front matter carries the durations, the stamp palette name, the finale's
# card count and the two y bands; these constants are the engine's look, like the card
# constants above. The finale geometry is read off the reference frames (nkb_11,
# dyson_10), the stamp and punch-in numbers off research sections 2 and 3.

FONT_STEP_PX = 4  # type shrinks in steps until a measured line fits

# The card fly-in the finale's cards (and the wall's cells) share: research S3.
CARD_STAGGER_S = 0.08
CARD_FLY_SIDE_PX, CARD_FLY_UP_PX = 900.0, 1200.0  # research S3: from 900 or 1200 px

FINALE_DIAMETER, FINALE_CENTER_Y, FINALE_RING_PX = 440.0, 850.0, 10
FINALE_TEXT_FONT_PX, FINALE_TEXT_TOP = 96, 1180.0
FINALE_CARD_IMAGE_W = 262.0
FINALE_IMAGE_MIN_H, FINALE_IMAGE_MAX_H = 200.0, 360.0
FINALE_SLOT_TOPS = (170.0, 470.0, 460.0)  # top centre, left, right (dyson_10)
FINALE_ROTATES = (2.0, -6.0, 5.0)

STAMP_FONT_PX, STAMP_MIN_FONT_PX = 92, 24  # research S3: 92 px type, 9 px border
STAMP_BORDER_PX, STAMP_RADIUS_PX = 9, 10
STAMP_PAD_X, STAMP_PAD_Y = 34.0, 16.0
STAMP_LINE_HEIGHT = 1.25
STAMP_ROTATE_DEG, STAMP_SCALE_FROM, STAMP_SHAKE_S = -4.0, 2.6, 0.25
STAMP_CENTER_Y = 620.0  # the reference stamps land around a third down the frame
STAMP_FILL = "rgba(17,17,17,0.82)"
# `broll.motion.stamp.palette` names the colour set. The plan carries no sentiment, so
# every stamp takes the set's lead colour (the references' most common one, the yellow
# price and status stamps); picking the green payoff or the red counter needs a field
# the plan does not have yet.
STAMP_PALETTES: Mapping[str, tuple[str, ...]] = {
    "yellow_green_red": ("#FFD60A", "#2ECC71", "#E53935"),
    "cyan_white": ("#22D3EE", "#FFFFFF"),
    "teal": ("#14B8A6",),
}
# 029: the counter is on screen while it counts, so its landing is a pop from this scale
# rather than the stamp's drop from 2.6.
COUNTER_POP_FROM = 1.3

LOWER_THIRD_BAR_PX, LOWER_THIRD_PAD_X = 12, 24.0
LOWER_THIRD_NAME_PX, LOWER_THIRD_ROLE_PX = 40, 28
LOWER_THIRD_NAME_WEIGHT, LOWER_THIRD_ROLE_WEIGHT = 700, 600
LOWER_THIRD_FILL = "rgba(17,17,17,0.72)"
LOWER_THIRD_SEPARATORS = ("·", "—", "–", "|", " - ")

# Research S2: the full-frame punch-in, scale and grade.
PUNCH_IN = PunchIn(
    scale_from=1.22, settle_to=1.03, settle_s=0.9, origin_y=0.30, contrast=1.06, saturate=1.08
)


@dataclass(frozen=True)
class CardSource:
    """One asset a set piece shows: the file the driver serves and its real size."""

    src: str
    width: int
    height: int
    label: str = ""


def _tilt_extent(width: float, height: float, rotate_deg: float) -> float:
    """Half the height of a box once tilted by `rotate_deg`."""
    theta = math.radians(rotate_deg)
    return (width * abs(math.sin(theta)) + height * math.cos(theta)) / 2


def _measured(text: str, *, font_px: int, style: CaptionStyle, weight: int | None = None) -> float:
    return measure(
        text,
        family=style.font_family,
        weight=weight if weight is not None else style.font_weight,
        size_px=font_px,
        letter_spacing_px=style.letter_spacing_px,
    )


def _box(
    source: CardSource, *, image_w: float, min_h: float, max_h: float, strip_px: int,
    strip_font_px: int, border_px: int,
) -> CardBox:  # fmt: skip
    """One card at the origin: the image covers a window of `image_w` by the height its
    aspect asks for, inside a white border with the label strip under it."""
    image_h = min(max_h, max(min_h, image_w * source.height / max(1, source.width)))
    strip = strip_px if source.label else 0
    return CardBox(
        src=source.src, width=source.width, height=source.height, left=0.0, top=0.0,
        box_width=image_w + 2 * border_px, box_height=image_h + 2 * border_px + strip,
        image_width=image_w, image_height=image_h, border_px=border_px, rotate_deg=0.0,
        label=source.label, strip_px=strip, strip_font_px=strip_font_px,
    )  # fmt: skip


def finale_card_boxes(sources: Sequence[CardSource], *, numbers: StyleNumbers) -> list[CardBox]:
    """The short's first images around the finale circle (the references close the loop
    with the faces they opened on): at most the style's `broll.motion.finale.cards`
    and the three slots."""
    border = numbers.broll.card_border_px
    wanted = min(numbers.broll.finale_cards, len(FINALE_SLOT_TOPS))
    boxes = [
        _box(s, image_w=FINALE_CARD_IMAGE_W, min_h=FINALE_IMAGE_MIN_H, max_h=FINALE_IMAGE_MAX_H,
             strip_px=0, strip_font_px=0, border_px=border)  # fmt: skip
        for s in sources[:wanted]
    ]
    def left_of(slot: int, width: float) -> float:
        """Top centre, then the left and right shoulders of the circle (dyson_10)."""
        if slot == 0:
            return (WIDTH - width) / 2
        return SAFE_LEFT if slot == 1 else WIDTH - SAFE_LEFT - width

    return [
        box.model_copy(update={
            "left": left_of(i, box.box_width), "top": FINALE_SLOT_TOPS[i],
            "rotate_deg": FINALE_ROTATES[i], "delay_s": i * CARD_STAGGER_S,
            "from_y": CARD_FLY_UP_PX if i == 0 else 0.0,
            "from_x": 0.0 if i == 0 else (-CARD_FLY_SIDE_PX if i == 1 else CARD_FLY_SIDE_PX),
        })  # fmt: skip
        for i, box in enumerate(boxes)
    ]


def finale_spec(
    text: str, sources: Sequence[CardSource], *, numbers: StyleNumbers
) -> FinaleCardSpec:
    return FinaleCardSpec(
        text=text,
        text_font_px=FINALE_TEXT_FONT_PX,
        text_top=FINALE_TEXT_TOP,
        text_color=numbers.palette.accent,
        circle_left=(WIDTH - FINALE_DIAMETER) / 2,
        circle_top=FINALE_CENTER_Y - FINALE_DIAMETER / 2,
        circle_diameter=FINALE_DIAMETER,
        ring_px=FINALE_RING_PX,
        ring_color=numbers.palette.accent,
        cards=finale_card_boxes(sources, numbers=numbers),
        fade_s=numbers.broll.finale_fade_s,
    )


def stamp_colors(numbers: StyleNumbers) -> tuple[str, ...]:
    """The style's stamp colour set; an unnamed set falls back to the palette accent."""
    return STAMP_PALETTES.get(numbers.broll.stamp_palette) or (numbers.palette.accent,)


def stamp_spec(text: str, *, numbers: StyleNumbers, max_font_px: int = STAMP_FONT_PX) -> StampSpec:
    """A landed stamp, measured and clamped: inside the style's top
    `broll.stamp_max_y_fraction` of the frame and clear of the platform's right rail.
    `max_font_px` lets the counter (029) hold one size across every frame's text."""
    style = numbers.captions
    available = WIDTH - SAFE_RIGHT_PX - SAFE_LEFT
    room = available - 2 * STAMP_PAD_X - 2 * STAMP_BORDER_PX
    font_px = max_font_px
    while font_px > STAMP_MIN_FONT_PX and _measured(text, font_px=font_px, style=style) > room:
        font_px -= FONT_STEP_PX
    width = min(
        _measured(text, font_px=font_px, style=style) + 2 * STAMP_PAD_X + 2 * STAMP_BORDER_PX,
        available,
    )
    height = font_px * STAMP_LINE_HEIGHT + 2 * STAMP_PAD_Y + 2 * STAMP_BORDER_PX
    left = min(max(SAFE_LEFT, (WIDTH - width) / 2), WIDTH - SAFE_RIGHT_PX - width)
    half = _tilt_extent(width, height, STAMP_ROTATE_DEG)
    limit = numbers.broll.stamp_max_y_fraction * HEIGHT
    centre = max(half, min(STAMP_CENTER_Y, limit - half))
    return StampSpec(
        text=text, left=left, top=centre - height / 2, width=width, height=height,
        rotate_deg=STAMP_ROTATE_DEG, font_px=font_px, border_px=STAMP_BORDER_PX,
        radius_px=STAMP_RADIUS_PX, color=stamp_colors(numbers)[0], fill=STAMP_FILL,
        scale_from=STAMP_SCALE_FROM,
        land_s=numbers.broll.stamp_land_s,
        shake_s=STAMP_SHAKE_S if numbers.broll.stamp_shake else 0.0,
    )  # fmt: skip


# --- stamps never cover a face (056 (4)) --------------------------------------------------
#
# run03 stamped the king's face on seven beats. When a stamp or counter sits over an
# image, the 3.3 face detector runs on that image, the face is mapped into composition
# pixels through the visual's geometry, and the stamp moves to the largest face-free
# band: the image's upper third, its lower third, or below it. No face, or no free band,
# leaves today's placement. The 6.3 top zone is `safe_area`'s, the gate's too; 061's
# text pops stay above its bottom zone.

STAMP_BELOW_GAP_PX = 24.0


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    def overlaps(self, other: Box) -> bool:
        return (
            self.left < other.right and other.left < self.right
            and self.top < other.bottom and other.top < self.bottom
        )  # fmt: skip

    def clearance(self, other: Box) -> float:
        """The vertical gap between the boxes; 0 when they overlap or touch."""
        if self.overlaps(other):
            return 0.0
        return max(0.0, max(other.top - self.bottom, self.top - other.bottom))


def _cover_offsets(
    box_w: float, box_h: float, img_w: int, img_h: int, zoom: float, fx: float, fy: float
) -> tuple[float, float, float]:
    """`object-fit: cover` at `object-position` (fx, fy) then `scale(zoom)` around the
    same point (the `Framed` component): the drawn scale and the image's top-left."""
    scale = max(box_w / img_w, box_h / img_h)
    drawn_w, drawn_h = img_w * scale, img_h * scale
    left, top = (box_w - drawn_w) * fx, (box_h - drawn_h) * fy
    # scale(zoom) with the transform origin at the focus point of the box
    ox, oy = fx * box_w, fy * box_h
    left, top = ox + (left - ox) * zoom, oy + (top - oy) * zoom
    return scale * zoom, left, top


def _scaled_about(box: Box, ox: float, oy: float, scale: float) -> Box:
    return Box(
        left=ox + (box.left - ox) * scale, top=oy + (box.top - oy) * scale,
        width=box.width * scale, height=box.height * scale,
    )  # fmt: skip


def _union(a: Box, b: Box) -> Box:
    left, top = min(a.left, b.left), min(a.top, b.top)
    return Box(left=left, top=top, width=max(a.right, b.right) - left,
               height=max(a.bottom, b.bottom) - top)  # fmt: skip


def image_box_on(visual: VisualSpec) -> Box:
    """Where the visual draws its image: the whole frame for a photo, the card's image
    window (border inside) for a card, both before any push."""
    card = visual.card
    if card is None:
        return Box(0.0, 0.0, float(WIDTH), float(HEIGHT))
    return Box(card.left + card.border_px, card.top + card.border_px,
               card.image_width, card.image_height)  # fmt: skip


def face_box_on(visual: VisualSpec, face: FaceBox) -> Box:
    """The face, detected in the image's own pixels, in composition pixels over the
    whole beat: the box at the beat's first and last frame (the photo's Ken Burns or the
    card's push, both around the focus / the card centre) taken together. The card's
    tilt (a degree or two) is left out."""
    window = image_box_on(visual)
    scale, left, top = _cover_offsets(
        window.width, window.height, visual.width, visual.height, visual.zoom,
        visual.focus_x, visual.focus_y,
    )  # fmt: skip
    at_rest = Box(
        left=window.left + left + face.left * scale, top=window.top + top + face.top * scale,
        width=face.width * scale, height=face.height * scale,
    )  # fmt: skip
    card = visual.card
    if card is None:
        ox, oy = visual.focus_x * WIDTH, visual.focus_y * HEIGHT
        boxes = [_scaled_about(at_rest, ox, oy, s) for s in (visual.scale_from, visual.scale_to)]
        # the drift across the margin, either way
        pan = abs(visual.pan_px) / 2
        boxes = [Box(b.left - pan, b.top, b.width + 2 * pan, b.height) for b in boxes]
    else:
        ox, oy = card.left + card.width / 2, card.top + card.height / 2
        boxes = [_scaled_about(at_rest, ox, oy, s) for s in (visual.scale_from, visual.scale_to)]
    return _union(boxes[0], boxes[1])


def stamp_box(stamp: StampSpec) -> Box:
    """The stamp's box with its tilt, as T12 and the face rule read it."""
    half = _tilt_extent(stamp.width, stamp.height, stamp.rotate_deg)
    centre = stamp.top + stamp.height / 2
    return Box(stamp.left, centre - half, stamp.width, 2 * half)


def _stamp_at(stamp: StampSpec, centre: float, *, numbers: StyleNumbers) -> StampSpec | None:
    """The stamp with its centre at `centre`, clamped into the style's top band and out
    of the 6.3 top zone; None when the band cannot hold it at all."""
    half = _tilt_extent(stamp.width, stamp.height, stamp.rotate_deg)
    limit = numbers.broll.stamp_max_y_fraction * HEIGHT
    lowest, highest = SAFE_TOP_PX + half, limit - half
    if lowest > highest:
        return None
    centre = min(max(centre, lowest), highest)
    return stamp.model_copy(update={"top": centre - stamp.height / 2})


def stamp_clear_of(
    stamp: StampSpec, face: Box, image: Box, *, numbers: StyleNumbers
) -> tuple[StampSpec, str | None]:
    """The stamp moved to the largest face-free band (056 (4)) and the band's name, or
    the stamp as it was and None: unchanged when it does not touch the face, and when
    no band is free of it."""
    if not stamp_box(stamp).overlaps(face):
        return stamp, None
    half = _tilt_extent(stamp.width, stamp.height, stamp.rotate_deg)
    bands = (
        ("upper third", image.top + image.height / 6),
        ("lower third", image.top + image.height * 5 / 6),
        ("below the image", image.bottom + STAMP_BELOW_GAP_PX + half),
    )
    best: tuple[float, str, StampSpec] | None = None
    for name, centre in bands:
        moved = _stamp_at(stamp, centre, numbers=numbers)
        if moved is None:
            continue
        box = stamp_box(moved)
        if box.overlaps(face):
            continue
        clearance = box.clearance(face)
        if best is None or clearance > best[0]:
            best = (clearance, name, moved)
    if best is None:
        return stamp, None
    return best[2], best[1]


# --- text pops (061; 4.1 as amended) ----------------------------------------------------
#
# 1-4 bold words pinned on the picture near the thing they name, landing on the spoken
# word. The style row (`broll.motion.text_pop`) carries the overshoot length, the hold,
# the per-beat cap, the tilt, the type size and the pop yellow; the treatment below
# (weight, outline, shadow, padding) is the engine's look like the stamp's. Placement:
# the planner's `{x, y, anchor}` in percent, clamped into the safe area, then moved to
# the nearest free spot when the box lands on the PIP circle, the caption band or a
# detected face (`place_text_pop`); no free spot means a dropped pop when a face was
# in the way and a build failure otherwise.

EPS = 1e-6
TEXT_POP_WEIGHT = 900
TEXT_POP_MIN_FONT_PX = 40
TEXT_POP_PAD_X, TEXT_POP_PAD_Y = 12.0, 8.0
TEXT_POP_LINE_HEIGHT = 1.2
TEXT_POP_STROKE_PX, TEXT_POP_DROP_PX = 6, 6
TEXT_POP_SCALE_FROM = 0.4
TEXT_POP_WHITE = "#FFFFFF"
TEXT_POP_GAP_PX = 24.0  # clearance kept from the circle, the caption band and a face
TEXT_POP_ANCHOR_SHIFT: Mapping[str, float] = {"left": 0.0, "center": 0.5, "right": 1.0}


def _pop_fill(fill: str, numbers: StyleNumbers) -> str:
    if fill == "white":
        return TEXT_POP_WHITE
    if fill == "accent":
        return numbers.palette.accent
    return numbers.broll.pop_fill


def _pop_size(text: str, *, numbers: StyleNumbers) -> tuple[int, float, float]:
    """The pop's type size (shrunk in steps until the words fit the width between the
    safe margins) and its box."""
    style = numbers.captions
    room = WIDTH - SAFE_RIGHT_PX - SAFE_LEFT - 2 * TEXT_POP_PAD_X
    font_px = numbers.broll.pop_font_px
    while (
        font_px > TEXT_POP_MIN_FONT_PX
        and _measured(text, font_px=font_px, style=style, weight=TEXT_POP_WEIGHT) > room
    ):
        font_px -= FONT_STEP_PX
    width = min(
        _measured(text, font_px=font_px, style=style, weight=TEXT_POP_WEIGHT) + 2 * TEXT_POP_PAD_X,
        room + 2 * TEXT_POP_PAD_X,
    )
    height = font_px * TEXT_POP_LINE_HEIGHT + 2 * TEXT_POP_PAD_Y
    return font_px, width, height


@dataclass(frozen=True)
class Placement:
    """Where a pop ended up: its centre, and the obstacles it was moved off (none when
    it sits where it was asked)."""

    cx: float
    cy: float
    cleared: tuple[str, ...]


def _tilted(cx: float, cy: float, width: float, half: float) -> Box:
    return Box(cx - width / 2, cy - half, width, 2 * half)


def _clamped_centre(
    cx: float, cy: float, *, width: float, half: float, lowest: float, highest: float
) -> tuple[float, float] | None:
    """The centre moved so the tilted box lies inside the safe margins and between
    `lowest` and `highest` (box top and bottom limits); None when it cannot fit."""
    if width > WIDTH - SAFE_RIGHT_PX - SAFE_LEFT + EPS or lowest + 2 * half > highest + EPS:
        return None
    x = min(max(cx, SAFE_LEFT + width / 2), WIDTH - SAFE_RIGHT_PX - width / 2)
    y = min(max(cy, lowest + half), highest - half)
    return x, y


def place_text_pop(
    cx: float,
    cy: float,
    *,
    width: float,
    height: float,
    rotate_deg: float,
    blocked: Mapping[str, Box],
    image: Box | None,
    highest: float,
) -> Placement | None:
    """The asked-for centre clamped into the safe area (the top zone to `highest`, the
    bottom zone's edge; the rails), then, when the tilted box lands on a `blocked`
    obstacle (the PIP circle, the caption band, a face), the nearest free centre among
    the spots beside each obstacle and the image's face-free bands; None when no spot
    is free. The caption band is an obstacle rather than a clamp so a move off it is
    reported like the others."""
    half = _tilt_extent(width, height, rotate_deg)
    gap = TEXT_POP_GAP_PX
    asked = _clamped_centre(cx, cy, width=width, half=half, lowest=SAFE_TOP_PX, highest=highest)
    if asked is None:
        return None

    def hits(centre: tuple[float, float]) -> list[str]:
        box = _tilted(*centre, width=width, half=half)
        return [name for name, obstacle in blocked.items() if box.overlaps(obstacle)]

    cleared = hits(asked)
    if not cleared:
        return Placement(asked[0], asked[1], ())
    candidates: list[tuple[float, float]] = []
    for obstacle in blocked.values():
        candidates += [
            (asked[0], obstacle.top - gap - half),
            (asked[0], obstacle.bottom + gap + half),
            (obstacle.right + gap + width / 2, asked[1]),
            (obstacle.left - gap - width / 2, asked[1]),
        ]
    if image is not None:
        candidates += [
            (asked[0], image.top + image.height / 6),
            (asked[0], image.top + image.height * 5 / 6),
            (asked[0], image.bottom + gap + half),
        ]
    free: list[tuple[float, float, float]] = []
    for x, y in candidates:
        centre = _clamped_centre(x, y, width=width, half=half, lowest=SAFE_TOP_PX, highest=highest)
        if centre is None or hits(centre):
            continue
        free.append((math.hypot(centre[0] - asked[0], centre[1] - asked[1]), *centre))
    if not free:
        return None
    _, x, y = min(free)
    return Placement(x, y, tuple(cleared))


def presenter_face_box(face: FaceBox) -> Box:
    """The presenter's own face on a `full` beat, in composition pixels: the measured
    box (already in cut pixels, 013) through the punch-in (research S2) at rest and at
    its widest, taken together."""
    at_rest = Box(float(face.left), float(face.top), float(face.width), float(face.height))
    ox, oy = WIDTH / 2, PUNCH_IN.origin_y * HEIGHT
    return _union(at_rest, _scaled_about(at_rest, ox, oy, PUNCH_IN.scale_from))


def text_pop_spec(
    pop: TextPop,
    index: int,
    *,
    beat_start_s: float,
    beat_end_s: float,
    numbers: StyleNumbers,
    blocked: Mapping[str, Box],
    image: Box | None,
) -> tuple[TextPopSpec | None, Placement | None]:
    """One pop of a beat, measured, placed (`place_text_pop`) and timed: it lands at
    its word's output time (`at_s`, the grammar's; the beat's start when never
    written) and leaves at the beat's end or `hold_max_s` later, whichever is first;
    pops of one beat tilt alternately. None when no spot is free."""
    b = numbers.broll
    font_px, width, height = _pop_size(pop.text, numbers=numbers)
    tilt = -b.pop_tilt_deg if index % 2 == 0 else b.pop_tilt_deg
    cx = pop.x / 100 * WIDTH + (0.5 - TEXT_POP_ANCHOR_SHIFT[pop.anchor]) * width
    cy = pop.y / 100 * HEIGHT
    placed = place_text_pop(
        cx, cy, width=width, height=height, rotate_deg=tilt, blocked=blocked, image=image,
        highest=HEIGHT - SAFE_BOTTOM_PX,
    )  # fmt: skip
    if placed is None:
        return None, None
    length = beat_end_s - beat_start_s
    at = 0.0 if pop.at_s is None else min(max(pop.at_s - beat_start_s, 0.0), max(length - EPS, 0.0))
    return TextPopSpec(
        text=pop.text, left=placed.cx - width / 2, top=placed.cy - height / 2, width=width,
        height=height, rotate_deg=tilt, font_px=font_px, font_weight=TEXT_POP_WEIGHT,
        color=_pop_fill(pop.fill, numbers), stroke_px=TEXT_POP_STROKE_PX,
        drop_px=TEXT_POP_DROP_PX, scale_from=TEXT_POP_SCALE_FROM, at_s=round(at, 3),
        pop_s=b.pop_s, until_s=round(min(length, at + b.pop_hold_max_s), 3),
    ), placed  # fmt: skip


# --- stickers (062; 4.1 as amended) -----------------------------------------------------
#
# A Fluent Emoji 3D PNG (fetched by the asset step into the job folder) popping in with an
# overshoot on its word, then floating gently under a soft shadow. The style row
# (`broll.motion.sticker`) carries the overshoot length, the hold, the per-beat cap, the
# square's size and the float; the ticket bounds the size to 180-320 px. Placement: with
# no `{x, y}` it sits centred above the PIP circle ("over his head"), `STICKER_GAP_PX`
# clear of it; otherwise centred on the planner's point; either way clamped into the safe
# area and moved off the circle, the caption band, the stamp, a face and the beat's text
# pops and bubbles by 061's `place_text_pop` search.

STICKER_SIZE_MIN_PX, STICKER_SIZE_MAX_PX = 180, 320
STICKER_GAP_PX = 20.0
STICKER_SCALE_FROM = 0.3
STICKER_SHADOW_PX = 18.0


def sticker_spec(
    sticker: Sticker,
    *,
    src: str,
    beat_id: str,
    beat_start_s: float,
    beat_end_s: float,
    numbers: StyleNumbers,
    blocked: Mapping[str, Box],
    image: Box | None,
    circle: Box | None,
) -> tuple[StickerSpec | None, Placement | None]:
    """One sticker, placed and timed: above `circle` (the PIP circle) when it has no
    `{x, y}`, else centred on its point; the square and its float kept off the
    obstacles (`place_text_pop`); it lands at `at_s` (the grammar's; the beat's start
    when never written) and leaves at the beat's end or `hold_max_s` later. None when
    no spot is free."""
    b = numbers.broll
    size, lift = float(b.sticker_size_px), b.sticker_float_px
    if sticker.x is not None and sticker.y is not None:
        cx, cy = sticker.x / 100 * WIDTH, sticker.y / 100 * HEIGHT
    elif circle is not None:
        cx, cy = circle.left + circle.width / 2, circle.top - STICKER_GAP_PX - size / 2
    else:
        raise RenderError(
            f"{beat_id}: sticker {sticker.name!r} has no {{x, y}} and no PIP circle to sit "
            "above (062)"
        )
    placed = place_text_pop(
        cx, cy, width=size, height=size + 2 * lift, rotate_deg=0.0, blocked=blocked,
        image=image, highest=HEIGHT - SAFE_BOTTOM_PX,
    )  # fmt: skip
    if placed is None:
        return None, None
    length = beat_end_s - beat_start_s
    at = 0.0
    if sticker.at_s is not None:
        at = min(max(sticker.at_s - beat_start_s, 0.0), max(length - EPS, 0.0))
    return StickerSpec(
        name=sticker.name, src=src, left=placed.cx - size / 2, top=placed.cy - size / 2,
        size=size, scale_from=STICKER_SCALE_FROM, at_s=round(at, 3), pop_s=b.sticker_s,
        until_s=round(min(length, at + b.sticker_hold_max_s), 3), float_px=lift,
        float_period_s=b.sticker_float_period_s, shadow_px=STICKER_SHADOW_PX,
    ), placed  # fmt: skip


# --- bubbles (063; 4.1 as amended) ------------------------------------------------------
#
# Speech and thought bubbles of the recording's own words. The style row
# (`broll.motion.bubble`) carries the overshoot length, the hold, the per-beat and word
# caps, the type size and its floor, the body width, the white fill and the dark ink; the
# treatment below (weight, padding, corner radius, outline, tail and dot sizes) is the
# engine's look like the stamp's. Placement: the body sits over the planner's anchor
# `{x, y}` (the tail's tip) at `BUBBLE_TAIL_LEN_PX`, clamped into the safe area, then moved
# to the nearest free spot (`place_text_pop`, 061's search) when it lands on the PIP
# circle, the caption band, the stamp, a detected face, the beat's earlier bubble or the
# anchor's own keep-out; the tail then leaves whichever side of the body faces the tip.

BUBBLE_WEIGHT = 800
BUBBLE_PAD_X, BUBBLE_PAD_Y = 28.0, 18.0
BUBBLE_LINE_HEIGHT = 1.2
BUBBLE_LINES_MAX = 4
BUBBLE_RADIUS_PX = 28.0
BUBBLE_STROKE_PX = 5
BUBBLE_SCALE_FROM = 0.5
BUBBLE_TAIL_LEN_PX = 90.0  # the body's edge sits this far from the tip when unobstructed
BUBBLE_TAIL_BASE_PX = 56.0
BUBBLE_ANCHOR_KEEPOUT_PX = 40.0  # half-size of the box around the anchor the body avoids
BUBBLE_DOT_RADII_PX = (14.0, 10.0, 6.0)  # the thought trail, body to anchor
BUBBLE_DOT_FRACTIONS = (0.3, 0.55, 0.8)

TailSide = Literal["top", "bottom", "left", "right"]


@dataclass(frozen=True)
class Tail:
    """A speech bubble's tail: the side of the body it leaves, its two base points on
    that edge (`a` before `b` along the edge's clockwise trace) and the tip."""

    side: TailSide
    a: tuple[float, float]
    b: tuple[float, float]
    tip: tuple[float, float]

    @property
    def base(self) -> tuple[float, float]:
        return (self.a[0] + self.b[0]) / 2, (self.a[1] + self.b[1]) / 2


def _wrapped(
    words: Sequence[str], *, font_px: int, room: float, style: CaptionStyle
) -> list[str] | None:
    """Greedy lines of `words` no wider than `room` at `font_px`; None when one word
    alone is wider than the room."""
    lines: list[list[str]] = [[]]
    for word in words:
        if _measured(word, font_px=font_px, style=style, weight=BUBBLE_WEIGHT) > room:
            return None
        candidate = [*lines[-1], word]
        if lines[-1] and _measured(" ".join(candidate), font_px=font_px, style=style,
                                   weight=BUBBLE_WEIGHT) > room:  # fmt: skip
            lines.append([word])
        else:
            lines[-1] = candidate
    return [" ".join(line) for line in lines]


def bubble_lines(text: str, *, numbers: StyleNumbers) -> tuple[int, list[str], float, float] | None:
    """The bubble's type size, its wrapped lines and its body box: the words wrapped
    inside `width_px` at `size_px`, the type shrinking in steps to `min_size_px` until
    they fit on at most `BUBBLE_LINES_MAX` lines; None when they never do."""
    b, style = numbers.broll, numbers.captions
    words = text.split()
    room = b.bubble_width_px - 2 * BUBBLE_PAD_X
    font_px = b.bubble_font_px
    while font_px >= b.bubble_min_font_px:
        lines = _wrapped(words, font_px=font_px, room=room, style=style)
        if lines is not None and len(lines) <= BUBBLE_LINES_MAX:
            widest = max(_measured(line, font_px=font_px, style=style, weight=BUBBLE_WEIGHT)
                         for line in lines)  # fmt: skip
            width = widest + 2 * BUBBLE_PAD_X
            height = len(lines) * font_px * BUBBLE_LINE_HEIGHT + 2 * BUBBLE_PAD_Y
            return font_px, lines, width, height
        font_px -= FONT_STEP_PX
    return None


def bubble_tail(body: Box, tip: tuple[float, float]) -> Tail | None:
    """The tail from `body` to `tip`: it leaves the side facing the tip, its base
    `BUBBLE_TAIL_BASE_PX` wide (narrower on a small body) and kept clear of the rounded
    corners; None when the tip is inside the body (nothing to point at)."""
    tx, ty = tip
    if ty >= body.bottom or ty <= body.top:
        side: TailSide = "bottom" if ty >= body.bottom else "top"
        base = max(0.0, min(BUBBLE_TAIL_BASE_PX, body.width - 2 * BUBBLE_RADIUS_PX))
        lo, hi = body.left + BUBBLE_RADIUS_PX + base / 2, body.right - BUBBLE_RADIUS_PX - base / 2
        cx = min(max(tx, lo), hi)
        y = body.bottom if side == "bottom" else body.top
        return Tail(side, (cx - base / 2, y), (cx + base / 2, y), tip)
    if tx >= body.right or tx <= body.left:
        side = "right" if tx >= body.right else "left"
        base = max(0.0, min(BUBBLE_TAIL_BASE_PX, body.height - 2 * BUBBLE_RADIUS_PX))
        lo, hi = body.top + BUBBLE_RADIUS_PX + base / 2, body.bottom - BUBBLE_RADIUS_PX - base / 2
        cy = min(max(ty, lo), hi)
        x = body.right if side == "right" else body.left
        return Tail(side, (x, cy - base / 2), (x, cy + base / 2), tip)
    return None


def _pt(x: float, y: float) -> str:
    return f"{x:g} {y:g}"


def bubble_path(body: Box, radius: float, tail: Tail | None) -> str:
    """The outline as one SVG path in composition pixels: the rounded body traced
    clockwise from the top-left corner, with the tail's two edges to the tip spliced
    into the side it leaves, so fill and outline are one shape with no seam."""
    r = min(radius, body.width / 2, body.height / 2)
    left, top, right, bottom = body.left, body.top, body.right, body.bottom
    arc = f"A {r:g} {r:g} 0 0 1"

    def edge(side: TailSide, end: str) -> str:
        if tail is None or tail.side != side:
            return end
        (ax, ay), (bx, by), (tx, ty) = tail.a, tail.b, tail.tip
        # the trace runs left-to-right on top, top-to-bottom on the right, right-to-left
        # along the bottom and bottom-to-top up the left, so the base points are met in
        # that order
        first, second = ((ax, ay), (bx, by)) if side in ("top", "right") else ((bx, by), (ax, ay))
        return f"L {_pt(*first)} L {_pt(tx, ty)} L {_pt(*second)} {end}"

    return " ".join([
        f"M {_pt(left + r, top)}",
        edge("top", f"H {right - r:g}"),
        f"{arc} {_pt(right, top + r)}",
        edge("right", f"V {bottom - r:g}"),
        f"{arc} {_pt(right - r, bottom)}",
        edge("bottom", f"H {left + r:g}"),
        f"{arc} {_pt(left, bottom - r)}",
        edge("left", f"V {top + r:g}"),
        f"{arc} {_pt(left + r, top)}",
        "Z",
    ])  # fmt: skip


def bubble_dots(body: Box, tip: tuple[float, float]) -> list[BubbleDot]:
    """A thought bubble's trail: `BUBBLE_DOT_RADII_PX` dots along the line from the
    body's edge (where a tail's base would sit) to the tip, largest first."""
    tail = bubble_tail(body, tip)
    if tail is None:
        return []
    (sx, sy), (tx, ty) = tail.base, tip
    return [
        BubbleDot(cx=round(sx + (tx - sx) * f, 2), cy=round(sy + (ty - sy) * f, 2), r=r)
        for f, r in zip(BUBBLE_DOT_FRACTIONS, BUBBLE_DOT_RADII_PX, strict=True)
    ]


def bubble_spec(
    bubble: Bubble,
    *,
    beat_id: str,
    beat_start_s: float,
    beat_end_s: float,
    numbers: StyleNumbers,
    blocked: Mapping[str, Box],
    image: Box | None,
) -> tuple[BubbleSpec | None, Placement | None]:
    """One bubble of a beat, wrapped (`bubble_lines`; text that never fits fails the
    build naming the beat), placed over its anchor at `BUBBLE_TAIL_LEN_PX` and moved
    off the obstacles and the anchor's own keep-out (`place_text_pop`), then given its
    tail (a speech bubble) or trail of dots (a thought bubble) to the anchor, and timed:
    it lands at `at_s` (the grammar's; the beat's start when never written) and leaves
    at the beat's end or `hold_max_s` later. None when no spot is free."""
    b = numbers.broll
    fitted = bubble_lines(bubble.text, numbers=numbers)
    if fitted is None:
        raise RenderError(
            f"{beat_id}: bubble {bubble.text!r} does not fit {b.bubble_width_px} px on "
            f"{BUBBLE_LINES_MAX} lines even at broll.motion.bubble.min_size_px "
            f"{b.bubble_min_font_px} (063)"
        )
    font_px, lines, width, height = fitted
    ax = min(max(bubble.x / 100 * WIDTH, 0.0), float(WIDTH))
    ay = min(max(bubble.y / 100 * HEIGHT, 0.0), float(HEIGHT))
    keep = BUBBLE_ANCHOR_KEEPOUT_PX
    obstacles = {**blocked, "its anchor": Box(ax - keep, ay - keep, 2 * keep, 2 * keep)}
    placed = place_text_pop(
        ax, ay - BUBBLE_TAIL_LEN_PX - height / 2, width=width, height=height, rotate_deg=0.0,
        blocked=obstacles, image=image, highest=HEIGHT - SAFE_BOTTOM_PX,
    )  # fmt: skip
    if placed is None:
        return None, None
    body = Box(placed.cx - width / 2, placed.cy - height / 2, width, height)
    radius = min(BUBBLE_RADIUS_PX, height / 2)
    tail = bubble_tail(body, (ax, ay)) if bubble.shape == "speech" else None
    length = beat_end_s - beat_start_s
    at = 0.0
    if bubble.at_s is not None:
        at = min(max(bubble.at_s - beat_start_s, 0.0), max(length - EPS, 0.0))
    return BubbleSpec(
        shape=bubble.shape, text=bubble.text, lines=lines, left=body.left, top=body.top,
        width=width, height=height, radius_px=radius, tip_x=ax, tip_y=ay,
        path=bubble_path(body, radius, tail),
        dots=bubble_dots(body, (ax, ay)) if bubble.shape == "thought" else [],
        font_px=font_px, font_weight=BUBBLE_WEIGHT, fill=b.bubble_fill, ink=b.bubble_ink,
        stroke_px=BUBBLE_STROKE_PX, scale_from=BUBBLE_SCALE_FROM, at_s=round(at, 3),
        pop_s=b.bubble_s, until_s=round(min(length, at + b.bubble_hold_max_s), 3),
    ), placed  # fmt: skip


def counter_spec(
    counter: CounterPlan, *, frames: int, fps: int, numbers: StyleNumbers
) -> CounterSpec:
    """The `counter` overlay (029): the digits for every frame of the beat, counting to
    the target and holding it through the last `broll.motion.stamp.duration_s`, where it
    lands with the stamp's shake. The box is the stamp's, measured on the widest text it
    shows so no frame spills out, and clamped into the same top band clear of the rail."""
    b = numbers.broll
    land_frames = min(frames, round(b.stamp_land_s * fps))
    texts = infographics.counter_texts(
        counter.start, counter.target, frames=frames, land_frames=land_frames,
        decimals=counter.decimals, grouping=b.counter_grouping, unit=counter.unit,
    )  # fmt: skip
    shown = set(texts)
    font_px = min(stamp_spec(t, numbers=numbers).font_px for t in shown)
    widest = max(shown, key=lambda t: _measured(t, font_px=font_px, style=numbers.captions))
    box = stamp_spec(widest, numbers=numbers, max_font_px=font_px)
    return CounterSpec(
        **box.model_dump(exclude={"text", "scale_from"}),
        text=texts[-1], scale_from=COUNTER_POP_FROM, texts=texts,
        land_frame=frames - land_frames,
    )  # fmt: skip


def split_label(text: str) -> tuple[str, str]:
    """`"India Gate · Delhi"` -> name and role; no separator means no role."""
    for separator in LOWER_THIRD_SEPARATORS:
        if separator in text:
            name, _, role = text.partition(separator)
            return name.strip(), role.strip()
    return text.strip(), ""


def lower_third_spec(text: str, *, numbers: StyleNumbers) -> LowerThirdSpec:
    """The name-and-role label in the style's `lower_third` band (6.3)."""
    b, style = numbers.broll, numbers.captions
    name, role = split_label(text)
    widest = max(
        _measured(name, font_px=LOWER_THIRD_NAME_PX, style=style, weight=LOWER_THIRD_NAME_WEIGHT),
        _measured(role, font_px=LOWER_THIRD_ROLE_PX, style=style, weight=LOWER_THIRD_ROLE_WEIGHT),
    )
    width = min(
        LOWER_THIRD_BAR_PX + 2 * LOWER_THIRD_PAD_X + widest, WIDTH - SAFE_RIGHT_PX - SAFE_LEFT
    )
    return LowerThirdSpec(
        name=name, role=role, left=SAFE_LEFT, top=float(b.lower_third_top_y), width=width,
        height=float(b.lower_third_bottom_y - b.lower_third_top_y), bar_px=LOWER_THIRD_BAR_PX,
        accent=numbers.palette.accent, fill=LOWER_THIRD_FILL,
        name_font_px=LOWER_THIRD_NAME_PX, role_font_px=LOWER_THIRD_ROLE_PX,
        fade_s=b.lower_third_fade_s,
    )  # fmt: skip


def opening_asset_ids(plan: PicturePlan, manifest: AssetManifest, count: int) -> list[str]:
    """The first `count` distinct still assets the short shows, in beat order (055): the
    opening's images first, then whatever follows. A beat's asset is the one the step
    decided for it, else its planned id through the aliases. A clip (058) is passed
    over: the finale's cards are stills."""
    out: list[str] = []
    for beat in plan.beats:
        decided = manifest.beat(beat.id)
        asset_id = (
            decided.asset_id
            if decided is not None
            else (manifest.aliases.get(beat.asset_id, beat.asset_id) if beat.asset_id else None)
        )
        record = manifest.asset(asset_id) if asset_id is not None else None
        if asset_id is None or asset_id in out or record is None or record.kind == "clip":
            continue
        out.append(asset_id)
        if len(out) == count:
            break
    return out


def card_sources(
    plan: PicturePlan, manifest: AssetManifest | None, job_dir: Path | None, *, count: int
) -> list[CardSource]:
    """The finale's cards (055): the short's first `count` distinct assets, labelled
    with the lower-third the beat that sourced them carries."""
    if manifest is None or job_dir is None:
        return []
    labels: dict[str, str] = {}
    for beat in plan.beats:
        decided = manifest.beat(beat.id)
        if decided is None or decided.asset_id is None:
            continue
        if beat.event.kind == "lower_third" and beat.event.text:
            labels.setdefault(decided.asset_id, beat.event.text)
    out: list[CardSource] = []
    for asset_id in opening_asset_ids(plan, manifest, count):
        record = manifest.asset(asset_id)
        assert record is not None  # opening_asset_ids keeps only assets with a record
        out.append(
            CardSource(
                src=str((job_dir / record.file).resolve()),
                width=record.width,
                height=record.height,
                label=labels.get(asset_id, ""),
            )
        )
    return out


# --- list, split and wall (ticket 027; decisions 4.1, 5.2, 5.3, 9.2) --------------------
#
# The three tier-1 set pieces. Their counts, entry times and base-still motion come from
# `broll.motion.list` / `.split` / `.wall`; the geometry below is read off nkb_04 (list:
# a header over rows with icons on a dimmed base), nkb_08 / decision 5.2 (split: the
# news-card composite, two panes in one framed card with a badge and a highlighted title
# strip) and nkb_09 (wall: cards flying in from alternating sides on a dimmed base).

LIST_HEADER_TOP, LIST_HEADER_FONT_PX, LIST_HEADER_MIN_FONT_PX = 250.0, 64, 40
LIST_BAND_TOP = 380.0
LIST_ROW_H, LIST_ROW_GAP = 116.0, 22.0
LIST_ROW_FONT_PX, LIST_ROW_MIN_FONT_PX = 46, 26
LIST_ROW_PAD_X = 28.0
LIST_ICON_PAD = 16.0
LIST_ROW_FILL, LIST_ROW_RADIUS_PX = "rgba(17,17,17,0.74)", 18
LIST_FLY_SIDE_PX, LIST_STAGGER_S = 760.0, 0.18

SPLIT_CARD_W = 940.0  # inside the archival card's 980 px limit (5.3), badge room to spare
SPLIT_PANE_ASPECT = 1.15  # head plus collar: a touch taller than square
SPLIT_SEAM_PX = 6
SPLIT_LABEL_PX, SPLIT_LABEL_FONT_PX = 56, 30
SPLIT_TITLE_PX, SPLIT_TITLE_FONT_PX, SPLIT_TITLE_MIN_FONT_PX = 88, 44, 26
SPLIT_TITLE_GAP_PX = 14.0
SPLIT_HIGHLIGHT_PAD_PX, SPLIT_HIGHLIGHT_RADIUS_PX = 10, 10
SPLIT_BADGE_DIAMETER, SPLIT_BADGE_RING_PX = 160.0, 8
SPLIT_BADGE_DROP = 0.4  # how far the badge hangs above the card's top edge

WALL_BAND_TOP, WALL_GAP_PX = 330.0, 24.0
WALL_MAX_COLUMNS, WALL_SMALL_COLUMNS = 3, 2  # 2x2 up to four cells, 3 across above it
WALL_FLY_SIDE_PX, WALL_STAGGER_S = 900.0, 0.1
WALL_ROTATES = (-2.0, 2.5, -1.5, 3.0, -2.5, 1.5, -3.0, 2.0, -1.0)


@dataclass(frozen=True)
class ItemSource:
    """One resolved item of a set piece (027): its text and the asset it shows, or none
    where the plan gave it none (a text-only list row) or the asset step rescued the
    beat that sourced it."""

    text: str
    card: CardSource | None = None


def _fitted(text: str, *, font_px: int, min_font_px: int, style: CaptionStyle,
            room: float) -> int:  # fmt: skip
    """The largest size from `font_px` down in `FONT_STEP_PX` steps whose measured line
    fits `room`, never under `min_font_px` (the stamp's rule, 026)."""
    while font_px > min_font_px and _measured(text, font_px=font_px, style=style) > room:
        font_px -= FONT_STEP_PX
    return font_px


def list_spec(header: str, items: Sequence[ItemSource], *, numbers: StyleNumbers) -> ListSpec:
    """The `list` set piece (nkb_04): the header over one pill per item, each springing
    in from the side, the whole stack inside the safe box and above the style's
    `broll.card_max_bottom_y`. More items than `broll.motion.list.items_max` are cut."""
    b, style = numbers.broll, numbers.captions
    rows_wanted = list(items[: b.list_items_max])
    width = WIDTH - 2 * SAFE_LEFT
    band = b.card_max_bottom_y - LIST_BAND_TOP
    pitch = min(LIST_ROW_H + LIST_ROW_GAP, band / max(1, len(rows_wanted)))
    height = pitch - LIST_ROW_GAP
    rows: list[ListRow] = []
    for i, item in enumerate(rows_wanted):
        icon = height - 2 * LIST_ICON_PAD if item.card is not None else 0.0
        text_left = LIST_ROW_PAD_X + (icon + LIST_ICON_PAD if icon else 0.0)
        font_px = _fitted(item.text, font_px=LIST_ROW_FONT_PX,
                          min_font_px=LIST_ROW_MIN_FONT_PX, style=style,
                          room=width - text_left - LIST_ROW_PAD_X)  # fmt: skip
        rows.append(
            ListRow(
                text=item.text, font_px=font_px, left=SAFE_LEFT,
                top=LIST_BAND_TOP + i * pitch, width=width, height=height,
                text_left=text_left,
                icon_src=item.card.src if item.card is not None else "",
                icon_width=item.card.width if item.card is not None else 0,
                icon_height=item.card.height if item.card is not None else 0,
                icon_left=LIST_ROW_PAD_X if icon else 0.0, icon_size=icon,
                from_x=-LIST_FLY_SIDE_PX if i % 2 == 0 else LIST_FLY_SIDE_PX,
                delay_s=i * LIST_STAGGER_S,
            )  # fmt: skip
        )
    header_px = _fitted(header, font_px=LIST_HEADER_FONT_PX,
                        min_font_px=LIST_HEADER_MIN_FONT_PX, style=style, room=width)  # fmt: skip
    return ListSpec(
        header=header, header_font_px=header_px, header_left=SAFE_LEFT,
        header_top=LIST_HEADER_TOP, header_color=numbers.palette.accent, rows=rows,
        row_fill=LIST_ROW_FILL, row_radius_px=LIST_ROW_RADIUS_PX, spring_s=b.list_reveal_s,
    )  # fmt: skip


def title_words(title: str, highlights: Sequence[str], *, font_px: int,
                style: CaptionStyle) -> list[TitleWord]:  # fmt: skip
    """The title strip's words measured and laid out in one centred line, the words the
    panes are labelled with boxed in the accent (5.2)."""
    wanted = {w.lower() for label in highlights for w in label.split()}
    words = title.split()
    gap = style.word_gap_px
    widths = [_measured(w, font_px=font_px, style=style) for w in words]
    total = sum(widths) + gap * max(0, len(words) - 1)
    x = (WIDTH - total) / 2
    out: list[TitleWord] = []
    for word, width in zip(words, widths, strict=True):
        out.append(TitleWord(text=word, left=x, width=width, highlight=word.lower() in wanted))
        x += width + gap
    return out


def split_bottom(piece: SplitSpec) -> float:
    """The lowest y the split composite reaches (tilt included), like `card_bottom`."""
    return piece.top + piece.height / 2 + _tilt_extent(piece.width, piece.height, piece.rotate_deg)


# 105: where the title strip may sit, in the order tried: a stacked card's strip between
# its pictures (059), under them, above them; a side-by-side card's under the panes (5.2),
# above them. A strip that would cross a face moves; if none fits it shrinks, down to the
# band the least title font needs; still none, it is left off - never across a face.
SPLIT_STRIPS: Mapping[str, tuple[str, ...]] = {
    "stacked": ("seam", "bottom", "top"),
    "side": ("bottom", "top"),
}
SPLIT_TITLE_LINE = 1.4  # the title's line height in `split.tsx`, a multiple of its font
SPLIT_TITLE_STEP_PX = 8


def _title_bands() -> list[int]:
    """The title band heights tried, the full band first, down to the least that still
    holds `SPLIT_TITLE_MIN_FONT_PX` with its highlight padding."""
    least = math.ceil(SPLIT_TITLE_MIN_FONT_PX * SPLIT_TITLE_LINE + 2 * SPLIT_HIGHLIGHT_PAD_PX)
    return [*range(SPLIT_TITLE_PX, least, -SPLIT_TITLE_STEP_PX), least]


def pane_focus(
    face: FaceBox, img_w: int, img_h: int, box_w: float, box_h: float, *, face_y: float
) -> tuple[float, float]:
    """105: the `objectPosition` (fractions) that puts the face's centre across the
    middle of a `box_w` x `box_h` pane picture drawn with `object-fit: cover`, at `face_y`
    of its height - moved in just enough to keep the whole face inside where it fits.
    An axis the picture already fills exactly keeps its centre."""
    scale = max(box_w / img_w, box_h / img_h)
    drawn_w, drawn_h = img_w * scale, img_h * scale
    fw, fh = face.width * scale, face.height * scale

    def axis(free: float, want: float, centre: float, size: float, span: float) -> float:
        if free > -EPS:
            return 0.5
        if size <= span:
            want = min(max(want, size / 2), span - size / 2)
        return min(1.0, max(0.0, (want - centre) / free))

    fx = axis(box_w - drawn_w, box_w / 2, (face.left + face.width / 2) * scale, fw, box_w)
    fy = axis(box_h - drawn_h, face_y * box_h, (face.top + face.height / 2) * scale, fh, box_h)
    return fx, fy


def _face_in_pane(
    face: FaceBox, pane: SplitPane, image_h: float
) -> tuple[float, float, float, float]:
    """The face in card pixels (left, top, right, bottom) as the pane draws its picture
    at its focus - not clipped to the pane, so a face the pane cuts reaches past it."""
    scale = max(pane.pane_width / pane.width, image_h / pane.height)
    left = pane.left + (pane.pane_width - pane.width * scale) * pane.focus_x
    top = pane.top + (image_h - pane.height * scale) * pane.focus_y
    right, bottom = face.left + face.width, face.top + face.height
    return (left + face.left * scale, top + face.top * scale,
            left + right * scale, top + bottom * scale)  # fmt: skip


def _crosses(
    strip: tuple[float, float], faces: Sequence[tuple[float, float, float, float]]
) -> bool:
    """105: the title band (top, bottom in card pixels) shares rows with a face."""
    top, bottom = strip
    return any(top < f[3] - EPS and f[1] < bottom - EPS for f in faces)


def _stacked(wanted: Sequence[ItemSource], panes: list[SplitPane], *, border: int,
             numbers: StyleNumbers, strip: str = "seam",
             title_px: int = SPLIT_TITLE_PX) -> tuple[float, float, float]:  # fmt: skip
    """059: the stacked split's panes appended to `panes` - the first picture on top, the
    second under it, each the card's full inner width, the title band between them
    (`seam`), under both (`bottom`) or over both (`top`; 105) - and the card's top,
    height and title band top. The card fills the band from the badge's overhang under
    the 6.3 top zone down to the style's `broll.card_max_bottom_y` (tilt included): the
    lower picture runs under the PIP circle, as a full-screen still does, so each picture
    is wider than tall rather than a letterbox strip above the circle."""
    b = numbers.broll
    ceiling = SAFE_TOP_PX + SPLIT_BADGE_DIAMETER * SPLIT_BADGE_DROP
    floor = float(b.card_max_bottom_y)
    theta = math.radians(b.card_rotate_deg)
    height = ((floor - ceiling) - SPLIT_CARD_W * abs(math.sin(theta))) / math.cos(theta)
    top = (ceiling + floor) / 2 - height / 2
    seam = 0 if strip == "seam" else SPLIT_SEAM_PX
    pane_h = (height - 2 * border - title_px - seam) / 2
    inner = SPLIT_CARD_W - 2 * border
    if strip == "seam":
        title_top = border + pane_h
        tops = (float(border), title_top + title_px)
    elif strip == "bottom":
        tops = (float(border), border + pane_h + seam)
        title_top = tops[1] + pane_h
    else:
        title_top = float(border)
        tops = (border + title_px, border + title_px + pane_h + seam)
    for i, p in enumerate(wanted):
        assert p.card is not None
        panes.append(
            SplitPane(
                src=p.card.src, width=p.card.width, height=p.card.height, left=float(border),
                top=tops[min(i, 1)], pane_width=inner, pane_height=pane_h, label=p.text,
                from_x=0.0 if i == 0 else SPLIT_CARD_W,
            )  # fmt: skip
        )
    return top, height, title_top


def _side(wanted: Sequence[ItemSource], panes: list[SplitPane], *, border: int,
          label_px: int, numbers: StyleNumbers, pip_top: int | None, strip: str = "bottom",
          title_px: int = SPLIT_TITLE_PX) -> tuple[float, float, float]:  # fmt: skip
    """5.2: the panes side by side, head plus collar, the title band under them (or, 105,
    over them), the card ending `PIP_GAP_PX` above the circle top (051)."""
    b = numbers.broll
    inner = SPLIT_CARD_W - 2 * border
    pane_w = (inner - SPLIT_SEAM_PX * (len(wanted) - 1)) / max(1, len(wanted))
    pane_h = pane_w * SPLIT_PANE_ASPECT
    height = pane_h + label_px + 2 * border + title_px
    half = _tilt_extent(SPLIT_CARD_W, height, b.card_rotate_deg)
    top = _card_limit(b, pip_top) - half - height / 2
    title_top, pane_top = (height - title_px, float(border)) if strip == "bottom" else (
        0.0, float(title_px + border))  # fmt: skip
    for i, p in enumerate(wanted):
        assert p.card is not None
        panes.append(
            SplitPane(
                src=p.card.src, width=p.card.width, height=p.card.height,
                left=border + i * (pane_w + SPLIT_SEAM_PX), top=pane_top,
                pane_width=pane_w, pane_height=pane_h + label_px, label=p.text,
                from_x=0.0 if i == 0 else SPLIT_CARD_W,
            )  # fmt: skip
        )
    return top, height, title_top


FaceOf = Callable[[str], FaceBox | None]


def split_spec(title: str, items: Sequence[ItemSource], badge: CardSource | None, *,
               numbers: StyleNumbers, pip_top: int | None = None,
               face_of: FaceOf | None = None) -> SplitSpec:  # fmt: skip
    """The `split` news-card composite (5.2): the style's `broll.motion.split.panes`
    panes side by side in one framed card `PIP_GAP_PX` above the circle top it is given
    (051), the badge overlapping its top-left corner inside the safe box, and the title
    strip under them. 105: `face_of` is the 3.3 detector on a pane's file; each pane
    with a face is framed so it sits at the style's `split.face_y` (`pane_focus`), one
    with none at `split.faceless_y` (the top, where a missed head most likely is), and
    the strip takes the first place in `SPLIT_STRIPS` that crosses no face, shrinking
    band by band when none does, left off when even the least band crosses one."""
    b, style = numbers.broll, numbers.captions
    # A pane the asset step rescued has no picture; it is left out, never drawn blank.
    panes_wanted = [p for p in items[: b.split_panes] if p.card is not None]
    border = b.card_border_px
    labelled = any(p.text for p in panes_wanted)
    label_px = SPLIT_LABEL_PX if labelled else 0
    left = (WIDTH - SPLIT_CARD_W) / 2
    faces = [face_of(p.card.src) if face_of and p.card else None for p in panes_wanted]

    def laid(strip: str, title_px: int) -> tuple[float, float, float, list[SplitPane]]:
        panes: list[SplitPane] = []
        if b.split_layout == "stacked":
            # the label strip sits inside each pane's height, as on the side-by-side card
            top, height, title_top = _stacked(
                panes_wanted, panes, border=border, numbers=numbers, strip=strip,
                title_px=title_px,
            )  # fmt: skip
        else:
            top, height, title_top = _side(panes_wanted, panes, border=border,
                                           label_px=label_px, numbers=numbers, pip_top=pip_top,
                                           strip=strip, title_px=title_px)  # fmt: skip
        framed: list[SplitPane] = []
        for pane, face in zip(panes, faces, strict=True):
            if face is None:
                # no detector: the centre; a detector that found no face: the top
                faceless = {"focus_y": b.split_faceless_y} if face_of is not None else {}
                framed.append(pane.model_copy(update=faceless))
                continue
            image_h = pane.pane_height - label_px
            fx, fy = pane_focus(face, pane.width, pane.height, pane.pane_width, image_h,
                                face_y=b.split_face_y)  # fmt: skip
            pane = pane.model_copy(update={"focus_x": fx, "focus_y": fy})
            framed.append(pane.model_copy(update={"face_box": _face_in_pane(face, pane, image_h)}))
        return top, height, title_top, framed

    strips = SPLIT_STRIPS[b.split_layout]
    chosen: tuple[int, tuple[float, float, float, list[SplitPane]]] | None = None
    for title_px in _title_bands():
        for strip in strips:
            layout = laid(strip, title_px)
            boxes = [p.face_box for p in layout[3] if p.face_box is not None]
            if not _crosses((layout[2], layout[2] + title_px), boxes):
                chosen = (title_px, layout)
                break
        if chosen is not None:
            break
    title_px, (top, height, title_top, panes) = chosen or (0, laid(strips[0], 0))
    font_px = _fitted(title, font_px=SPLIT_TITLE_FONT_PX, min_font_px=SPLIT_TITLE_MIN_FONT_PX,
                      style=style, room=WIDTH - 2 * SAFE_LEFT)  # fmt: skip
    # a shrunk band holds a smaller title: the font its line height fits, never below the floor
    band_font = int((title_px - 2 * SPLIT_HIGHLIGHT_PAD_PX) / SPLIT_TITLE_LINE)
    font_px = max(SPLIT_TITLE_MIN_FONT_PX, min(font_px, band_font))
    return SplitSpec(
        left=left, top=top, width=SPLIT_CARD_W, height=height, border_px=border,
        rotate_deg=b.card_rotate_deg, seam_px=SPLIT_SEAM_PX, panes=panes,
        label_px=label_px, label_font_px=SPLIT_LABEL_FONT_PX, title_px=title_px,
        title_font_px=font_px, title_color="#FFFFFF",
        title_words=title_words(title, [p.text for p in panes_wanted], font_px=font_px,
                                style=style) if title_px > 0 else [],  # fmt: skip
        title_top=title_top,
        highlight_fg=style.keyword_fg, highlight_bg=numbers.palette.accent,
        highlight_pad_px=SPLIT_HIGHLIGHT_PAD_PX, highlight_radius_px=SPLIT_HIGHLIGHT_RADIUS_PX,
        badge=(
            BadgeSpec(
                src=badge.src, width=badge.width, height=badge.height,
                left=max(SAFE_LEFT, left - SPLIT_BADGE_DIAMETER / 2),
                top=top - SPLIT_BADGE_DIAMETER * SPLIT_BADGE_DROP,
                diameter=SPLIT_BADGE_DIAMETER, ring_px=SPLIT_BADGE_RING_PX,
                ring_color="#FFFFFF",
            )  # fmt: skip
            if badge is not None
            else None
        ),
        slide_s=b.split_slide_s,
    )


def split_face_boxes(piece: SplitSpec) -> list[tuple[Box, Box]]:
    """105: each pane's face and the pane's picture in composition pixels (the card's
    tilt, a degree or two, left out as `face_box_on` leaves it), the face clipped to the
    picture it is seen in."""
    out: list[tuple[Box, Box]] = []
    for pane in piece.panes:
        if pane.face_box is None:
            continue
        image = Box(piece.left + pane.left, piece.top + pane.top, pane.pane_width,
                    pane.pane_height - piece.label_px)  # fmt: skip
        left, top, right, bottom = pane.face_box
        left, right = max(left + piece.left, image.left), min(right + piece.left, image.right)
        top, bottom = max(top + piece.top, image.top), min(bottom + piece.top, image.bottom)
        if right > left and bottom > top:
            out.append((Box(left, top, right - left, bottom - top), image))
    return out


def stamp_off_split(
    stamp: StampSpec, piece: SplitSpec, *, numbers: StyleNumbers
) -> tuple[StampSpec, bool]:
    """105 (056 (4) on a split): a stamp over a pane's face moves to the face-free band
    - a pane picture's upper or lower third, between two faces, or under the card -
    farthest from every face, and True; unchanged and False when it touches no face or
    no band is free."""
    faces = split_face_boxes(piece)
    if not any(stamp_box(stamp).overlaps(face) for face, _ in faces):
        return stamp, False
    half = _tilt_extent(stamp.width, stamp.height, stamp.rotate_deg)
    sixth = [(image, image.height / 6) for _, image in faces]
    centres = [c for image, h in sixth for c in (image.top + h, image.bottom - h)]
    # between two faces one above the other (a stacked card's two portraits)
    ordered = sorted((face for face, _ in faces), key=lambda f: f.top)
    centres += [(a.bottom + b.top) / 2 for a, b in zip(ordered, ordered[1:], strict=False)]
    centres.append(split_bottom(piece) + STAMP_BELOW_GAP_PX + half)
    best: tuple[float, StampSpec] | None = None
    for centre in centres:
        moved = _stamp_at(stamp, centre, numbers=numbers)
        if moved is None:
            continue
        box = stamp_box(moved)
        if any(box.overlaps(face) for face, _ in faces):
            continue
        clearance = min(box.clearance(face) for face, _ in faces)
        if best is None or clearance > best[0]:
            best = (clearance, moved)
    return (best[1], True) if best is not None else (stamp, False)


# 059: the title strip's text stays this far inside the bar's ends.
TITLE_STRIP_PAD_X = 28.0


def title_strip_spec(text: str, *, until_frame: int, numbers: StyleNumbers) -> TitleStripSpec:
    """The fixed title strip (059): the style's `broll.title_strip` bar from `top_y`,
    across the safe width (the left margin to the platform's right rail), the words in
    the caption weight fitted from `size_px` down to `min_size_px`."""
    row = numbers.title_strip
    assert row is not None, "the style carries no broll.title_strip"
    style = numbers.captions
    width = WIDTH - SAFE_LEFT - SAFE_RIGHT_PX
    font_px = _fitted(text, font_px=row.size_px, min_font_px=row.min_size_px, style=style,
                      room=width - 2 * TITLE_STRIP_PAD_X)  # fmt: skip
    return TitleStripSpec(
        text=text, left=SAFE_LEFT, top=float(row.top_y), width=width, height=float(row.height_px),
        font_px=font_px, font_weight=style.font_weight, fill=row.fill, ink=row.ink,
        slide_s=row.duration_s, until_frame=until_frame,
    )  # fmt: skip


def title_strip_box(strip: TitleStripSpec | None) -> Box | None:
    return None if strip is None else Box(strip.left, strip.top, strip.width, strip.height)


def wall_columns(cells: int) -> int:
    """2x2 up to four cells, three across above it (the AC's 2x2 to 3x3 grid)."""
    if cells <= 1:
        return 1
    return WALL_SMALL_COLUMNS if cells <= WALL_SMALL_COLUMNS**2 else WALL_MAX_COLUMNS


def wall_spec(items: Sequence[ItemSource], *, numbers: StyleNumbers) -> WallSpec:
    """The `wall` set piece (nkb_09): the grid laid out to fill the band between
    `WALL_BAND_TOP` and the style's `broll.card_max_bottom_y`, every cell flying in from
    an alternating side on the style's stagger, each with its own Ken Burns."""
    b = numbers.broll
    cells_wanted = [i for i in items[: b.wall_cells_max] if i.card is not None]
    columns = wall_columns(len(cells_wanted))
    rows = math.ceil(len(cells_wanted) / columns) if cells_wanted else 0
    width = (WIDTH - 2 * SAFE_LEFT - (columns - 1) * WALL_GAP_PX) / columns
    band = b.card_max_bottom_y - WALL_BAND_TOP
    height = (band - (rows - 1) * WALL_GAP_PX) / rows if rows else 0.0
    border = b.card_border_px
    cells: list[CardBox] = []
    for i, item in enumerate(cells_wanted):
        card = item.card
        assert card is not None
        strip = SPLIT_LABEL_PX if item.text else 0
        scale_from, scale_to = _ken_burns(i, b.photo_scale_from, b.photo_scale_to, True)
        cells.append(
            CardBox(
                src=card.src, width=card.width, height=card.height,
                left=SAFE_LEFT + (i % columns) * (width + WALL_GAP_PX),
                top=WALL_BAND_TOP + (i // columns) * (height + WALL_GAP_PX),
                box_width=width, box_height=height, image_width=width - 2 * border,
                image_height=height - 2 * border - strip, border_px=border,
                rotate_deg=WALL_ROTATES[i % len(WALL_ROTATES)], label=item.text,
                strip_px=strip, strip_font_px=SPLIT_LABEL_FONT_PX,
                from_x=-WALL_FLY_SIDE_PX if i % 2 == 0 else WALL_FLY_SIDE_PX,
                delay_s=i * WALL_STAGGER_S, scale_from=scale_from, scale_to=scale_to,
            )  # fmt: skip
        )
    return WallSpec(cells=cells, columns=columns, spring_s=b.wall_spring_s)


def item_sources(
    beat: Beat, manifest: AssetManifest | None, job_dir: Path | None
) -> list[ItemSource]:
    """A set-piece beat's items resolved through the manifest's aliases (027). An item
    naming an id the asset step never saw is a render-spec error - the plan and the
    manifest disagree. An id the asset step resolved to nothing (a rung-4 rescue of the
    beat that sourced it) leaves the item without a picture: a list row draws as text,
    and a pane or a cell is left out rather than drawn blank."""
    out: list[ItemSource] = []
    for item in beat.items:
        if item.asset_id is None or manifest is None or job_dir is None:
            out.append(ItemSource(text=item.text))
            continue
        if item.asset_id not in manifest.aliases and manifest.asset(item.asset_id) is None:
            raise RenderError(
                f"{beat.id}: set-piece item asset {item.asset_id!r} was never sourced "
                "(4.1: every item reads its asset by id from the manifest)"
            )
        asset_id = manifest.aliases.get(item.asset_id, item.asset_id)
        record = manifest.asset(asset_id) if asset_id is not None else None
        if record is not None and record.kind == "clip":
            raise RenderError(
                f"{beat.id}: set-piece item asset {item.asset_id!r} is a clip; a set piece "
                "shows stills (058)"
            )
        out.append(
            ItemSource(
                text=item.text,
                card=(
                    CardSource(src=str((job_dir / record.file).resolve()), width=record.width,
                               height=record.height, label=item.text)  # fmt: skip
                    if record is not None
                    else None
                ),
            )
        )
    return out


def badge_source(
    beat: Beat, manifest: AssetManifest | None, job_dir: Path | None
) -> CardSource | None:
    """The split's circular badge (5.2): the beat's own sourced asset, the mark the
    two panes belong to. None where the beat was rescued onto the gradient (4.4)."""
    if manifest is None or job_dir is None:
        return None
    decided = manifest.beat(beat.id)
    record = manifest.asset(decided.asset_id) if decided and decided.asset_id else None
    if record is None:
        return None
    return CardSource(
        src=str((job_dir / record.file).resolve()), width=record.width, height=record.height
    )


def set_piece(
    beat: Beat, manifest: AssetManifest | None, job_dir: Path | None, *,
    numbers: StyleNumbers, pip_top: int | None = None, face_of: FaceOf | None = None,
) -> tuple[ListSpec | None, SplitSpec | None, WallSpec | None]:  # fmt: skip
    """The `list`, `split` or `wall` this beat draws, already measured and placed; the
    split ends above `pip_top`, the top of the circle the spec draws (051), its panes
    framed round the faces `face_of` finds (105)."""
    if beat.kind not in ("list", "split", "wall"):
        return None, None, None
    items = item_sources(beat, manifest, job_dir)
    if beat.kind == "list":
        return list_spec(beat.set_piece_title, items, numbers=numbers), None, None
    if beat.kind == "split":
        badge = badge_source(beat, manifest, job_dir)
        split = split_spec(beat.set_piece_title, items, badge, numbers=numbers, pip_top=pip_top,
                           face_of=face_of)
        return None, split, None
    return None, None, wall_spec(items, numbers=numbers)


# --- charts and labelled diagrams (ticket 021; decisions 9.2, 9.3, 5.5) -----------------


def diagram_base(
    beat: Beat, manifest: AssetManifest | None, job_dir: Path | None
) -> infographics.DiagramAsset | None:
    """The label-free base of an `infographic` beat: the beat's own asset as the step
    classified it (5.3). None where the beat was rescued onto the gradient (4.4) - a
    diagram with no picture under it is the PIP and its stamp word, not blank labels."""
    if manifest is None or job_dir is None:
        return None
    decided = manifest.beat(beat.id)
    record = manifest.asset(decided.asset_id) if decided and decided.asset_id else None
    if decided is None or record is None or decided.treatment == "gradient":
        return None
    return infographics.DiagramAsset(
        src=str((job_dir / record.file).resolve()), width=record.width, height=record.height,
        treatment=decided.treatment, crop=decided.crop,
    )  # fmt: skip


def infographic(
    beat: Beat, manifest: AssetManifest | None, job_dir: Path | None, *, numbers: StyleNumbers
) -> tuple[ChartLayout | None, DiagramLayout | None]:
    """The `chart` drawn from the beat's series, or the labelled diagram drawn over its
    base (021). A recipe the frame cannot hold is a build failure with the numbers in the
    message, as a finale outside its band is (026)."""
    if beat.kind not in ("chart", "infographic"):
        return None, None
    try:
        if beat.kind == "chart":
            return (
                infographics.resolve_chart(
                    infographics.chart_recipe(beat), numbers=numbers.info
                ),
                None,
            )
        base = diagram_base(beat, manifest, job_dir)
        if base is None:
            return None, None
        return None, infographics.resolve_diagram(
            infographics.diagram_recipe(beat), base, numbers=numbers.info,
            length_s=beat.end - beat.start,
        )  # fmt: skip
    except infographics.InfographicError as exc:
        raise RenderError(f"{beat.id}: {exc}") from None


def map_layout(
    beat: Beat, *, numbers: StyleNumbers, geocoder: geo.Geocoder, stamp: StampSpec | None = None
) -> MapLayout | None:
    """The `map` drawn from the bundled geodata with its markers at the geocoder's
    points (020, 9.3). A name the geocoder does not know is a build failure naming it,
    as a diagram label outside the safe area is (021): never a guessed point. The
    beat's `pin_drop`, `route_arrow` and `object_path` overlays switch the three map
    animations on, timed from the beat's length (028). The beat's `stamp` is kept clear
    of by the target tag and the country names (104; run05 b07)."""
    if beat.kind != "map":
        return None
    avoid: list[tuple[float, float, float, float]] = []
    if stamp is not None:
        box = stamp_box(stamp)
        avoid.append((box.left, box.top, box.left + box.width, box.top + box.height))
    try:
        return infographics.resolve_map(
            infographics.map_recipe(beat), numbers=numbers.info, geocoder=geocoder,
            overlays=beat.overlays, length_s=beat.end - beat.start, avoid=avoid,
        )  # fmt: skip
    except (infographics.InfographicError, geo.GeocodeError, ValueError, KeyError) as exc:
        # 097: any geocoding or recipe failure names the beat, so the editor can rescue it
        raise RenderError(f"{beat.id}: {exc}") from None


def _stamp_text(beat: Beat, manifest: AssetManifest | None) -> str | None:
    """The beat's stamp word: its own landed event, else the rescue word a rung-3 or
    rung-4 beat carries (4.4, 016)."""
    if beat.event.kind == "stamp" and beat.event.text:
        return beat.event.text
    decided = manifest.beat(beat.id) if manifest is not None else None
    return decided.stamp if decided is not None and decided.rescued else None


def _check_finale(plan: PicturePlan, captions: Captions, numbers: StyleNumbers) -> Beat | None:
    """The finale beat, its length inside the style's band and no caption page running
    into it (3.4, 6.1). A plan with no finale beat is the grammar's rejection (3.2)."""
    beat = next((b for b in plan.beats if b.id == plan.finale.beat_id), None)
    if beat is None:
        return None
    length = beat.end - beat.start
    if not numbers.finale.min_s - 1e-9 <= length <= numbers.finale.max_s + 1e-9:
        raise RenderError(
            f"the finale beat {beat.id} runs {length:g} s, outside finale.min_s-finale.max_s "
            f"{numbers.finale.min_s:g}-{numbers.finale.max_s:g} s"
        )
    late = [p.index for p in captions.pages if p.end > beat.start + 1e-9]
    if late:
        raise RenderError(
            f"caption pages {late} run into the finale beat {beat.id} at {beat.start:g} s "
            "(6.1: captions are hidden from the finale word onward)"
        )
    return beat


# --- the spec --------------------------------------------------------------------------


def build_spec(
    plan: PicturePlan,
    captions: Captions,
    *,
    presenter: Path,
    source_size: tuple[int, int],
    duration_s: float,
    numbers: StyleNumbers | None = None,
    fps: int = FPS,
    manifest: AssetManifest | None = None,
    job_dir: Path | None = None,
    pip: PipGeometry | None = None,
    geocoder: geo.Geocoder | None = None,
    detector: presenter.FaceDetector | None = None,
    presenter_face: FaceBox | None = None,
    log: Callable[[str], None] | None = None,
) -> RenderSpec:
    """`pip` is the measured geometry from `job.json.presenter` (013); None falls back
    to `fixed_pip`. Whichever it is, it is derived first: the cards and the split
    composite are placed against the top of the circle the spec draws, not the style's
    fixed `pip.top` (051). `geocoder` places the map markers (020); None is the bundled
    gazetteer, and whichever it is, it is bound to the job's directory for its cache.
    `detector` is the 3.3 face detector the stamps, counters, text pops and bubbles
    are kept off faces with (056 (4), 061, 063); None runs no detection and keeps
    today's placement. `presenter_face` is the measured face of the presenter cut
    (`job.json.presenter`), which a text pop or a bubble on a `full` beat is kept off
    (061, 063). `log` gets one line per stamp moved, or left in place with no free
    band, and one per text pop or bubble moved or dropped."""
    numbers = numbers or style_numbers(styles.DEFAULT)
    frames = round(duration_s * fps)
    geometry = pip or fixed_pip(source_size, numbers)
    faces: dict[str, FaceBox | None] = {}

    def face_in(src: str) -> FaceBox | None:
        """105: the face on a split pane's file (103: on a still, for `crop_fill`), detected
        once per file like `face_on`."""
        if detector is None:
            return None
        if src not in faces:
            try:
                faces[src] = detector.detect(Path(src))
            except RuntimeError as exc:
                faces[src] = None
                if log is not None:
                    log(f"faces: face detection skipped on {Path(src).name}: {exc}")
        return faces[src]

    visuals = _visuals(plan, manifest, job_dir, numbers, pip_top=geometry.top, fps=fps,
                       face_of=face_in)
    geocoder = geocoder or geo.GazetteerGeocoder()
    if job_dir is not None:
        geocoder = geocoder.for_job(job_dir)
    finale_beat = _check_finale(plan, captions, numbers)
    sources = card_sources(plan, manifest, job_dir, count=numbers.broll.finale_cards)
    two_lines = set(captions.beats_with_two_lines)
    # 059: the style's fixed title strip, shown until the finale; the overlays keep off it.
    strip = (
        title_strip_spec(
            plan.title_strip, numbers=numbers,
            until_frame=round(finale_beat.start * fps) if finale_beat is not None else frames,
        )  # fmt: skip
        if numbers.title_strip is not None and plan.title_strip.strip()
        else None
    )
    strip_box = title_strip_box(strip)

    def clear_of_strip(blocked: dict[str, Box]) -> dict[str, Box]:
        return blocked if strip_box is None else {**blocked, "the title strip": strip_box}

    def face_on(visual: VisualSpec | None) -> Box | None:
        """The face on the beat's image in composition pixels, detected once per file.
        A clip (058) has no still to read: the overlays keep today's placement."""
        if detector is None or visual is None or visual.treatment == "clip":
            return None
        if visual.src not in faces:
            try:
                faces[visual.src] = detector.detect(Path(visual.src))
            except RuntimeError as exc:
                faces[visual.src] = None
                if log is not None:
                    log(f"stamp: face detection skipped on {Path(visual.src).name}: {exc}")
        face = faces[visual.src]
        return face_box_on(visual, face) if face is not None else None

    def off_face[S: StampSpec](beat_id: str, placed: S, visual: VisualSpec | None) -> S:
        face = face_on(visual)
        if face is None or visual is None:
            return placed
        moved, band = stamp_clear_of(placed, face, image_box_on(visual), numbers=numbers)
        if log is not None:
            if band is not None:
                log(f"stamp: {beat_id}: {placed.text!r} moved off the face to the image's "
                    f"{band} (056)")  # fmt: skip
            elif moved is placed and stamp_box(placed).overlaps(face):
                log(f"stamp: {beat_id}: {placed.text!r} left in place, no face-free band on "
                    "the image (056)")  # fmt: skip
        return cast("S", moved)

    def text_pops(
        b: Beat, mode: Mode, visual: VisualSpec | None, split: SplitSpec | None = None
    ) -> tuple[TextPopSpec, ...]:
        """061: the beat's pops placed off the circle (a `pip` beat), the caption band
        and the face - the image's (detected) or the presenter's own (a `full` beat)."""
        if not b.text_pops:
            return ()
        blocked: dict[str, Box] = {}
        if mode == "pip":
            blocked["the PIP circle"] = Box(
                float(geometry.left), float(geometry.top), float(geometry.diameter),
                float(geometry.diameter),
            )  # fmt: skip
        band_top = styles.caption_block_top(numbers.captions)
        blocked["the caption band"] = Box(0.0, band_top, float(WIDTH), HEIGHT - band_top)
        face = presenter_face_box(presenter_face) if mode == "full" and presenter_face else None
        face = face if face is not None else face_on(visual)
        if face is not None:
            blocked["the face"] = face
        # 105: the faces on a split's panes, as the face on a card
        for i, (pane_face, _) in enumerate(split_face_boxes(split) if split else []):
            blocked[f"the face on pane {i + 1}"] = pane_face
            face = face or pane_face
        blocked = clear_of_strip(blocked)
        placed: list[TextPopSpec] = []
        for i, pop in enumerate(b.text_pops):
            spec, placement = text_pop_spec(
                pop, i, beat_start_s=b.start, beat_end_s=b.end, numbers=numbers,
                blocked=blocked, image=image_box_on(visual) if visual is not None else None,
            )  # fmt: skip
            if spec is None or placement is None:
                if face is None:
                    raise RenderError(
                        f"{b.id}: text pop {pop.text!r} at ({pop.x:g} %, {pop.y:g} %) has no "
                        "spot clear of the PIP circle and the captions inside the safe area (061)"
                    )
                if log is not None:
                    log(f"text pop: {b.id}: {pop.text!r} dropped, no spot clear of the face, "
                        "the circle and the captions (061)")  # fmt: skip
                continue
            if placement.cleared and log is not None:
                log(f"text pop: {b.id}: {pop.text!r} moved off {' and '.join(placement.cleared)} "
                    f"to ({spec.left + spec.width / 2:.0f}, {spec.top + spec.height / 2:.0f}) "
                    "(061)")  # fmt: skip
            placed.append(spec)
        return tuple(placed)

    def bubbles(
        b: Beat, mode: Mode, visual: VisualSpec | None, stamp: StampSpec | None
    ) -> tuple[BubbleSpec, ...]:
        """063: the beat's bubbles placed off the circle (a `pip` beat), the caption
        band, the stamp, the face - the image's (detected) or the presenter's own (a
        `full` beat) - and each other."""
        if not b.bubbles:
            return ()
        blocked: dict[str, Box] = {}
        if mode == "pip":
            blocked["the PIP circle"] = Box(
                float(geometry.left), float(geometry.top), float(geometry.diameter),
                float(geometry.diameter),
            )  # fmt: skip
        band_top = styles.caption_block_top(numbers.captions)
        blocked["the caption band"] = Box(0.0, band_top, float(WIDTH), HEIGHT - band_top)
        if stamp is not None:
            blocked["the stamp"] = stamp_box(stamp)
        face = presenter_face_box(presenter_face) if mode == "full" and presenter_face else None
        face = face if face is not None else face_on(visual)
        if face is not None:
            blocked["the face"] = face
        blocked = clear_of_strip(blocked)
        placed: list[BubbleSpec] = []
        for i, bubble in enumerate(b.bubbles):
            spec, placement = bubble_spec(
                bubble, beat_id=b.id, beat_start_s=b.start, beat_end_s=b.end, numbers=numbers,
                blocked=blocked, image=image_box_on(visual) if visual is not None else None,
            )  # fmt: skip
            label = f"{bubble.shape} bubble {bubble.text!r}"
            if spec is None or placement is None:
                if face is None:
                    raise RenderError(
                        f"{b.id}: {label} at ({bubble.x:g} %, {bubble.y:g} %) has no spot clear "
                        "of the PIP circle, the captions and the stamp inside the safe area (063)"
                    )
                if log is not None:
                    log(f"bubble: {b.id}: {label} dropped, no spot clear of the face, the circle, "
                        "the captions and the stamp (063)")  # fmt: skip
                continue
            if placement.cleared and log is not None:
                log(f"bubble: {b.id}: {label} moved off {' and '.join(placement.cleared)} "
                    f"to ({spec.left + spec.width / 2:.0f}, {spec.top + spec.height / 2:.0f}); "
                    f"the tail still points at ({spec.tip_x:.0f}, {spec.tip_y:.0f}) "
                    "(063)")  # fmt: skip
            blocked = {**blocked, "the first bubble" if i == 0 else f"bubble {i + 1}":
                       Box(spec.left, spec.top, spec.width, spec.height)}  # fmt: skip
            placed.append(spec)
        return tuple(placed)

    def sticker_specs(
        b: Beat, mode: Mode, visual: VisualSpec | None, stamp: StampSpec | None,
        pops: Sequence[TextPopSpec], said: Sequence[BubbleSpec],
    ) -> tuple[StickerSpec, ...]:  # fmt: skip
        """062: the beat's sticker, its file the job's copy the asset step fetched (none:
        left out, logged), placed above the circle or on its point, off the circle (a
        `pip` beat), the caption band, the stamp, the face and the beat's text pops and
        bubbles."""
        if not b.stickers:
            return ()
        blocked: dict[str, Box] = {}
        circle = None
        if mode == "pip":
            circle = Box(float(geometry.left), float(geometry.top), float(geometry.diameter),
                         float(geometry.diameter))  # fmt: skip
            blocked["the PIP circle"] = circle
        band_top = styles.caption_block_top(numbers.captions)
        blocked["the caption band"] = Box(0.0, band_top, float(WIDTH), HEIGHT - band_top)
        if stamp is not None:
            blocked["the stamp"] = stamp_box(stamp)
        face = presenter_face_box(presenter_face) if mode == "full" and presenter_face else None
        face = face if face is not None else face_on(visual)
        if face is not None:
            blocked["the face"] = face
        for i, pop in enumerate(pops):
            blocked[f"text pop {i + 1}"] = Box(pop.left, pop.top, pop.width, pop.height)
        for i, bubble in enumerate(said):
            blocked[f"bubble {i + 1}"] = Box(bubble.left, bubble.top, bubble.width, bubble.height)
        blocked = clear_of_strip(blocked)
        placed: list[StickerSpec] = []
        for sticker in b.stickers:
            record = manifest.sticker(sticker.name) if manifest is not None else None
            if record is None or job_dir is None:
                if log is not None:
                    log(f"sticker: {b.id}: {sticker.name!r} has no fetched file; left out (062)")
                continue
            spec, placement = sticker_spec(
                sticker, src=str((job_dir / record.file).resolve()), beat_id=b.id,
                beat_start_s=b.start, beat_end_s=b.end, numbers=numbers, blocked=blocked,
                image=image_box_on(visual) if visual is not None else None, circle=circle,
            )  # fmt: skip
            if spec is None or placement is None:
                if face is None:
                    raise RenderError(
                        f"{b.id}: sticker {sticker.name!r} has no spot clear of the PIP circle, "
                        "the captions, the stamp and the beat's pops inside the safe area (062)"
                    )
                if log is not None:
                    log(f"sticker: {b.id}: {sticker.name!r} dropped, no spot clear of the face, "
                        "the circle and the captions (062)")  # fmt: skip
                continue
            if placement.cleared and log is not None:
                log(f"sticker: {b.id}: {sticker.name!r} moved off "
                    f"{' and '.join(placement.cleared)} to ({placement.cx:.0f}, "
                    f"{placement.cy:.0f}) (062)")  # fmt: skip
            placed.append(spec)
        return tuple(placed)

    beats: list[BeatSpec] = []
    for b in plan.beats:
        if b.enter not in numbers.transitions.enabled:
            raise RenderError(
                f"{b.id}: enter {b.enter!r} is not in the style's broll.enter_transitions "
                f"{numbers.transitions.enabled} (9.4)"
            )
        mode, visual = visuals.get(b.id, (b.mode, None))
        stamp = _stamp_text(b, manifest)
        labelled = visual is not None and visual.card is not None and visual.card.strip_px > 0
        label = b.event.text if b.event.kind == "lower_third" and b.event.text else None
        rows, split, wall = set_piece(b, manifest, job_dir, numbers=numbers,
                                      pip_top=geometry.top, face_of=face_in)  # fmt: skip
        chart, diagram = infographic(b, manifest, job_dir, numbers=numbers)
        start_frame, end_frame = round(b.start * fps), round(b.end * fps)
        placed_stamp = off_face(b.id, stamp_spec(stamp, numbers=numbers), visual) if stamp else None
        if placed_stamp is not None and split is not None:
            # 105: a stamp on a split keeps off the panes' faces
            placed_stamp, moved = stamp_off_split(placed_stamp, split, numbers=numbers)
            if moved and log is not None:
                log(f"stamp: {b.id}: {placed_stamp.text!r} moved off a split pane's face (105)")
        placed_pops = text_pops(b, mode, visual, split)
        placed_bubbles = bubbles(b, mode, visual, placed_stamp)
        beats.append(
            BeatSpec(
                id=b.id,
                start_frame=start_frame,
                end_frame=end_frame,
                mode=mode,
                kind=b.kind,
                enter=b.enter,
                visual=visual,
                punch_in=PUNCH_IN if mode == "full" else None,
                stamp=placed_stamp,
                lower_third=(
                    lower_third_spec(label, numbers=numbers)
                    if label and not labelled and b.id not in two_lines
                    else None
                ),
                text_pops=placed_pops,
                bubbles=placed_bubbles,
                stickers=sticker_specs(b, mode, visual, placed_stamp, placed_pops, placed_bubbles),
                finale=(
                    finale_spec(plan.finale.text, sources, numbers=numbers)
                    if finale_beat is not None and b.id == finale_beat.id
                    else None
                ),
                split=split,
                wall=wall,
                list=rows,
                chart=chart,
                infographic=diagram,
                map=map_layout(b, numbers=numbers, geocoder=geocoder, stamp=placed_stamp),
                counter=(
                    off_face(
                        b.id,
                        counter_spec(b.counter, frames=end_frame - start_frame, fps=fps,
                                     numbers=numbers),  # fmt: skip
                        visual,
                    )
                    if b.counter is not None
                    else None
                ),
            )
        )
    return RenderSpec(
        width=WIDTH,
        height=HEIGHT,
        fps=fps,
        frames=frames,
        presenter=str(presenter),
        source_width=source_size[0],
        source_height=source_size[1],
        beats=beats,
        captions=[
            CaptionPageSpec(index=p.index, start=p.start, end=p.end, lines=p.lines, words=p.words)
            for p in captions.pages
        ],
        beats_with_two_lines=captions.beats_with_two_lines,
        pip=geometry,
        palette=numbers.palette,
        caption_style=numbers.captions,
        transitions=numbers.transitions,
        title_strip=strip,
    )


# --- the driver ------------------------------------------------------------------------

_PROGRESS = re.compile(r"^progress (\d+)/(\d+)\s*$")
_DONE = re.compile(r"^done frames=(\d+) render_s=([\d.]+) bundle_s=([\d.]+)\s*$")


def parse_progress(line: str) -> tuple[int, int] | None:
    match = _PROGRESS.match(line)
    return (int(match.group(1)), int(match.group(2))) if match else None


@dataclass(frozen=True)
class DriverResult:
    frames: int
    render_s: float
    bundle_s: float
    wall_s: float


def registry() -> list[str]:
    """The component names the Node project exports (9.2)."""
    return list(json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["components"])


def node_binary() -> str:
    node = shutil.which("node")
    if node is None:
        raise RenderError("node is not on PATH; the picture engine needs Node (ticket 004)")
    return node


def run_driver(
    spec: RenderSpec,
    *,
    spec_path: Path,
    out_path: Path,
    log_path: Path,
    on_progress: Callable[[int], None] | None = None,
    concurrency: int = CONCURRENCY,
) -> DriverResult:
    """Render `spec` to `out_path` through the driver; every driver line lands in
    `log_path`, `progress` lines reach `on_progress` as a percentage when it changes."""
    spec_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    argv = [
        node_binary(),
        str(DRIVER),
        "render",
        "--spec",
        str(spec_path),
        "--out",
        str(out_path),
        "--concurrency",
        str(concurrency),
    ]
    done: DriverResult | None = None
    last_pct = -1
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        log.write(" ".join(argv) + "\n")

        def on_line(stream: str, line: str) -> None:
            nonlocal done, last_pct
            log.write(f"[{stream}] {line}\n")
            if stream != "out":
                return
            progress = parse_progress(line)
            if progress is not None and on_progress is not None:
                rendered, total = progress
                pct = min(100, math.floor(100 * rendered / max(1, total)))
                if pct != last_pct:
                    last_pct = pct
                    on_progress(pct)
                return
            match = _DONE.match(line)
            if match:
                done = DriverResult(
                    frames=int(match.group(1)),
                    render_s=float(match.group(2)),
                    bundle_s=float(match.group(3)),
                    wall_s=0.0,
                )

        proc = subproc.stream(argv, on_line, timeout_s=DRIVER_TIMEOUT_S, cwd=REPO_ROOT)
    if proc.returncode != 0 or done is None or not out_path.is_file():
        tail = log_path.read_text(encoding="utf-8")[-4000:]
        raise RenderError(f"remotion driver exited {proc.returncode}:\n{tail}")
    if on_progress is not None and last_pct != 100:
        on_progress(100)
    return DriverResult(
        frames=done.frames,
        render_s=done.render_s,
        bundle_s=done.bundle_s,
        wall_s=time.perf_counter() - started,
    )


def load_captions(job: Job) -> Captions:
    return Captions.model_validate_json(
        (job.work_dir / "captions.json").read_text(encoding="utf-8")
    )


def _load_plan(job: Job) -> PicturePlan:
    return PicturePlan.model_validate_json(
        (job.work_dir / "plan.json").read_text(encoding="utf-8")
    )


def _raw_path(job: Job) -> Path:
    return job.input_dir / (job.record.input.file if job.record.input else "raw.mp4")


def _cut_path(job: Job) -> Path:
    return job.work_dir / "cut.mp4"


def measured_pip(job: Job) -> PipGeometry | None:
    """The PIP geometry `presenter.measure` wrote to `job.json` at `transcribing` (013),
    or None on a job that was never measured (the renderer's own tests)."""
    measured = job.record.presenter
    return measured.pip if measured is not None else None


def spec_for_job(
    job: Job,
    *,
    numbers: StyleNumbers | None = None,
    geocoder: geo.Geocoder | None = None,
    detector: presenter.FaceDetector | None = None,
) -> RenderSpec:
    """The RenderSpec from the job's files: plan.json, captions.json, the presenter cut
    (`work/cut.mp4`, 005) and the measured PIP geometry (`job.json.presenter`, 013),
    with the numbers of the job's resolved style (`job.json.style`, 008). The short is
    as long as the cut list. `geocoder` places the map markers (020); `detector` keeps
    the stamps off faces (056 (4)), its lines going to `job.log`; a text pop on a `full`
    beat is kept off the measured presenter face the same way (061)."""
    numbers = numbers or style_numbers(job.record.style)
    plan = _load_plan(job)
    captions = load_captions(job)
    cut = _cut_path(job)
    if not cut.is_file():
        raise RenderError("work/cut.mp4 is missing: cut_presenter runs before the picture")
    return build_spec(
        plan,
        captions,
        presenter=cut,
        source_size=ffmpeg.video_size(cut),
        duration_s=presenter.total_duration(presenter.cut_list(plan)),
        numbers=numbers,
        manifest=assets.load_manifest(job.path),
        job_dir=job.path,
        pip=measured_pip(job),
        geocoder=geocoder,
        detector=detector,
        presenter_face=job.record.presenter.face if job.record.presenter else None,
        log=lambda line: jobs.note(job, line),
    )


def render_picture(
    job: Job,
    *,
    on_progress: Callable[[int], None] | None = None,
    geocoder: geo.Geocoder | None = None,
    detector: presenter.FaceDetector | None = None,
) -> Path:
    """The `rendering` step's picture half: `work/picture.mp4`, silent H.264."""
    spec = spec_for_job(job, geocoder=geocoder, detector=detector)
    out = job.work_dir / "picture.mp4"
    run_driver(
        spec,
        spec_path=job.work_dir / "render_spec.json",
        out_path=out,
        log_path=job.work_dir / "render.log",
        on_progress=on_progress,
    )
    return out


# --- the ffmpeg half (ticket 005; decisions 2.1, 7.3, 9.1, 10.1) -----------------------


def span_filter(spans: Sequence[Span], *, video: bool, audio: bool) -> str:
    """A filter graph that trims each span of input 0 and concatenates them in order;
    the outputs are `[vc]` and/or `[ac]`. Both streams use the same span times, so the
    cut and the voice stem stay sample-aligned."""
    parts: list[str] = []
    inputs = ""
    for i, span in enumerate(spans):
        if video:
            parts.append(
                f"[0:v]trim=start={span.start:.3f}:end={span.end:.3f},setpts=PTS-STARTPTS[v{i}]"
            )
            inputs += f"[v{i}]"
        if audio:
            parts.append(
                f"[0:a]atrim=start={span.start:.3f}:end={span.end:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
            inputs += f"[a{i}]"
    outs = ("[vc]" if video else "") + ("[ac]" if audio else "")
    parts.append(f"{inputs}concat=n={len(spans)}:v={int(video)}:a={int(audio)}{outs}")
    return ";".join(parts)


def crop_filter(source_size: tuple[int, int]) -> str:
    """Centre crop to the largest 9:16 window (1.5x rule enforced by `crop_window`),
    scale to the composition size (`presenter.scale_filter`, shared with the 013
    stills), constant 30 fps, 4:2:0."""
    return f"{presenter.scale_filter(source_size)},fps={FPS},format=yuv420p"


def cut_presenter(job: Job) -> Path:
    """`work/cut.mp4`: the cut list applied to the raw upload, CFR 30 fps H.264 with no
    B-frames, 1080x1920, its audio carried along as AAC."""
    plan = _load_plan(job)
    raw = _raw_path(job)
    if job.record.input is not None:
        source_size = (job.record.input.width, job.record.input.height)
    else:
        source_size = ffmpeg.video_size(raw)
    picture = crop_filter(source_size)  # raises UpscaleExceeded before ffmpeg starts
    spans = presenter.cut_list(plan)
    graph = f"{span_filter(spans, video=True, audio=True)};[vc]{picture}[v]"
    out = _cut_path(job)
    ffmpeg.run(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(raw),
            "-filter_complex", graph, "-map", "[v]", "-map", "[ac]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-bf", "0",
            "-fps_mode", "cfr", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE),
            "-movflags", "+faststart", str(out),
        ],  # fmt: skip
        timeout_s=FFMPEG_TIMEOUT_S,
    )
    presenter.write_cut_list(job, spans)  # 031: the boundaries T10 checks
    return out


def voice_chain() -> str:
    """Research §5 / decision 7.3 voice chain before loudnorm: the mono fold inside the
    graph (never `-ac 1`), high-pass 80 Hz, compressor -18 dB ratio 2.5."""
    return (
        "aformat=channel_layouts=stereo,pan=mono|c0=0.5*c0+0.5*c1,"
        "highpass=f=80,acompressor=threshold=-18dB:ratio=2.5"
    )


def loudnorm_second_pass(measured: ffmpeg.Loudness, *, target_lufs: float, target_tp: float) -> str:
    """The linear second pass of two-pass loudnorm from the first pass's measurement."""
    return (
        f"{ffmpeg.loudnorm_filter(target_lufs=target_lufs, target_tp=target_tp)}"
        f":measured_I={measured.integrated:g}:measured_TP={measured.true_peak:g}"
        f":measured_LRA={measured.lra:g}:measured_thresh={measured.threshold:g}"
        f":offset={measured.offset:g}:linear=true:print_format=summary"
    )


def _stems_dir(job: Job) -> Path:
    stems = job.work_dir / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    return stems


def voice_stem(job: Job) -> Path:
    """`work/stems/voice.wav`: the cut list's audio through the voice chain and
    two-pass loudnorm to -19 LUFS / -3 dBTP, mono 48 kHz PCM."""
    plan = _load_plan(job)
    raw = _raw_path(job)
    graph = span_filter(presenter.cut_list(plan), video=False, audio=True)
    measured = ffmpeg.measure_loudness(
        raw,
        prefilter=voice_chain(),
        target_lufs=VOICE_LUFS,
        target_tp=VOICE_TP,
        filter_complex=graph,
        label="ac",
    )
    second = loudnorm_second_pass(measured, target_lufs=VOICE_LUFS, target_tp=VOICE_TP)
    out = _stems_dir(job) / "voice.wav"
    ffmpeg.run(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(raw),
            "-filter_complex", f"{graph};[ac]{voice_chain()},{second},aresample={SAMPLE_RATE}[out]",
            "-map", "[out]", "-c:a", "pcm_s16le", str(out),
        ],  # fmt: skip
        timeout_s=FFMPEG_TIMEOUT_S,
    )
    return out


def master_chain(measured: ffmpeg.Loudness, *, request_lufs: float = MASTER_LUFS) -> str:
    """Master: two-pass loudnorm to `request_lufs` / (-1.5 dBTP less the AAC headroom)
    then the 0.891 limiter. The limiter's auto-level is off; on, it would re-gain the
    output to 0 dB and break T4."""
    second = loudnorm_second_pass(
        measured, target_lufs=request_lufs, target_tp=MASTER_TP - AAC_HEADROOM_DB
    )
    return f"{second},alimiter=limit={LIMITER}:level=false,aresample={SAMPLE_RATE}"


MASTER_TOLERANCE_LU = 0.2
MASTER_PASSES = 4


def master(source: Path, mix: Path) -> ffmpeg.Loudness:
    """Render `source` through the master chain into `mix` and converge on -14 LUFS.

    loudnorm's linear mode is impossible whenever the gain to target would push the
    peaks past the -1.5 dBTP ceiling (any voice stem peaking above about -6.5 dBTP, so
    most speech), and its dynamic mode lands a few tenths of an LU off a fresh
    measurement. The requested target is corrected by the measured error and the pass
    re-run, at most `MASTER_PASSES` times, so T4 (-14 +- 0.5) holds on every recording
    while the chain itself stays the 7.3 graph."""
    request = MASTER_LUFS
    got: ffmpeg.Loudness | None = None
    for _ in range(MASTER_PASSES):
        measured = ffmpeg.measure_loudness(
            source, target_lufs=request, target_tp=MASTER_TP - AAC_HEADROOM_DB
        )
        ffmpeg.run(
            [
                ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(source),
                "-af", master_chain(measured, request_lufs=request),
                "-c:a", "pcm_s16le", str(mix),
            ],  # fmt: skip
            timeout_s=FFMPEG_TIMEOUT_S,
        )
        got = ffmpeg.measure_loudness(mix)
        error = MASTER_LUFS - got.integrated
        if abs(error) <= MASTER_TOLERANCE_LU:
            break
        request += error
    assert got is not None
    return got


def _load_story(job: Job) -> SoundStory | None:
    path = job.work_dir / "sound.json"
    if not path.is_file():
        return None
    return SoundStory.model_validate_json(path.read_text(encoding="utf-8"))


def sound_mix(
    job: Job,
    *,
    library: sound.Library | None = None,
    search: sound.AudioSearch | None = None,
    offset_db: float = 0.0,
) -> sound.MixResult | None:
    """The 022 sound director over the job's plan and sound story: the music and SFX
    stems beside the voice, and the premix the master is cut from. None when there is
    nothing to mix - a job planned before the sound call (the renderer's own tests), or
    an empty catalogue with no search to fill it - and the short is then the voice
    alone, as it was before 022. `search` is the 7.2 audio search the director asks
    under the bed-score threshold (024, 054; 070: never for an effect, which comes only
    from the approved library); None means no search is configured. `offset_db` moves
    the bed's target from the style's starting level (091's remembered level).

    054 (1, 5): every search and every sound decision is a `sound:` line in `job.log`,
    and a short that goes out voice-only says why in one line on the job page.

    101: with `job.record.bed_pick` set (093), that bed plays under the whole reel on
    every re-render - change box, rework, rewind - and its rights row is kept; a pick
    no longer in the library is one `sound:` line and the director picks as usual."""
    library = library if library is not None else sound.load_catalogue()
    story = _load_story(job)
    if story is None:
        return None
    if not library.entries and search is None:
        _voice_only(job, sound.NO_SEARCH_LINE)
        return None
    plan = _load_plan(job)
    result = sound.build_mix(
        picked=_picked_bed(job, library),
        stems=_stems_dir(job),
        voice=_stems_dir(job) / "voice.wav",
        plan=plan,
        story=story,
        nums=sound.at_offset(loaded_styles()[job.record.style].sound, offset_db),
        library=library,
        runtime_s=presenter.total_duration(presenter.cut_list(plan)),
        search=search,
        counter_land_s=counter_land_s(loaded_styles()[job.record.style]),
        log=lambda line: jobs.note(job, f"sound: {line}"),
    )
    jobs.note(job, result.summary())
    if result.fallback is not None and result.bed is not None:
        # 076: the bed came from the search, not the approved library; the log has the
        # line already, the page gets it once.
        _page_notice(job, result.fallback)
    for line in result.balance.notes:
        # 088: 069's ceiling on a bed approved by ear - measured, shown, not held against it.
        _page_notice(job, f"sound: {line}")
    if result.balance.bed_dropped is not None:
        # 056 (1): every repair failed on every candidate; the short goes out with the
        # voice and the hits, and the page says so in one line.
        _page_warning(
            job, f"{sound.VOICE_AND_HITS_LINE} (last bed {result.balance.bed_dropped})"
        )
    elif result.bed is None and not result.cues:
        _voice_only(job, sound.NO_SEARCH_LINE if search is None else sound.SEARCH_EMPTY_LINE)
    return result


def _picked_bed(job: Job, library: sound.Library) -> AudioEntry | None:
    """101: the operator's bed pick (093) as a library entry, or None when there is no
    pick or it is not in the library any more (one `sound:` line)."""
    chosen = job.record.bed_pick
    if chosen is None:
        return None
    entry = library.entry(chosen.entry_id)
    if entry is None:
        jobs.note(job, f"sound: the picked bed {chosen.entry_id} is not in the audio library "
                  "any more; the sound director picks the bed (101)")  # fmt: skip
    return entry


def _voice_only(job: Job, why: str) -> None:
    """054 (5): the one line the job log and the job page both carry when the short goes
    out with no bed and no cues; written once, so a retry does not repeat it."""
    _page_warning(job, f"voice only: {why} (the audio catalogue has nothing for this short)")


def _page_warning(job: Job, line: str) -> None:
    """One `sound:` line in job.log and the same line among the job page's warnings,
    written once, so a retry does not repeat it."""
    jobs.note(job, f"sound: {line}")
    _page_notice(job, line)


def _page_notice(job: Job, line: str) -> None:
    """`line` among the job page's warnings, once."""
    current = jobs.load(job.path).record.warnings
    if line not in current:
        jobs.amend(job, warnings=[*current, line])


def counter_land_s(spec: StyleSpec) -> float | None:
    """How long a counter takes to land (029): the stamp's `duration_s`, so the sound
    director fires its hit where the picture lands it. None on a spec with no stamp row."""
    land = spec.broll.motion.get("stamp", {}).get("duration_s")
    return float(land) if land is not None else None


def _audio_rights(job: Job, result: sound.MixResult | None) -> None:
    """5.4 / 016: the music and SFX rows are written where `rights.write` will pick them
    up, then the log is regenerated, so they sit beside the asset rows and survive a
    re-run of the asset step. 101: a picked bed (093) keeps the row it already has."""
    rows = sound.rights_rows(result) if result is not None else []
    if job.record.bed_pick is not None:
        kept = {r.id: r for r in rights.audio_rows(job.path) if r.kind == "music"}
        rows = [
            kept[r.id] if r.kind == "music" and r.id in kept and kept[r.id].sha256 == r.sha256
            else r
            for r in rows
        ]
    rights.write_audio(job.path, rows)
    manifest = assets.load_manifest(job.path)
    if manifest is not None:
        rights.write(job.path, manifest, _load_plan(job))


def mux(
    job: Job,
    *,
    library: sound.Library | None = None,
    search: sound.AudioSearch | None = None,
) -> Path:
    """`work/stems/mix.wav` (the mastered mix of voice, bed and cues; 022) and
    `out/short.mp4`: the picture stream copied, the mix as AAC."""
    stems = _stems_dir(job)
    voice = stems / "voice.wav"
    picture = job.work_dir / "picture.mp4"
    for needed in (voice, picture):
        if not needed.is_file():
            raise RenderError(f"{needed.relative_to(job.path).as_posix()} is missing before mux")
    library = library if library is not None else sound.load_catalogue()
    start = starting_level(job)
    result = sound_mix(job, library=library, search=search, offset_db=start.offset_db)
    mix = stems / "mix.wav"
    master(result.premix if result is not None else voice, mix)
    _audio_rights(job, result)
    if result is not None and result.music is not None:
        # 090: the slider's starting point; 091: the operator's last setting when there is one.
        jobs.amend(job, music_level=start)
    job.out_dir.mkdir(parents=True, exist_ok=True)
    return remux(picture, mix, job.out_dir / "short.mp4")


# 090: the level measure `bed_db_under_voice` is held on - the median of the full-band
# RMS windows under the voice. A slider offset carries its name (089 may add another).
LEVEL_MEASURE = "full_band"


def starting_level(job: Job) -> jobs.MusicLevel:
    """The level a mix starts the bed at (091): a retry (043) keeps the job's recorded
    level; a new job takes the operator's last slider setting from
    `<data_dir>/music_level.json`, whatever style it was set on; with no file, or one
    set on another level measure (ignored with its line), the style's level, offset 0.
    The pipeline's choice: `sound_mix` still repairs a bed that crowds the voice."""
    recorded = job.record.music_level
    if recorded is not None and recorded.measure == LEVEL_MEASURE:
        return recorded
    default = jobs.MusicLevel(
        offset_db=0.0, measure=LEVEL_MEASURE, set_by="default", set_at=datetime.now(UTC)
    )
    last = remembered.load(jobs.data_dir_of(job))
    if last is None:
        return default
    said = f"music level: remembered offset {last.offset_db:+g} dB from job {last.job_id}"
    if last.measure != LEVEL_MEASURE:
        jobs.note(
            job, f"{said} is on measure {last.measure}, not {LEVEL_MEASURE}; ignored, "
            "starting at the style's level",
        )  # fmt: skip
        return default
    jobs.note(job, said)
    return default.model_copy(update={
        "offset_db": last.offset_db, "set_by": "remembered", "from_job": last.job_id,
        "start_db": last.offset_db,
    })  # fmt: skip


def remux(picture: Path, mix: Path, out: Path) -> Path:
    """`out`: the picture stream copied (never re-encoded) and `mix` as AAC."""
    ffmpeg.run(
        [
            ffmpeg.FFMPEG, "-v", "error", "-y", "-i", str(picture), "-i", str(mix),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
        ],  # fmt: skip
        timeout_s=FFMPEG_TIMEOUT_S,
    )
    return out


def render_short(
    job: Job,
    *,
    on_progress: Callable[[int], None] | None = None,
    library: sound.Library | None = None,
    search: sound.AudioSearch | None = None,
    geocoder: geo.Geocoder | None = None,
    detector: presenter.FaceDetector | None = None,
) -> Path:
    """The whole `rendering` step (9.1): cut, voice stem, picture, sound and mux."""
    cut_presenter(job)
    voice_stem(job)
    render_picture(job, on_progress=on_progress, geocoder=geocoder, detector=detector)
    return mux(job, library=library, search=search)


# --- the interface the pipeline uses ---------------------------------------------------


class Renderer(ABC):
    """The render engine as the pipeline sees it: the whole `rendering` step from the
    job's plan to `out/short.mp4`. Remotion and ffmpeg are local, not paid, but a
    render costs seconds, so the fake keeps the pipeline and app tests fast; the real
    path is covered by test_render and smoke (12.1)."""

    @abstractmethod
    def render(
        self,
        job: Job,
        *,
        on_progress: Callable[[int], None] | None = None,
        library: sound.Library | None = None,
    ) -> Path:
        """Write `work/cut.mp4`, `work/stems/*`, `work/picture.mp4` and `out/short.mp4`;
        return the short. `on_progress` gets the picture render's 0-100, and `library` is
        the audio catalogue the sound director mixes from (022); None loads the shipped
        one."""


class RemotionRenderer(Renderer):
    """The real step. `search` is the 7.2 runtime audio search the sound director asks
    when no catalogue bed clears the style's threshold (`sound.freesound`, 024); the
    renderer owns it the way the asset step owns its sources, so the pipeline's `render`
    call stays the same with or without one. `geocoder` places the map markers (020):
    the bundled gazetteer alone by default, with Nominatim behind it when the operator
    enables the fallback (`geo.from_settings`). `detector` is the 3.3 face detector the
    stamps are kept off faces with (056 (4)); None is the Haar cascade, built on first
    use."""

    def __init__(
        self,
        *,
        search: sound.AudioSearch | None = None,
        geocoder: geo.Geocoder | None = None,
        detector: presenter.FaceDetector | None = None,
    ) -> None:
        self._search = search
        self.geocoder = geocoder or geo.GazetteerGeocoder()
        self._detector = detector

    def detector(self) -> presenter.FaceDetector:
        if self._detector is None:
            self._detector = presenter.HaarDetector()
        return self._detector

    def render(
        self,
        job: Job,
        *,
        on_progress: Callable[[int], None] | None = None,
        library: sound.Library | None = None,
    ) -> Path:
        return render_short(
            job, on_progress=on_progress, library=library, search=self._search,
            geocoder=self.geocoder, detector=self.detector(),
        )  # fmt: skip


class FakeRenderer(Renderer):
    """Builds the same RenderSpec (so a bad plan still fails here), reports 0, 50 and
    100, and writes placeholders for every file the step leaves; none is media."""

    def __init__(self) -> None:
        self.jobs: list[Path] = []

    def render(
        self,
        job: Job,
        *,
        on_progress: Callable[[int], None] | None = None,
        library: sound.Library | None = None,
    ) -> Path:
        self.jobs.append(job.path)
        cut = _cut_path(job)
        cut.write_bytes(b"")
        plan = _load_plan(job)
        presenter.write_cut_list(job, presenter.cut_list(plan))
        captions = load_captions(job)
        spec = build_spec(
            plan,
            captions,
            presenter=cut,
            source_size=(WIDTH, HEIGHT),
            duration_s=presenter.total_duration(presenter.cut_list(plan)),
            numbers=style_numbers(job.record.style),
            manifest=assets.load_manifest(job.path),
            job_dir=job.path,
            pip=measured_pip(job),
        )
        (job.work_dir / "render_spec.json").write_text(
            spec.model_dump_json(indent=2), encoding="utf-8"
        )
        (job.work_dir / "render.log").write_text("fake render\n", encoding="utf-8")
        stems = _stems_dir(job)
        (stems / "voice.wav").write_bytes(b"")
        for pct in (0, 50, 100):
            if on_progress is not None:
                on_progress(pct)
        (job.work_dir / "picture.mp4").write_bytes(b"")
        (stems / "mix.wav").write_bytes(b"")
        job.out_dir.mkdir(parents=True, exist_ok=True)
        out = job.out_dir / "short.mp4"
        out.write_bytes(b"")
        return out
