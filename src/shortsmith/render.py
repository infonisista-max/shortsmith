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
-3 dBTP) into `work/stems/voice.wav`. `mux` masters the mix (voice only until 022:
two-pass loudnorm -14 LUFS / -1.5 dBTP less `AAC_HEADROOM_DB` so the encoded file
still meets -1.5 dBTP, then the 0.891 limiter with auto-level off so the target holds)
into `work/stems/mix.wav` and muxes it with the picture stream copied bit-for-bit into
`out/short.mp4` (revision proof (a), 10.1). Stems always sit beside the mix under
`work/stems/`. `render_short` is the whole `rendering` step.

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

from shortsmith import assets, ffmpeg, presenter, styles, subproc
from shortsmith.captions import measure
from shortsmith.contracts import (
    AssetManifest,
    Beat,
    BeatSpec,
    CaptionPageSpec,
    Captions,
    CaptionStyle,
    CardBox,
    CardSpec,
    Crop,
    FinaleCardSpec,
    HookCardsSpec,
    LowerThirdSpec,
    Mode,
    Palette,
    PicturePlan,
    PipGeometry,
    PunchIn,
    RenderSpec,
    Span,
    StampSpec,
    VisualSpec,
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


def broll_numbers(spec: StyleSpec) -> BrollNumbers:
    try:
        motion = spec.broll.motion
        photo, card = motion["photo"], motion["card"]
        stamp, lower, finale = motion["stamp"], motion["lower_third"], motion["finale"]
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
    """The 004 geometry: the style diameter, left at the style edge, bottom touching the
    caption block's top (6.3); the crop window is the largest square of full source
    width anchored at the top, centred horizontally on a landscape source."""
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
        if beat.kind not in ("photo", "card") or record is None:
            continue
        src = str((job_dir / record.file).resolve())
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


def stamp_spec(text: str, *, numbers: StyleNumbers) -> StampSpec:
    """A landed stamp, measured and clamped: inside the style's top
    `broll.stamp_max_y_fraction` of the frame and clear of the platform's right rail."""
    style = numbers.captions
    available = WIDTH - SAFE_RIGHT_PX - SAFE_LEFT
    room = available - 2 * STAMP_PAD_X - 2 * STAMP_BORDER_PX
    font_px = STAMP_FONT_PX
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
) -> RenderSpec:
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
        beats.append(
            BeatSpec(
                id=b.id,
                start_frame=round(b.start * fps),
                end_frame=round(b.end * fps),
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
        pip=fixed_pip(source_size, numbers),
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


def spec_for_job(job: Job, *, numbers: StyleNumbers | None = None) -> RenderSpec:
    """The RenderSpec from the job's files: plan.json, captions.json and the
    presenter cut (`work/cut.mp4`, 005), with the numbers of the job's resolved style
    (`job.json.style`, 008). The short is as long as the cut list."""
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
        source_size=_probe_size(cut),
        duration_s=presenter.total_duration(presenter.cut_list(plan)),
        numbers=numbers,
        manifest=assets.load_manifest(job.path),
        job_dir=job.path,
    )


def _probe_size(path: Path) -> tuple[int, int]:
    for stream in ffmpeg.probe(path)["streams"]:
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    raise RenderError(f"{path.name} has no video stream")


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
    scale to the composition size, constant 30 fps, 4:2:0."""
    crop_w, crop_h, x, y = presenter.crop_window(source_size)
    return (
        f"crop={crop_w}:{crop_h}:{x}:{y},scale={WIDTH}:{HEIGHT}:flags=lanczos,"
        f"fps={FPS},format=yuv420p"
    )


def cut_presenter(job: Job) -> Path:
    """`work/cut.mp4`: the cut list applied to the raw upload, CFR 30 fps H.264 with no
    B-frames, 1080x1920, its audio carried along as AAC."""
    plan = _load_plan(job)
    raw = _raw_path(job)
    if job.record.input is not None:
        source_size = (job.record.input.width, job.record.input.height)
    else:
        source_size = _probe_size(raw)
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


def mux(job: Job) -> Path:
    """`work/stems/mix.wav` (the mastered mix; voice only until 022) and
    `out/short.mp4`: the picture stream copied, the mix as AAC."""
    stems = _stems_dir(job)
    voice = stems / "voice.wav"
    picture = job.work_dir / "picture.mp4"
    for needed in (voice, picture):
        if not needed.is_file():
            raise RenderError(f"{needed.relative_to(job.path).as_posix()} is missing before mux")
    mix = stems / "mix.wav"
    master(voice, mix)
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


def render_short(job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
    """The whole `rendering` step (9.1): cut, voice stem, picture, master and mux."""
    cut_presenter(job)
    voice_stem(job)
    render_picture(job, on_progress=on_progress)
    return mux(job)


# --- the interface the pipeline uses ---------------------------------------------------


class Renderer(ABC):
    """The render engine as the pipeline sees it: the whole `rendering` step from the
    job's plan to `out/short.mp4`. Remotion and ffmpeg are local, not paid, but a
    render costs seconds, so the fake keeps the pipeline and app tests fast; the real
    path is covered by test_render and smoke (12.1)."""

    @abstractmethod
    def render(self, job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        """Write `work/cut.mp4`, `work/stems/*`, `work/picture.mp4` and `out/short.mp4`;
        return the short. `on_progress` gets the picture render's 0-100."""


class RemotionRenderer(Renderer):
    def render(self, job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        return render_short(job, on_progress=on_progress)


class FakeRenderer(Renderer):
    """Builds the same RenderSpec (so a bad plan still fails here), reports 0, 50 and
    100, and writes placeholders for every file the step leaves; none is media."""

    def __init__(self) -> None:
        self.jobs: list[Path] = []

    def render(self, job: Job, *, on_progress: Callable[[int], None] | None = None) -> Path:
        self.jobs.append(job.path)
        cut = _cut_path(job)
        cut.write_bytes(b"")
        plan = _load_plan(job)
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
