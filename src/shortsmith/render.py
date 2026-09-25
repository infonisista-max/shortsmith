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
`broll.card_max_bottom_y`. A rung-4 rescue is drawn as `pip` over the gradient;
other kinds keep their visuals for their own tickets. The engine constants below
(strip, blur, ring) are not style numbers yet.

Set pieces and overlays (ticket 026; decisions 3.2, 3.4, 4.1, 4.2, 6.1, 6.3): every
`BeatSpec` also carries what lands on it, already measured and placed.

- `hook` on the hook-cards beat: the title wrapped into at most two lines of caption
  typography, and the cards of `hook.card_asset_ids` resolved through the manifest's
  aliases into the three reference slots, labelled with the lower-third of the beat
  that sourced them. Fewer than the style's `broll.motion.hook_cards.cards` resolved
  leaves one centred card; none leaves the title alone, never a blank frame.
- `finale` on the finale beat: the presenter cut in a ringed centre circle with the
  same cards around it and the payoff word under them (the references close the loop
  with the hook's faces). The beat's length must sit inside `finale.min_s`-`max_s`
  and no caption page may run into it, or the build fails here rather than on screen.
- `stamp` wherever a beat lands one, or carries a rescue word (4.4): the text measured
  at 92 px, shrunk until it fits, and clamped into the style's top
  `broll.stamp_max_y_fraction` of the frame, clear of the platform's right rail.
- `lower_third` on a beat whose event is one, unless a two-line caption page shows
  over it (6.3) or the beat's own card strip already carries the same text.
- `punch_in` on every `full` beat: the research section 2 push with its grade.

The three remaining tier-1 set pieces (ticket 027; decisions 4.1, 5.2, 5.3, 9.2) are
built the same way, from the beat's own `set_piece_title` and `items`, whose asset ids
resolve through the manifest's aliases exactly as the hook's cards do (an item is a
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

Ticket 029 adds the two overlays: `label_flyin` is the diagram's labels flying in (their
stagger and edges are `infographics.resolve_diagram`'s), and `counter` on a beat whose plan
carries `counter` numbers - the digits of every frame written in
`broll.motion.counter.grouping`, landing in the stamp's time with its shake, in the stamp's
box measured on the widest text it shows (`counter_spec`).

Every number the style front matter carries (the four `broll.motion` rows, the two y
bands, the card count, the stamp palette name, `finale.min_s`/`max_s`) is read from
it; the geometry read off the reference frames stays in the constants below.
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
from functools import cache
from pathlib import Path

from shortsmith import (
    assets,
    ffmpeg,
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
    BadgeSpec,
    Beat,
    BeatSpec,
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
    FinaleCardSpec,
    HookCardsSpec,
    ListRow,
    ListSpec,
    LowerThirdSpec,
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
    TitleWord,
    VisualSpec,
    WallSpec,
)
from shortsmith.jobs import Job
from shortsmith.styles import StyleSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTION_DIR = REPO_ROOT / "src" / "remotion"
DRIVER = REMOTION_DIR / "driver.mjs"
REGISTRY_PATH = REMOTION_DIR / "registry.json"
WIDTH, HEIGHT, FPS = 1080, 1920, 30
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
class BrollNumbers:
    """`broll.motion.*` and the geometry limits of 4.1 / 6.3: the photo and card
    motions, the card's bottom limit, and (026) the stamp, lower-third, hook-card and
    finale motion rows plus the stamp's y band."""

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
    hook_cards: int
    finale_fade_s: float
    # 027: the three set pieces' counts, entry times and (list, wall) base still motion.
    list_items_max: int
    list_reveal_s: float
    list_scale_from: float
    list_scale_to: float
    list_dim: float
    split_panes: int
    split_slide_s: float
    wall_cells_min: int
    wall_cells_max: int
    wall_spring_s: float
    wall_scale_from: float
    wall_scale_to: float
    wall_dim: float
    # 029: the counter's digit grouping; it lands in the stamp's time with its shake.
    counter_grouping: str


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


def broll_numbers(spec: StyleSpec) -> BrollNumbers:
    try:
        motion = spec.broll.motion
        photo, card = motion["photo"], motion["card"]
        stamp, lower, finale = motion["stamp"], motion["lower_third"], motion["finale"]
        rows, split, wall = motion["list"], motion["split"], motion["wall"]
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
            hook_cards=int(motion["hook_cards"]["cards"]),
            finale_fade_s=float(finale["duration_s"]),
            list_items_max=int(rows["items_max"]),
            list_reveal_s=float(rows["duration_s"]),
            list_scale_from=float(rows["scale_from"]),
            list_scale_to=float(rows["scale_to"]),
            list_dim=float(rows["dim"]),
            split_panes=int(split["panes"]),
            split_slide_s=float(split["duration_s"]),
            wall_cells_min=int(wall["cells_min"]),
            wall_cells_max=int(wall["cells_max"]),
            wall_spring_s=float(wall["duration_s"]),
            wall_scale_from=float(wall["scale_from"]),
            wall_scale_to=float(wall["scale_to"]),
            wall_dim=float(wall["dim"]),
            counter_grouping=str(motion["counter"]["grouping"]),
        )
    except KeyError as exc:
        raise styles.StyleError(f"{spec.name}: broll.motion is missing {exc}") from None


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


def card_bottom(visual: VisualSpec) -> float:
    """The lowest y the card reaches over its beat (full push, tilt included)."""
    card = visual.card
    assert card is not None
    return card.top + card.height / 2 + _half_extent(card, max(visual.scale_from, visual.scale_to))


def card_visual(src: str, width: int, height: int, *, strip_text: str, ring: bool, index: int,
                crop: Crop, numbers: StyleNumbers) -> VisualSpec:  # fmt: skip
    """The framed archival card (4.1, 5.3), placed so it ends above the style limit."""
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
    centre = min(b.pip_top - PIP_GAP_PX, b.card_max_bottom_y) - half
    card = card.model_copy(update={"top": centre - outer_h / 2})
    return VisualSpec(
        treatment="card", src=src, width=width, height=height, zoom=crop.zoom,
        focus_x=crop.focus_x, focus_y=crop.focus_y, scale_from=scale_from, scale_to=scale_to,
        pan_px=0.0, card=card,
    )  # fmt: skip


# 4.2: a number or quote beat stamps over the asset already on screen, so its motion
# carries on from the previous beat instead of restarting.
CONTINUING_SUBJECTS = frozenset({"number", "quote"})
# The kinds whose own asset is drawn behind them: the two B-roll treatments, and (027)
# the dimmed base still of a `list` or a `wall`. A `split` fills its card instead.
BASE_STILL_KINDS = frozenset({"photo", "card", "list", "wall"})


def continued(previous: VisualSpec, previous_s: float, own_s: float) -> VisualSpec:
    """`previous` carried on for `own_s` more seconds at the rate it was moving: the
    same framing, the Ken Burns picked up where it stopped, never restarted (4.2)."""
    span = max(previous_s, 1e-6)
    step = (previous.scale_to - previous.scale_from) * own_s / span
    updates: dict[str, object] = {
        "scale_from": previous.scale_to,
        "scale_to": max(1.0, previous.scale_to + step),
        "pan_px": previous.pan_px * own_s / span,
    }
    card = previous.card
    if card is not None:
        cover = (card.cover_scale_to - card.cover_scale_from) * own_s / span
        updates["card"] = card.model_copy(update={
            "cover_scale_from": card.cover_scale_to,
            "cover_scale_to": max(1.0, card.cover_scale_to + cover),
        })  # fmt: skip
    return previous.model_copy(update=updates)


def _visuals(
    plan: PicturePlan, manifest: AssetManifest | None, job_dir: Path | None,
    numbers: StyleNumbers,
) -> dict[str, tuple[Mode, VisualSpec | None]]:  # fmt: skip
    """Per beat id: the mode to draw (a rung-4 rescue becomes `pip`) and its visual."""
    out: dict[str, tuple[Mode, VisualSpec | None]] = {}
    if manifest is None:
        return out
    if job_dir is None:
        raise ValueError("build_spec needs job_dir to resolve the manifest's asset files")
    index = 0
    previous: tuple[Beat, VisualSpec, str] | None = None
    for beat in plan.beats:
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
        if carries_on and previous is not None:
            earlier, visual, _ = previous
            visual = continued(visual, earlier.end - earlier.start, beat.end - beat.start)
        elif decided.treatment == "photo":
            visual = photo_visual(src, record.width, record.height, index=index,
                                  crop=decided.crop, numbers=numbers)  # fmt: skip
        else:
            label = beat.event.text if beat.event.kind == "lower_third" else None
            visual = card_visual(src, record.width, record.height, strip_text=label or "",
                                 ring=beat.event.kind == "ring", index=index,
                                 crop=decided.crop, numbers=numbers)  # fmt: skip
        out[beat.id] = (beat.mode, visual)
        if not carries_on:
            index += 1
        previous = (beat, visual, decided.asset_id)
    return out


# --- set pieces and overlays (ticket 026; decisions 3.4, 4.1, 4.2, 6.3) -----------------
#
# The style front matter carries the durations, the stamp palette name, the hook's card
# count and the two y bands; these constants are the engine's look, like the card
# constants above. The hook and finale geometry is read off the reference frames
# (nkb_02 / nkb_11, dyson_02 / dyson_10), the stamp and punch-in numbers off research
# sections 2 and 3.

SAFE_LEFT = 60.0  # the style's left margin, the caption block's too (6.2)
SAFE_RIGHT_PX = 140.0  # the platform's right rail: nothing lands under it
FONT_STEP_PX = 4  # type shrinks in steps until a measured line fits

HOOK_TITLE_TOP, HOOK_TITLE_FONT_PX, HOOK_TITLE_MAX_LINES = 170.0, 80, 2
HOOK_TITLE_MIN_FONT_PX = 48
HOOK_CARD_IMAGE_W = 402.0  # 430 across with the style's 14 px border
HOOK_IMAGE_MIN_H, HOOK_IMAGE_MAX_H = 300.0, 560.0
HOOK_STRIP_PX, HOOK_STRIP_FONT_PX = 52, 30
HOOK_BAND_TOP = 340.0
HOOK_SECOND_DROP_PX = 100.0  # the right-hand card hangs lower (nkb_02, dyson_02)
HOOK_ROTATES = (-3.0, 4.0, -2.0)
HOOK_SPRING_S, HOOK_STAGGER_S = 0.45, 0.08
HOOK_FLY_SIDE_PX, HOOK_FLY_UP_PX = 900.0, 1200.0  # research S3: from 900 or 1200 px

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


def _wrap(
    words: Sequence[str], *, font_px: int, style: CaptionStyle, max_width: float
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and _measured(trial, font_px=font_px, style=style) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def title_lines(title: str, *, style: CaptionStyle) -> tuple[list[str], int]:
    """The hook title in caption typography, wrapped into at most two lines inside the
    caption width, the type shrinking until it fits (3.4)."""
    words = title.split()
    font_px = HOOK_TITLE_FONT_PX
    while True:
        lines = _wrap(words, font_px=font_px, style=style, max_width=style.max_width_px)
        fits = len(lines) <= HOOK_TITLE_MAX_LINES and all(
            _measured(line, font_px=font_px, style=style) <= style.max_width_px for line in lines
        )
        if fits or font_px <= HOOK_TITLE_MIN_FONT_PX:
            return lines or [""], font_px
        font_px -= FONT_STEP_PX


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


def hook_card_boxes(sources: Sequence[CardSource], *, numbers: StyleNumbers) -> list[CardBox]:
    """The hook's cards placed (3.4): the style's card count in priority order across
    the three reference slots, one centred card when fewer resolved, none when the
    manifest resolved nothing (the title still draws, never a blank frame)."""
    b = numbers.broll
    wanted = min(b.hook_cards, len(HOOK_ROTATES))
    chosen = list(sources[:wanted]) if len(sources) >= wanted else list(sources[:1])
    boxes = [
        _box(s, image_w=HOOK_CARD_IMAGE_W, min_h=HOOK_IMAGE_MIN_H, max_h=HOOK_IMAGE_MAX_H,
             strip_px=HOOK_STRIP_PX, strip_font_px=HOOK_STRIP_FONT_PX,
             border_px=b.card_border_px)  # fmt: skip
        for s in chosen
    ]
    placed: list[CardBox] = []
    for i, box in enumerate(boxes):
        rotate = HOOK_ROTATES[i if len(boxes) > 1 else 2]
        # The lowest the card's centre may sit for its tilted box to end above the limit.
        lowest = b.card_max_bottom_y - _tilt_extent(box.box_width, box.box_height, rotate)
        if len(boxes) == 1:
            centre = min(lowest, max(HOOK_BAND_TOP + box.box_height / 2,
                                     (HOOK_BAND_TOP + b.card_max_bottom_y) / 2))  # fmt: skip
            left = (WIDTH - box.box_width) / 2
            top = centre - box.box_height / 2
            from_x, from_y = 0.0, HOOK_FLY_UP_PX
        elif i == 0:
            left, top = SAFE_LEFT, HOOK_BAND_TOP
            from_x, from_y = -HOOK_FLY_SIDE_PX, 0.0
        elif i == 1:
            left = WIDTH - SAFE_LEFT - box.box_width
            top = HOOK_BAND_TOP + HOOK_SECOND_DROP_PX
            from_x, from_y = HOOK_FLY_SIDE_PX, 0.0
        else:
            left = (WIDTH - box.box_width) / 2
            top = lowest - box.box_height / 2
            from_x, from_y = 0.0, HOOK_FLY_UP_PX
        placed.append(box.model_copy(update={
            "left": left, "top": top, "rotate_deg": rotate,
            "from_x": from_x, "from_y": from_y, "delay_s": i * HOOK_STAGGER_S,
        }))  # fmt: skip
    return placed


def hook_spec(title: str, sources: Sequence[CardSource], *, numbers: StyleNumbers) -> HookCardsSpec:
    lines, font_px = title_lines(title, style=numbers.captions)
    return HookCardsSpec(
        title_lines=lines,
        title_font_px=font_px,
        title_top=HOOK_TITLE_TOP,
        title_line_px=font_px * numbers.captions.line_height,
        title_color="#FFFFFF",
        cards=hook_card_boxes(sources, numbers=numbers),
        spring_s=HOOK_SPRING_S,
    )


def finale_card_boxes(sources: Sequence[CardSource], *, numbers: StyleNumbers) -> list[CardBox]:
    """The hook's cards again, around the finale circle (the references close the loop
    with the same faces)."""
    border = numbers.broll.card_border_px
    boxes = [
        _box(s, image_w=FINALE_CARD_IMAGE_W, min_h=FINALE_IMAGE_MIN_H, max_h=FINALE_IMAGE_MAX_H,
             strip_px=0, strip_font_px=0, border_px=border)  # fmt: skip
        for s in sources[: len(FINALE_SLOT_TOPS)]
    ]
    def left_of(slot: int, width: float) -> float:
        """Top centre, then the left and right shoulders of the circle (dyson_10)."""
        if slot == 0:
            return (WIDTH - width) / 2
        return SAFE_LEFT if slot == 1 else WIDTH - SAFE_LEFT - width

    return [
        box.model_copy(update={
            "left": left_of(i, box.box_width), "top": FINALE_SLOT_TOPS[i],
            "rotate_deg": FINALE_ROTATES[i], "delay_s": i * HOOK_STAGGER_S,
            "from_y": HOOK_FLY_UP_PX if i == 0 else 0.0,
            "from_x": 0.0 if i == 0 else (-HOOK_FLY_SIDE_PX if i == 1 else HOOK_FLY_SIDE_PX),
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


def card_sources(
    plan: PicturePlan, manifest: AssetManifest | None, job_dir: Path | None
) -> list[CardSource]:
    """The hook's planned card ids resolved through the manifest's aliases, once each,
    labelled with the lower-third the beat that sourced them carries."""
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
    seen: set[str] = set()
    for planned in plan.hook.card_asset_ids:
        asset_id = manifest.aliases.get(planned, planned)
        if asset_id is None or asset_id in seen:
            continue
        record = manifest.asset(asset_id)
        if record is None:
            continue
        seen.add(asset_id)
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


def split_spec(title: str, items: Sequence[ItemSource], badge: CardSource | None, *,
               numbers: StyleNumbers) -> SplitSpec:  # fmt: skip
    """The `split` news-card composite (5.2): the style's `broll.motion.split.panes`
    panes side by side in one framed card above the PIP, the badge overlapping its
    top-left corner inside the safe box, and the title strip under them."""
    b, style = numbers.broll, numbers.captions
    # A pane the asset step rescued has no picture; it is left out, never drawn blank.
    panes_wanted = [p for p in items[: b.split_panes] if p.card is not None]
    border = b.card_border_px
    inner = SPLIT_CARD_W - 2 * border
    pane_w = (inner - SPLIT_SEAM_PX * (len(panes_wanted) - 1)) / max(1, len(panes_wanted))
    pane_h = pane_w * SPLIT_PANE_ASPECT
    labelled = any(p.text for p in panes_wanted)
    label_px = SPLIT_LABEL_PX if labelled else 0
    height = pane_h + label_px + 2 * border + SPLIT_TITLE_PX
    left = (WIDTH - SPLIT_CARD_W) / 2
    half = _tilt_extent(SPLIT_CARD_W, height, b.card_rotate_deg)
    top = min(b.pip_top - PIP_GAP_PX, b.card_max_bottom_y) - half - height / 2
    panes: list[SplitPane] = []
    for i, p in enumerate(panes_wanted):
        assert p.card is not None
        panes.append(
            SplitPane(
                src=p.card.src, width=p.card.width, height=p.card.height,
                left=border + i * (pane_w + SPLIT_SEAM_PX), top=float(border),
                pane_width=pane_w, pane_height=pane_h + label_px, label=p.text,
                from_x=0.0 if i == 0 else SPLIT_CARD_W,
            )  # fmt: skip
        )
    font_px = _fitted(title, font_px=SPLIT_TITLE_FONT_PX, min_font_px=SPLIT_TITLE_MIN_FONT_PX,
                      style=style, room=WIDTH - 2 * SAFE_LEFT)  # fmt: skip
    return SplitSpec(
        left=left, top=top, width=SPLIT_CARD_W, height=height, border_px=border,
        rotate_deg=b.card_rotate_deg, seam_px=SPLIT_SEAM_PX, panes=panes,
        label_px=label_px, label_font_px=SPLIT_LABEL_FONT_PX, title_px=SPLIT_TITLE_PX,
        title_font_px=font_px, title_color="#FFFFFF",
        title_words=title_words(title, [p.text for p in panes_wanted], font_px=font_px,
                                style=style),  # fmt: skip
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
    beat: Beat, manifest: AssetManifest | None, job_dir: Path | None, *, numbers: StyleNumbers
) -> tuple[ListSpec | None, SplitSpec | None, WallSpec | None]:
    """The `list`, `split` or `wall` this beat draws, already measured and placed."""
    if beat.kind not in ("list", "split", "wall"):
        return None, None, None
    items = item_sources(beat, manifest, job_dir)
    if beat.kind == "list":
        return list_spec(beat.set_piece_title, items, numbers=numbers), None, None
    if beat.kind == "split":
        badge = badge_source(beat, manifest, job_dir)
        return None, split_spec(beat.set_piece_title, items, badge, numbers=numbers), None
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
) -> RenderSpec:
    """`pip` is the measured geometry from `job.json.presenter` (013); None falls back
    to `fixed_pip`."""
    numbers = numbers or style_numbers(styles.DEFAULT)
    frames = round(duration_s * fps)
    visuals = _visuals(plan, manifest, job_dir, numbers)
    finale_beat = _check_finale(plan, captions, numbers)
    sources = card_sources(plan, manifest, job_dir)
    two_lines = set(captions.beats_with_two_lines)
    beats: list[BeatSpec] = []
    for b in plan.beats:
        mode, visual = visuals.get(b.id, (b.mode, None))
        stamp = _stamp_text(b, manifest)
        labelled = visual is not None and visual.card is not None and visual.card.strip_px > 0
        label = b.event.text if b.event.kind == "lower_third" and b.event.text else None
        rows, split, wall = set_piece(b, manifest, job_dir, numbers=numbers)
        chart, diagram = infographic(b, manifest, job_dir, numbers=numbers)
        start_frame, end_frame = round(b.start * fps), round(b.end * fps)
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
                stamp=stamp_spec(stamp, numbers=numbers) if stamp else None,
                lower_third=(
                    lower_third_spec(label, numbers=numbers)
                    if label and not labelled and b.id not in two_lines
                    else None
                ),
                hook=(
                    hook_spec(plan.hook.title, sources, numbers=numbers)
                    if b.kind == "hook_cards"
                    else None
                ),
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
                counter=(
                    counter_spec(b.counter, frames=end_frame - start_frame, fps=fps,
                                 numbers=numbers)  # fmt: skip
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
        pip=pip or fixed_pip(source_size, numbers),
        palette=numbers.palette,
        caption_style=numbers.captions,
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


def spec_for_job(job: Job, *, numbers: StyleNumbers | None = None) -> RenderSpec:
    """The RenderSpec from the job's files: plan.json, captions.json, the presenter cut
    (`work/cut.mp4`, 005) and the measured PIP geometry (`job.json.presenter`, 013),
    with the numbers of the job's resolved style (`job.json.style`, 008). The short is
    as long as the cut list."""
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
    )


def render_picture(job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
    """The `rendering` step's picture half: `work/picture.mp4`, silent H.264."""
    spec = spec_for_job(job)
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
) -> sound.MixResult | None:
    """The 022 sound director over the job's plan and sound story: the music and SFX
    stems beside the voice, and the premix the master is cut from. None when there is
    nothing to mix - an empty catalogue, or a job planned before the sound call (the
    renderer's own tests) - and the short is then the voice alone, as it was before 022.
    `search` is the 7.2 audio search the director asks under the bed-score threshold
    (024); None means no search is configured."""
    library = library if library is not None else sound.load_catalogue()
    story = _load_story(job)
    if not library.entries or story is None:
        return None
    plan = _load_plan(job)
    result = sound.build_mix(
        stems=_stems_dir(job),
        voice=_stems_dir(job) / "voice.wav",
        plan=plan,
        story=story,
        nums=loaded_styles()[job.record.style].sound,
        library=library,
        runtime_s=presenter.total_duration(presenter.cut_list(plan)),
        search=search,
        counter_land_s=counter_land_s(loaded_styles()[job.record.style]),
    )
    jobs.note(job, result.summary())
    return result


def counter_land_s(spec: StyleSpec) -> float | None:
    """How long a counter takes to land (029): the stamp's `duration_s`, so the sound
    director fires its hit where the picture lands it. None on a spec with no stamp row."""
    land = spec.broll.motion.get("stamp", {}).get("duration_s")
    return float(land) if land is not None else None


def _audio_rights(job: Job, result: sound.MixResult | None, library: sound.Library) -> None:
    """5.4 / 016: the music and SFX rows are written where `rights.write` will pick them
    up, then the log is regenerated, so they sit beside the asset rows and survive a
    re-run of the asset step."""
    rows = sound.rights_rows(result, library) if result is not None else []
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
    result = sound_mix(job, library=library, search=search)
    mix = stems / "mix.wav"
    master(result.premix if result is not None else voice, mix)
    _audio_rights(job, result, library)
    job.out_dir.mkdir(parents=True, exist_ok=True)
    out = job.out_dir / "short.mp4"
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
) -> Path:
    """The whole `rendering` step (9.1): cut, voice stem, picture, sound and mux."""
    cut_presenter(job)
    voice_stem(job)
    render_picture(job, on_progress=on_progress)
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
    call stays the same with or without one."""

    def __init__(self, *, search: sound.AudioSearch | None = None) -> None:
        self._search = search

    def render(
        self,
        job: Job,
        *,
        on_progress: Callable[[int], None] | None = None,
        library: sound.Library | None = None,
    ) -> Path:
        return render_short(job, on_progress=on_progress, library=library, search=self._search)


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
