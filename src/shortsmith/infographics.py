"""Charts and labelled diagrams (PRD `infographics`; ticket 021, decisions 9.2, 9.3, 5.5).

The two infographic kinds that are drawn rather than found. Both are measured and
placed here, in Python, and animated by the `chart` and `infographic` components: the
same division of labour as the set pieces of 026 / 027.

- `resolve_chart(recipe, numbers=...)` lays out a `bar`, a `line` or a two-value
  `comparison` from the planner's `series`: the axes scale to the real numbers (the
  largest value fills the plot), every value is formatted in the style's grouping and
  decimals, the columns are spread across the plot box inside the safe area, the axis
  labels sit under the baseline outside the plot, and the title strip sits above it.
  An empty, one-point, over-long, negative or all-zero series is refused with
  `InfographicError`: a chart that drops or invents a data point lies about the data.
- `resolve_diagram(recipe, asset, numbers=...)` maps the planner's percentage label
  positions onto the base picture as it is drawn - the whole frame for a full-bleed
  base, a boxed card above the style's `broll.card_max_bottom_y` otherwise - and
  refuses a label whose box would leave the safe area (decision 9.3's promise that a
  label is readable on a phone). Labels past the style's `labels_max` are cut, not
  refused: losing a label is not a false statement. Ticket 029 flies the labels in one
  after another (`label_flyin`): each from the frame edge nearest its box, on a stagger
  from the beat's length (`label_stagger`), so the last one has landed early enough in
  the beat to be read.
- `counter_texts` is the `counter` overlay's digits, one string per frame (029): easing
  from the plan's start value to its target and holding the target through the landing,
  every value written in the style's digit grouping with the plan's decimals and unit.
- `resolve_map(recipe, geocoder=...)` (ticket 020, 9.3) is the map composed in code:
  the region (a name the geocoder answers with a bbox, or the plan's own bbox) widened
  to hold every marker and route point, padded by the style's `padding` and fitted
  into the band with the Mercator maths in `geo`; the bundled Natural Earth land, coast
  and borders projected, clipped to the frame and written as SVG paths; every marker at
  the coordinate the geocoder gave its name (the plan's own lat/lon are never read),
  its label pill (the name as the planner wrote it) beside the dot inside the safe area,
  flipped or stepped clear of every other pill and dot (072); the route as pixels. A name the
  geocoder does not know is `InfographicError` naming it - a marker is never placed by
  a guess. Ticket 028 animates it: the beat's `pin_drop`, `route_arrow` and
  `object_path` overlays switch the three motions on, `map_timeline` shares the beat
  between them in that order from its length, and `route_segments` turns the route
  polyline into legs with the tangent heading the arrowhead and the moving object
  follow. Every pixel still comes from the layout; the planner names places only.

The base picture is always label-free: `assets.generate` appends "no text, no labels"
to a diagram base's prompt (5.5) and the asset step marks the asset as a diagram base,
so it is never shown as a bare photo.

Every count, duration and number format comes from the style front matter
(`broll.motion.chart`, `broll.motion.infographic`, the palette and the caption
typography); the geometry below is this engine's look, as in `render`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from shortsmith import geo, styles
from shortsmith.captions import measure
from shortsmith.contracts import (
    Beat,
    CaptionStyle,
    ChartForm,
    ChartLayout,
    ChartMark,
    Crop,
    DiagramLabel,
    DiagramLayout,
    MapLayout,
    MapMarkerLayout,
    MapObject,
    OverlayKind,
    Palette,
    PlanLabel,
    RouteSegment,
    SeriesPoint,
    Treatment,
)
from shortsmith.geo import GeocodeError, Geocoder, Place
from shortsmith.safe_area import HEIGHT, SAFE_LEFT, SAFE_RIGHT_PX, SAFE_TOP_PX, WIDTH
from shortsmith.styles import StyleSpec

__all__ = ["Geocoder", "GeocodeError", "Place"]  # the interface, re-exported from `geo`

# The composition's frame and the margins nothing lands under (6.2 left margin, the
# platform's right rail and top zone) are `safe_area`'s, the renderer's and the gate's
# too (067).
FONT_STEP_PX = 4

# The chart's look, read off the reference frames' stat cards (nkb_07, dyson_07).
CHART_TITLE_TOP, CHART_TITLE_FONT_PX, CHART_TITLE_MIN_FONT_PX = 250.0, 64, 40
CHART_BAND_TOP = 400.0
CHART_LABEL_FONT_PX, CHART_LABEL_MIN_FONT_PX = 36, 22
CHART_LABEL_GAP_PX = 18.0
CHART_VALUE_FONT_PX = 44
CHART_VALUE_GAP_PX = 14.0  # the value label rides this far above the bar or dot
CHART_BAR_FRACTION = 0.56  # of its column; a comparison's two bars are wider
CHART_COMPARISON_FRACTION = 0.72
CHART_DOT_PX = 20
CHART_BASELINE_PX = 4
CHART_STAGGER_S = 0.1
CHART_MARK_FILL = "rgba(255,255,255,0.82)"
CHART_AXIS_COLOR = "rgba(255,255,255,0.45)"

# The diagram's look: the base's box when it is not full-bleed, and the label pills.
DIAGRAM_BAND_TOP = 330.0
DIAGRAM_LABEL_FONT_PX, DIAGRAM_LABEL_MIN_FONT_PX = 40, 26
DIAGRAM_LABEL_PAD_X, DIAGRAM_LABEL_PAD_Y = 22.0, 12.0
DIAGRAM_LABEL_FILL, DIAGRAM_LABEL_RADIUS_PX = "rgba(17,17,17,0.78)", 14
# 029: the labels share the first part of the beat, one after another, so the last one
# has landed while there is still time to read it; a long beat never drips them slower
# than the ceiling.
LABELS_IN_FRACTION = 0.6
LABEL_STAGGER_MAX_S = 0.3

# The map's look (020): the marker dot with its pale ring, the label pill beside it in
# the diagram's pill style, the frame the base is clipped to (a margin past the edges so
# a stroke never ends visibly at the frame), and the spans a name without a bbox gets.
MAP_LABEL_FONT_PX, MAP_LABEL_MIN_FONT_PX = 36, 24
MAP_LABEL_PAD_X, MAP_LABEL_PAD_Y = 16.0, 8.0
MAP_LABEL_GAP_PX = 12.0
MAP_DOT_PX, MAP_RING_PX = 22, 4
MAP_CLIP_MARGIN_PX = 60.0
CITY_SPAN_DEG = 3.0  # a region that is a point (a city) shows this many degrees across
MIN_SPAN_DEG = 1.0  # a crop is never narrower than this in either axis

# 028: the map's three animations share the first `MOTIONS_IN_FRACTION` of the beat in
# order - the pins drop, the route draws on, the object travels - so the last one has
# landed while there is still time to read the map. Each phase has a ceiling a long beat
# never exceeds; a short beat scales every phase by the one factor that fits the window,
# so the order and the proportions hold at any length (the same rule as the labels).
MOTIONS_IN_FRACTION = 0.8
PIN_STAGGER_MAX_S = 0.2  # between one pin's drop and the next
PIN_DROP_MAX_S = 0.3  # the fall and the spring settle
LABEL_POP_MAX_S = 0.2  # the label pill growing in once its pin has landed
ROUTE_DRAW_MAX_S = 0.8
OBJECT_TRAVEL_MAX_S = 1.5
PIN_DROP_PX = 140.0  # a pin falls this far onto its point
ROUTE_PX = 6.0  # the route's stroke
ARROW_PX = 28.0  # the arrowhead's length
OBJECT_PX = 64.0  # the sprite's box


class InfographicError(ValueError):
    """The recipe cannot be drawn: a series that is empty or does not match its form, or
    a label that would land outside the safe area. The message carries the numbers."""


class LayoutError(InfographicError):
    """072: a map label that no flip or step can place clear of every other pill and dot
    inside the safe area. The message names the marker and the others on the map."""


# --- the style numbers (decision 1.2) ---------------------------------------------------


@dataclass(frozen=True)
class ChartNumbers:
    """`broll.motion.chart`: how many marks a chart may have, how long it draws on, and
    how its numbers are written."""

    marks_max: int
    draw_s: float
    decimals: int
    grouping: str


@dataclass(frozen=True)
class DiagramNumbers:
    """`broll.motion.infographic`: the label count, the fly-in time, the base still's
    Ken Burns and its scrim, plus the y the base may not pass."""

    labels_max: int
    fly_s: float
    scale_from: float
    scale_to: float
    dim: float
    max_bottom_y: int


@dataclass(frozen=True)
class MapNumbers:
    """`broll.motion.map` (020): the marker cap, the base's fade-in, the crop padding
    as a fraction of the region's span, and the base colours and stroke widths (the
    marker takes the palette accent), plus the y the band may not pass."""

    markers_max: int
    draw_s: float
    padding: float
    land: str
    coast: str
    border: str
    coast_px: float
    border_px: float
    max_bottom_y: int
    # 072: how far a pill that covers another pill or dot steps up or down, how many times
    label_step_px: float
    label_steps_max: int


@dataclass(frozen=True)
class InfographicNumbers:
    """Everything the three resolvers read from a loaded style spec."""

    chart: ChartNumbers
    diagram: DiagramNumbers
    map: MapNumbers
    palette: Palette
    captions: CaptionStyle


def numbers_for(spec: StyleSpec) -> InfographicNumbers:
    """The `chart`, `infographic` and `map` rows of `broll.motion` with the palette and
    the caption typography; a missing key names the spec, as `render.broll_numbers` does."""
    try:
        chart, diagram = spec.broll.motion["chart"], spec.broll.motion["infographic"]
        map_row = spec.broll.motion["map"]
        return InfographicNumbers(
            chart=ChartNumbers(
                marks_max=int(chart["marks_max"]),
                draw_s=float(chart["duration_s"]),
                decimals=int(chart["decimals"]),
                grouping=str(chart["grouping"]),
            ),
            diagram=DiagramNumbers(
                labels_max=int(diagram["labels_max"]),
                fly_s=float(diagram["duration_s"]),
                scale_from=float(diagram["scale_from"]),
                scale_to=float(diagram["scale_to"]),
                dim=float(diagram["dim"]),
                max_bottom_y=spec.broll.card_max_bottom_y,
            ),
            map=MapNumbers(
                markers_max=int(map_row["markers_max"]),
                draw_s=float(map_row["duration_s"]),
                padding=float(map_row["padding"]),
                land=str(map_row["land"]),
                coast=str(map_row["coast"]),
                border=str(map_row["border"]),
                coast_px=float(map_row["coast_px"]),
                border_px=float(map_row["border_px"]),
                max_bottom_y=spec.broll.card_max_bottom_y,
                label_step_px=float(map_row["label_step_px"]),
                label_steps_max=int(map_row["label_steps_max"]),
            ),
            palette=spec.palette,
            captions=spec.caption_style(),
        )
    except KeyError as exc:
        raise styles.StyleError(f"{spec.name}: broll.motion is missing {exc}") from None


# --- number formatting (9.2: the style writes the numbers, not the code) ---------------


def _grouped(digits: str, grouping: str) -> str:
    """`1234567` in the style's grouping: Indian lakh/crore, Western thousands, or
    plain. An unknown name is plain, so a style can switch it off."""
    if grouping == "plain" or len(digits) <= 3:
        return digits
    if grouping == "western":
        head, tail = digits[:-3], digits[-3:]
        parts: list[str] = []
        while head:
            parts.insert(0, head[-3:])
            head = head[:-3]
        return ",".join([*parts, tail])
    if grouping != "indian":
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while head:
        parts.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([*parts, tail])


def format_value(value: float, *, decimals: int, grouping: str) -> str:
    """One series value as the style writes it: rounded to `decimals` and grouped."""
    text = f"{abs(value):.{decimals}f}"
    whole, _, fraction = text.partition(".")
    out = _grouped(whole, grouping) + (f".{fraction}" if fraction else "")
    return f"-{out}" if value < 0 else out


def with_unit(text: str, unit: str) -> str:
    """The value plus the beat's unit: a symbol sits against the number, a word after a
    space ("40%", "12,00,000 crore")."""
    unit = unit.strip()
    if not unit:
        return text
    return f"{text}{unit}" if not unit[0].isalnum() else f"{text} {unit}"


def counter_texts(
    start: float, target: float, *, frames: int, land_frames: int, decimals: int,
    grouping: str, unit: str,
) -> list[str]:  # fmt: skip
    """The `counter` overlay's text on each frame of its beat (029, 9.2): the value eases
    out from `start` to `target` over the frames before the landing, then holds the
    target through the last `land_frames`, where it lands with the stamp's shake. Every
    value is written as the chart's are: the plan's decimals, the style's grouping."""
    counting = max(1, frames - land_frames)
    out: list[str] = []
    for frame in range(frames):
        progress = min(1.0, frame / max(1, counting - 1))
        eased = 1.0 - (1.0 - progress) ** 3
        value = start + (target - start) * eased
        out.append(with_unit(format_value(value, decimals=decimals, grouping=grouping), unit))
    return out


# --- measuring text (the same bundled fonts the pager uses) ----------------------------


def _measured(text: str, *, font_px: int, style: CaptionStyle, weight: int | None = None) -> float:
    return measure(
        text,
        family=style.font_family,
        weight=weight if weight is not None else style.font_weight,
        size_px=font_px,
        letter_spacing_px=style.letter_spacing_px,
    )


def _fitted(text: str, *, font_px: int, min_font_px: int, style: CaptionStyle,
            room: float) -> int:  # fmt: skip
    while font_px > min_font_px and _measured(text, font_px=font_px, style=style) > room:
        font_px -= FONT_STEP_PX
    return font_px


# --- charts (9.2) ----------------------------------------------------------------------


@dataclass(frozen=True)
class ChartRecipe:
    """What a `chart` beat asks for: the form, the series, the title strip's words and
    the unit its values are written in."""

    form: ChartForm
    series: tuple[SeriesPoint, ...] = ()
    title: str = ""
    unit: str = ""


def chart_recipe(beat: Beat) -> ChartRecipe:
    """A `chart` beat as a recipe; the grammar has already checked the fields exist."""
    if beat.chart_form is None:
        raise InfographicError(f"{beat.id}: a chart beat has no chart_form (9.2)")
    return ChartRecipe(
        form=beat.chart_form,
        series=tuple(beat.series),
        title=beat.set_piece_title,
        unit=beat.value_unit,
    )


def _check_series(recipe: ChartRecipe, numbers: ChartNumbers) -> list[SeriesPoint]:
    """The series as it will be drawn, or `InfographicError` with the numbers: a chart
    never drops, invents or guesses a data point."""
    series = list(recipe.series)
    if not series:
        raise InfographicError(f"a {recipe.form} chart has an empty series (9.2)")
    if recipe.form == "comparison" and len(series) != 2:
        raise InfographicError(
            f"a comparison chart has {len(series)} values; it draws exactly two (9.2)"
        )
    if len(series) < 2:
        raise InfographicError(
            f"a {recipe.form} chart has {len(series)} value; it needs at least two (9.2)"
        )
    if len(series) > numbers.marks_max:
        raise InfographicError(
            f"a {recipe.form} chart has {len(series)} values, over "
            f"broll.motion.chart.marks_max {numbers.marks_max}"
        )
    for point in series:
        if not point.label.strip():
            raise InfographicError(f"the chart value {point.value:g} has no axis label (9.2)")
        if point.value < 0:
            raise InfographicError(
                f"the chart value {point.label!r} is negative ({point.value:g}); "
                "v1 charts draw non-negative series only (9.2)"
            )
    if max(p.value for p in series) <= 0:
        raise InfographicError("every chart value is zero: there is no scale to draw (9.2)")
    return series


def resolve_chart(recipe: ChartRecipe, *, numbers: InfographicNumbers) -> ChartLayout:
    """The chart laid out in composition pixels (9.2): the plot inside the safe box and
    above the style's `broll.card_max_bottom_y`, the largest value filling the plot."""
    style, chart_numbers = numbers.captions, numbers.chart
    series = _check_series(recipe, chart_numbers)
    plot_left = SAFE_LEFT
    plot_width = WIDTH - 2 * SAFE_LEFT
    label_room = CHART_LABEL_GAP_PX + CHART_LABEL_FONT_PX
    plot_top = CHART_BAND_TOP + CHART_VALUE_FONT_PX + CHART_VALUE_GAP_PX
    baseline_y = numbers.diagram.max_bottom_y - label_room
    plot_height = baseline_y - plot_top
    column = plot_width / len(series)
    fraction = (
        CHART_COMPARISON_FRACTION if recipe.form == "comparison" else CHART_BAR_FRACTION
    )
    bar_width = column * fraction
    dot = float(CHART_DOT_PX)
    top_value = max(p.value for p in series)
    biggest = max(range(len(series)), key=lambda i: series[i].value)
    accent = numbers.palette.accent
    marks: list[ChartMark] = []
    for i, point in enumerate(series):
        left = plot_left + i * column
        reach = plot_height * point.value / top_value
        point_x = left + column / 2
        point_y = baseline_y - reach
        if recipe.form == "line":
            box_left, box_top, box_w, box_h = point_x - dot / 2, point_y - dot / 2, dot, dot
        else:
            box_left, box_top, box_w, box_h = left + (column - bar_width) / 2, point_y, \
                bar_width, reach  # fmt: skip
        if recipe.form == "comparison":
            color = accent if i == 0 else CHART_MARK_FILL
        else:
            color = accent if i == biggest else CHART_MARK_FILL
        marks.append(
            ChartMark(
                label=point.label,
                value=point.value,
                value_text=with_unit(
                    format_value(
                        point.value,
                        decimals=chart_numbers.decimals,
                        grouping=chart_numbers.grouping,
                    ),
                    recipe.unit,
                ),
                left=left,
                width=column,
                bar_left=box_left,
                bar_top=box_top,
                bar_width=box_w,
                bar_height=box_h,
                point_x=point_x,
                point_y=point_y,
                color=color,
                delay_s=i * CHART_STAGGER_S,
            )
        )
    title_px = _fitted(recipe.title, font_px=CHART_TITLE_FONT_PX, style=style,
                       min_font_px=CHART_TITLE_MIN_FONT_PX, room=plot_width)  # fmt: skip
    label_px = min(
        _fitted(p.label, font_px=CHART_LABEL_FONT_PX, min_font_px=CHART_LABEL_MIN_FONT_PX,
                style=style, room=column)  # fmt: skip
        for p in series
    )
    return ChartLayout(
        form=recipe.form,
        title=recipe.title,
        title_font_px=title_px,
        title_top=CHART_TITLE_TOP,
        title_color=accent,
        plot_left=plot_left,
        plot_top=plot_top,
        plot_width=plot_width,
        plot_height=plot_height,
        baseline_y=baseline_y,
        baseline_px=CHART_BASELINE_PX,
        axis_color=CHART_AXIS_COLOR,
        label_top=baseline_y + CHART_LABEL_GAP_PX,
        label_font_px=label_px,
        value_font_px=CHART_VALUE_FONT_PX,
        dot_px=CHART_DOT_PX,
        marks=marks,
        grow_s=chart_numbers.draw_s,
    )


# --- labelled diagrams (9.2, 9.3, 5.5) ------------------------------------------------


@dataclass(frozen=True)
class DiagramRecipe:
    """What an `infographic` beat asks for: the labels, in the order they fly in."""

    labels: tuple[PlanLabel, ...] = ()


def diagram_recipe(beat: Beat) -> DiagramRecipe:
    return DiagramRecipe(labels=tuple(beat.labels))


@dataclass(frozen=True)
class DiagramAsset:
    """The base picture as the asset step classified it (5.3): a `photo` fills the
    frame, anything else is boxed like a card."""

    src: str
    width: int
    height: int
    treatment: Treatment = "photo"
    crop: Crop = field(default_factory=Crop)


Box = tuple[float, float, float, float]


def diagram_box(asset: DiagramAsset, *, numbers: DiagramNumbers) -> Box:
    """(left, top, width, height) of the base as drawn: the whole frame when it is
    full-bleed, else the widest box of its own aspect inside the safe box and above the
    style's `broll.card_max_bottom_y`."""
    if asset.treatment == "photo":
        return 0.0, 0.0, float(WIDTH), float(HEIGHT)
    box_w = WIDTH - 2 * SAFE_LEFT
    band = numbers.max_bottom_y - DIAGRAM_BAND_TOP
    box_h = min(band, box_w * asset.height / max(1, asset.width))
    box_w = min(box_w, box_h * asset.width / max(1, asset.height))
    top = DIAGRAM_BAND_TOP + (band - box_h) / 2
    return (WIDTH - box_w) / 2, top, box_w, box_h


def label_stagger(count: int, *, length_s: float, fly_s: float) -> tuple[float, float]:
    """(stagger, fly time) for `count` labels on a beat of `length_s` (029): they share
    the first `LABELS_IN_FRACTION` of the beat, one after another, never more than
    `LABEL_STAGGER_MAX_S` apart. The style's `fly_s` holds where the beat has room; a
    short beat flies them faster rather than landing the last one as the beat cuts."""
    window = length_s * LABELS_IN_FRACTION
    if count <= 1:
        return 0.0, min(fly_s, window)
    stagger = min(LABEL_STAGGER_MAX_S, window / count)
    return stagger, min(fly_s, window - (count - 1) * stagger)


def fly_from(left: float, top: float, width: float, height: float) -> tuple[float, float]:
    """The offset that puts a label box just past the frame edge nearest it (029): the
    fly-in starts there and springs back to the anchored position."""
    edges = [
        (left, (-(left + width), 0.0)),
        (WIDTH - (left + width), (WIDTH - left, 0.0)),
        (top, (0.0, -(top + height))),
        (HEIGHT - (top + height), (0.0, HEIGHT - top)),
    ]
    return min(edges, key=lambda edge: edge[0])[1]


def resolve_diagram(
    recipe: DiagramRecipe, asset: DiagramAsset, *, numbers: InfographicNumbers,
    length_s: float,
) -> DiagramLayout:  # fmt: skip
    """The labelled diagram (9.3): the planner's percentages mapped onto the base as it
    is drawn, each label pilled and measured, every box inside the safe area, each one
    flying in from its nearest edge on the beat's stagger (029)."""
    style, d = numbers.captions, numbers.diagram
    left, top, box_w, box_h = diagram_box(asset, numbers=d)
    room = WIDTH - SAFE_RIGHT_PX - SAFE_LEFT
    planned_labels = recipe.labels[: d.labels_max]
    stagger, fly_s = label_stagger(len(planned_labels), length_s=length_s, fly_s=d.fly_s)
    labels: list[DiagramLabel] = []
    for i, planned in enumerate(planned_labels):
        font_px = _fitted(planned.text, font_px=DIAGRAM_LABEL_FONT_PX, style=style,
                          min_font_px=DIAGRAM_LABEL_MIN_FONT_PX, room=room)  # fmt: skip
        width = _measured(planned.text, font_px=font_px, style=style) + 2 * DIAGRAM_LABEL_PAD_X
        height = font_px * style.line_height + 2 * DIAGRAM_LABEL_PAD_Y
        x = left + box_w * planned.x / 100
        y = top + box_h * planned.y / 100
        box_left = {"left": x, "center": x - width / 2, "right": x - width}[planned.anchor]
        box_top = y - height / 2
        _check_inside(planned, box_left, box_top, width, height, numbers=d)
        from_x, from_y = fly_from(box_left, box_top, width, height)
        labels.append(
            DiagramLabel(
                text=planned.text, left=box_left, top=box_top, width=width, height=height,
                font_px=font_px, anchor=planned.anchor, delay_s=i * stagger,
                from_x=from_x, from_y=from_y,
            )  # fmt: skip
        )
    return DiagramLayout(
        src=asset.src, width=asset.width, height=asset.height, left=left, top=top,
        box_width=box_w, box_height=box_h, zoom=asset.crop.zoom, focus_x=asset.crop.focus_x,
        focus_y=asset.crop.focus_y, scale_from=d.scale_from, scale_to=d.scale_to, dim=d.dim,
        labels=labels, fill=DIAGRAM_LABEL_FILL, radius_px=DIAGRAM_LABEL_RADIUS_PX,
        text_color="#FFFFFF", fly_s=fly_s,
    )  # fmt: skip


def _check_inside(
    planned: PlanLabel, left: float, top: float, width: float, height: float, *,
    numbers: DiagramNumbers,
) -> None:  # fmt: skip
    """9.3: a label the viewer could not read is a build failure, not a clamp - the
    plan asked for it in a place the frame does not have."""
    right, bottom = left + width, top + height
    inside = (
        left >= SAFE_LEFT - 1e-6
        and right <= WIDTH - SAFE_RIGHT_PX + 1e-6
        and top >= SAFE_TOP_PX - 1e-6
        and bottom <= numbers.max_bottom_y + 1e-6
    )
    if not inside:
        raise InfographicError(
            f"the label {planned.text!r} at {planned.x:g}% x {planned.y:g}% draws at "
            f"({left:.0f}, {top:.0f}) to ({right:.0f}, {bottom:.0f}), outside the safe area "
            f"x {SAFE_LEFT:g}-{WIDTH - SAFE_RIGHT_PX:g}, y {SAFE_TOP_PX:g}-{numbers.max_bottom_y}"
        )


# --- maps (9.3, 12.1; ticket 020) ---------------------------------------------------------


@dataclass(frozen=True)
class MapMarkerRecipe:
    """A marker by name. The plan's `lat` / `lon` ride along and are never read (9.3)."""

    name: str
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class MapRecipe:
    """What a `map` beat asks for: the region by name or a bbox (west, south, east,
    north), the markers, the route as names in order, the object that travels it."""

    region: str = ""
    bbox: geo.BBox | None = None
    markers: tuple[MapMarkerRecipe, ...] = ()
    route: tuple[str, ...] = ()
    object: MapObject | None = None


def map_recipe(beat: Beat) -> MapRecipe:
    """A `map` beat as a recipe; the grammar has already checked the shape."""
    if beat.map is None:
        raise InfographicError(f"{beat.id}: a map beat has no map recipe (9.3)")
    plan = beat.map
    return MapRecipe(
        region=plan.region.strip(),
        bbox=plan.bbox,
        markers=tuple(MapMarkerRecipe(m.name.strip(), m.lat, m.lon) for m in plan.markers),
        route=tuple(n.strip() for n in plan.route),
        object=plan.object,
    )


def _locate(geocoder: Geocoder, name: str, what: str) -> Place:
    """The place for `name`, or the 9.3 refusal naming it."""
    try:
        found = geocoder.lookup(name)
    except GeocodeError as exc:
        raise InfographicError(f"the map {what} {name!r} could not be geocoded: {exc}") from None
    if found is None:
        raise InfographicError(
            f"the map {what} {name!r} is not in the gazetteer (and no fallback answered); "
            "a marker is never placed by a guess (9.3)"
        )
    return found


def _widened(bbox: geo.BBox, places: Sequence[Place]) -> geo.BBox:
    west, south, east, north = bbox
    for p in places:
        west, east = min(west, p.lon), max(east, p.lon)
        south, north = min(south, p.lat), max(north, p.lat)
    if east - west < MIN_SPAN_DEG:
        mid = (west + east) / 2
        west, east = mid - MIN_SPAN_DEG / 2, mid + MIN_SPAN_DEG / 2
    if north - south < MIN_SPAN_DEG:
        mid = (south + north) / 2
        south, north = mid - MIN_SPAN_DEG / 2, mid + MIN_SPAN_DEG / 2
    return west, south, east, north


def _padded(bbox: geo.BBox, padding: float) -> geo.BBox:
    west, south, east, north = bbox
    dx, dy = (east - west) * padding, (north - south) * padding
    return (
        max(-180.0, west - dx),
        max(-geo.MAX_LAT, south - dy),
        min(180.0, east + dx),
        min(geo.MAX_LAT, north + dy),
    )


Edges = tuple[float, float, float, float]  # left, top, right, bottom (072)


def _meets(a: Edges, b: Edges) -> bool:
    """Two boxes share area; touching edges do not count."""
    eps = 1e-6
    return a[0] < b[2] - eps and b[0] < a[2] - eps and a[1] < b[3] - eps and b[1] < a[3] - eps


def _inside_map_band(box: Edges, numbers: MapNumbers) -> bool:
    left, top, right, bottom = box
    return (
        left >= SAFE_LEFT - 1e-6
        and right <= WIDTH - SAFE_RIGHT_PX + 1e-6
        and top >= SAFE_TOP_PX - 1e-6
        and bottom <= numbers.max_bottom_y + 1e-6
    )


def _pill_candidates(
    x: float, y: float, width: float, height: float, numbers: MapNumbers
) -> list[Edges]:
    """072: where a pill may sit, in the order tried - to the right of its dot (to the
    left when the right rail is near), then the other side, then each step up and down
    by the style's `label_step_px`, both sides at every step, up to `label_steps_max`."""
    right = x + MAP_DOT_PX / 2 + MAP_LABEL_GAP_PX
    left = x - MAP_DOT_PX / 2 - MAP_LABEL_GAP_PX - width
    sides = (right, left) if right + width <= WIDTH - SAFE_RIGHT_PX else (left, right)
    offsets = [0.0]
    for k in range(1, numbers.label_steps_max + 1):
        offsets += [-k * numbers.label_step_px, k * numbers.label_step_px]
    out: list[Edges] = []
    for dy in offsets:
        top = y - height / 2 + dy
        out += [(side, top, side + width, top + height) for side in sides]
    return out


Options = list[list[tuple[int, Edges]]]  # per marker: (candidate index, pill box), in order


def _separated(options: Options) -> list[Edges] | None:
    """072's collision pass: one pill per marker, no two meeting, with the least total
    candidate index (the least moving: a pill that is clear stays, a flip before a step),
    ties to the earlier marker's earlier candidate. A depth-first search in marker order
    that drops every later candidate a choice covers and cuts a branch that cannot beat
    the best found; at most `markers_max` markers, so it stays small. None when no
    arrangement exists."""
    best: list[Edges] | None = None
    best_cost = math.inf

    def walk(k: int, chosen: list[Edges], cost: int, rest: Options) -> None:
        nonlocal best, best_cost
        if k == len(options):
            best, best_cost = list(chosen), cost
            return
        for index, box in rest[0]:
            if cost + index >= best_cost:
                break  # the candidates are in index order: none after this one is cheaper
            later = [[(j, b) for j, b in opts if not _meets(b, box)] for opts in rest[1:]]
            if all(later):
                walk(k + 1, [*chosen, box], cost + index, later)

    walk(0, [], 0, options)
    return best


def _marker_layouts(
    names: Sequence[str], places: Sequence[Place], projection: geo.Mercator, *,
    style: CaptionStyle, numbers: MapNumbers,
) -> list[MapMarkerLayout]:  # fmt: skip
    """Every dot at its projected point and its pill beside it (9.3). The pill says the
    name the planner wrote; the gazetteer gave the coordinate only (072). A pill's
    candidates are the ones inside the safe area that cover no other marker's dot; the
    collision pass then picks one per marker so no two pills meet. A marker with no
    candidate, or a set the pass cannot separate, is a `LayoutError` naming the markers,
    as a diagram label outside the safe area is a build failure."""
    points = [projection.project(p.lon, p.lat) for p in places]
    ring = MAP_DOT_PX / 2 + MAP_RING_PX
    dots: list[Edges] = [(x - ring, y - ring, x + ring, y + ring) for x, y in points]
    room = WIDTH - SAFE_RIGHT_PX - SAFE_LEFT
    sizes: list[tuple[int, float, float]] = []
    options: Options = []
    for i, (name, (x, y)) in enumerate(zip(names, points, strict=True)):
        font_px = _fitted(name, font_px=MAP_LABEL_FONT_PX, style=style,
                          min_font_px=MAP_LABEL_MIN_FONT_PX, room=room)  # fmt: skip
        width = _measured(name, font_px=font_px, style=style) + 2 * MAP_LABEL_PAD_X
        height = font_px * style.line_height + 2 * MAP_LABEL_PAD_Y
        sizes.append((font_px, width, height))
        others = [d for j, d in enumerate(dots) if j != i]
        options.append([
            (index, b) for index, b in enumerate(_pill_candidates(x, y, width, height, numbers))
            if _inside_map_band(b, numbers) and not any(_meets(b, d) for d in others)
        ])  # fmt: skip
    where = (
        f"on either side of its dot within {numbers.label_steps_max} steps of "
        f"{numbers.label_step_px:g} px, clear of the other dots, inside the safe area x "
        f"{SAFE_LEFT:g}-{WIDTH - SAFE_RIGHT_PX:g}, y {SAFE_TOP_PX:g}-{numbers.max_bottom_y}"
    )
    for name, (x, y), opts, (_, width, height) in zip(names, points, options, sizes, strict=True):
        if not opts:
            raise LayoutError(
                f"the map label {name!r} ({width:.0f} x {height:.0f} px, dot at ({x:.0f}, "
                f"{y:.0f})) has no place {where}; the markers are "
                f"{', '.join(repr(n) for n in names)} (072)"
            )
    pills = _separated(options)
    if pills is None:
        raise LayoutError(
            f"the map labels {', '.join(repr(n) for n in names)} cannot all be placed {where} "
            "without one pill covering another (072)"
        )
    return [
        MapMarkerLayout(
            name=name, lat=place.lat, lon=place.lon, x=x, y=y, label_left=box[0],
            label_top=box[1], label_width=width, label_height=height, label_font_px=font_px,
            source=place.source,
        )  # fmt: skip
        for name, place, (x, y), box, (font_px, width, height)
        in zip(names, places, points, pills, sizes, strict=True)
    ]


@dataclass(frozen=True)
class MapTimeline:
    """When each of the map's motions runs, in seconds from the beat's start (028): one
    drop start per marker, the drop and label-pop lengths, the route's start and draw
    time, the object's start and travel time, and `landed_s`, when the last present
    motion has landed. An absent motion is 0 long and the ones after it close up."""

    pin_delays: tuple[float, ...]
    pin_drop_s: float
    label_pop_s: float
    route_start_s: float
    route_draw_s: float
    object_start_s: float
    object_travel_s: float
    landed_s: float


def map_timeline(
    length_s: float, *, markers: int, pins: bool, route: bool, obj: bool
) -> MapTimeline:
    """The beat's first `MOTIONS_IN_FRACTION` shared between the present motions in
    order - pins, route, object - each at its ceiling on a long beat, all scaled by
    the one factor that fits the window on a short one."""
    window = max(0.0, length_s) * MOTIONS_IN_FRACTION
    pins_full = (
        (max(1, markers) - 1) * PIN_STAGGER_MAX_S + PIN_DROP_MAX_S + LABEL_POP_MAX_S
        if pins
        else 0.0
    )
    route_full = ROUTE_DRAW_MAX_S if route else 0.0
    object_full = OBJECT_TRAVEL_MAX_S if obj else 0.0
    total = pins_full + route_full + object_full
    factor = min(1.0, window / total) if total > 0 else 0.0
    stagger = PIN_STAGGER_MAX_S * factor if pins else 0.0
    pin_drop_s = PIN_DROP_MAX_S * factor if pins else 0.0
    label_pop_s = LABEL_POP_MAX_S * factor if pins else 0.0
    pin_delays = tuple(i * stagger for i in range(max(1, markers)))
    pins_end = (pin_delays[-1] + pin_drop_s + label_pop_s) if pins else 0.0
    route_draw_s = route_full * factor
    object_travel_s = object_full * factor
    route_start_s = pins_end
    object_start_s = route_start_s + route_draw_s
    return MapTimeline(
        pin_delays=pin_delays,
        pin_drop_s=pin_drop_s,
        label_pop_s=label_pop_s,
        route_start_s=route_start_s,
        route_draw_s=route_draw_s,
        object_start_s=object_start_s,
        object_travel_s=object_travel_s,
        landed_s=object_start_s + object_travel_s,
    )


def route_segments(points: Sequence[tuple[float, float]]) -> list[RouteSegment]:
    """The route polyline as straight legs (028): each with its ends, its start and end
    as fractions of the whole length, and the tangent heading in screen degrees
    (`atan2` with y down: 0 east, 90 south, 180 west, -90 north). A zero-length leg is
    dropped; a route with no length at all is no legs."""
    legs: list[tuple[tuple[float, float], tuple[float, float], float]] = []
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        length = math.hypot(x1 - x0, y1 - y0)
        if length > 0:
            legs.append(((x0, y0), (x1, y1), length))
    total = sum(length for _, _, length in legs)
    if total <= 0:
        return []
    out: list[RouteSegment] = []
    walked = 0.0
    for (x0, y0), (x1, y1), length in legs:
        out.append(
            RouteSegment(
                x0=x0, y0=y0, x1=x1, y1=y1, t0=walked / total, t1=(walked + length) / total,
                heading_deg=math.degrees(math.atan2(y1 - y0, x1 - x0)),
            )  # fmt: skip
        )
        walked += length
    return out


def route_path(points: Sequence[tuple[float, float]]) -> str:
    """The route as an SVG path string to a tenth of a pixel, as the base paths are."""
    if not points:
        return ""
    head, *rest = points
    return " ".join([f"M {head[0]:.1f} {head[1]:.1f}", *(f"L {x:.1f} {y:.1f}" for x, y in rest)])


def resolve_map(
    recipe: MapRecipe, *, numbers: InfographicNumbers, geocoder: Geocoder,
    layers: geo.Layers | None = None, overlays: Sequence[OverlayKind] = (),
    length_s: float = 0.0,
) -> MapLayout:  # fmt: skip
    """The map laid out in composition pixels (9.3): the crop fitted into the band
    inside the safe box and above the style's `broll.card_max_bottom_y`, the base as
    SVG paths, the markers at their geocoded points, the route as pixels. `overlays`
    are the beat's (028): `pin_drop`, `route_arrow` and `object_path` switch the three
    motions on, timed from the beat's `length_s`; with none the map is static and the
    length is not read."""
    m, style = numbers.map, numbers.captions
    if not recipe.markers:
        raise InfographicError("a map has no markers (9.3)")
    if len(recipe.markers) > m.markers_max:
        raise InfographicError(
            f"a map has {len(recipe.markers)} markers, over broll.motion.map.markers_max "
            f"{m.markers_max}"
        )
    pins = "pin_drop" in overlays
    arrow = "route_arrow" in overlays
    moving = "object_path" in overlays
    if (arrow or moving) and len(recipe.route) < 2:
        raise InfographicError(
            f"{'route_arrow' if arrow else 'object_path'} follows the map's route; this map "
            "has none (9.3)"
        )
    if moving and recipe.object is None:
        raise InfographicError(
            "object_path moves the map's object (plane | ship | arrow); none is named (9.3)"
        )
    places = [_locate(geocoder, marker.name, "marker") for marker in recipe.markers]
    route_places = [_locate(geocoder, name, "route point") for name in recipe.route]
    if recipe.bbox is not None:
        base = recipe.bbox
    else:
        if not recipe.region:
            raise InfographicError("a map names no region and no bbox (9.3)")
        region = _locate(geocoder, recipe.region, "region")
        base = region.bbox or (
            region.lon - CITY_SPAN_DEG / 2, region.lat - CITY_SPAN_DEG / 2,
            region.lon + CITY_SPAN_DEG / 2, region.lat + CITY_SPAN_DEG / 2,
        )  # fmt: skip
    crop = _padded(_widened(base, [*places, *route_places]), m.padding)
    band: geo.Rect = (
        SAFE_LEFT, DIAGRAM_BAND_TOP, WIDTH - SAFE_RIGHT_PX - SAFE_LEFT,
        m.max_bottom_y - DIAGRAM_BAND_TOP,
    )  # fmt: skip
    projection = geo.Mercator.fit(crop, band)
    frame: geo.Rect = (
        -MAP_CLIP_MARGIN_PX, -MAP_CLIP_MARGIN_PX,
        WIDTH + 2 * MAP_CLIP_MARGIN_PX, HEIGHT + 2 * MAP_CLIP_MARGIN_PX,
    )  # fmt: skip
    paths = geo.base_paths(layers or geo.load_layers(), projection, frame)
    timeline = map_timeline(length_s, markers=len(places), pins=pins, route=arrow, obj=moving)
    laid = _marker_layouts([marker.name for marker in recipe.markers], places, projection,
                           style=style, numbers=m)  # fmt: skip
    markers = [
        marker.model_copy(update={"delay_s": delay})
        for marker, delay in zip(laid, timeline.pin_delays, strict=True)
    ]
    route = [projection.project(p.lon, p.lat) for p in route_places]
    segments = route_segments(route) if (arrow or moving) else []
    return MapLayout(
        region=recipe.region, bbox=crop, left=band[0], top=band[1], width=band[2],
        height=band[3], scale=projection.scale, center_lon=projection.center_lon,
        center_merc=projection.center_merc, center_x=projection.center_x,
        center_y=projection.center_y, land=paths.land, coast=paths.coast,
        borders=paths.borders, land_color=m.land, coast_color=m.coast, border_color=m.border,
        coast_px=m.coast_px, border_px=m.border_px, markers=markers,
        route=route, object=recipe.object,
        marker_color=numbers.palette.accent, dot_px=MAP_DOT_PX, ring_px=MAP_RING_PX,
        label_fill=DIAGRAM_LABEL_FILL, label_radius_px=DIAGRAM_LABEL_RADIUS_PX,
        text_color="#FFFFFF", draw_s=m.draw_s,
        # 028: the three animations, on or off by the beat's overlays.
        pin_drop=pins, route_arrow=arrow, object_path=moving,
        pin_drop_s=timeline.pin_drop_s, pin_drop_px=PIN_DROP_PX if pins else 0.0,
        label_pop_s=timeline.label_pop_s,
        route_path=route_path(route) if segments else "",
        route_length_px=sum(math.dist((s.x0, s.y0), (s.x1, s.y1)) for s in segments),
        segments=segments, route_start_s=timeline.route_start_s,
        route_draw_s=timeline.route_draw_s, route_px=ROUTE_PX if arrow else 0.0,
        arrow_px=ARROW_PX if arrow else 0.0, object_start_s=timeline.object_start_s,
        object_travel_s=timeline.object_travel_s, object_px=OBJECT_PX if moving else 0.0,
        landed_s=timeline.landed_s,
    )  # fmt: skip
