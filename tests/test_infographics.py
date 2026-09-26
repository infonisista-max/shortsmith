"""infographics (ticket 021; decisions 9.2, 9.3, 5.5): the two infographic kinds that
are drawn, not found.

`resolve_chart` lays a bar, line or two-value comparison out from the planner's series
- axes scaled from the real numbers, values formatted in the style's grouping, the plot
inside the safe box and above the style's `broll.card_max_bottom_y`. `resolve_diagram`
maps the planner's percentage label positions onto the classified base picture and
refuses a label that would land outside the safe area (text never goes inside a
generated image, so the labels are drawn in code).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import fixture, geo, infographics, render
from shortsmith.contracts import (
    Constraints,
    Crop,
    PlanLabel,
    PlanRequest,
    PlanStyle,
    SeriesPoint,
)
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber

NUMBERS = infographics.numbers_for(render.loaded_styles()["explainer"])
CARD_LIMIT = render.loaded_styles()["explainer"].broll.card_max_bottom_y


def _series(*values: float) -> tuple[SeriesPoint, ...]:
    return tuple(
        SeriesPoint(label=f"y{2020 + i}", value=v) for i, v in enumerate(values)
    )


def _chart(form: str, *values: float, title: str = "Where the money went",
           unit: str = "") -> infographics.ChartLayout:  # fmt: skip
    recipe = infographics.ChartRecipe(
        form=form,  # pyright: ignore[reportArgumentType]
        series=_series(*values),
        title=title,
        unit=unit,
    )
    return infographics.resolve_chart(recipe, numbers=NUMBERS)


def _base(width: int = 1080, height: int = 1920, treatment: str = "photo"):
    return infographics.DiagramAsset(
        src="/tmp/base.png",
        width=width,
        height=height,
        treatment=treatment,  # pyright: ignore[reportArgumentType]
        crop=Crop(),
    )


def _diagram(*labels: PlanLabel, base: infographics.DiagramAsset | None = None,
             length_s: float = 3.0):  # fmt: skip
    return infographics.resolve_diagram(
        infographics.DiagramRecipe(labels=labels), base or _base(), numbers=NUMBERS,
        length_s=length_s,
    )


# --- charts (9.2) ----------------------------------------------------------------------


def test_bars_scale_from_the_real_series_with_the_tallest_filling_the_plot() -> None:
    chart = _chart("bar", 10.0, 5.0, 20.0)
    heights = [m.bar_height for m in chart.marks]
    assert heights[2] == pytest.approx(chart.plot_height)
    assert heights[0] == pytest.approx(chart.plot_height * 0.5)
    assert heights[1] == pytest.approx(chart.plot_height * 0.25)
    assert [m.label for m in chart.marks] == ["y2020", "y2021", "y2022"]


def test_bars_sit_on_the_baseline_left_to_right_inside_the_plot() -> None:
    chart = _chart("bar", 3.0, 7.0, 5.0, 9.0)
    lefts = [m.bar_left for m in chart.marks]
    assert lefts == sorted(lefts)
    for mark in chart.marks:
        assert mark.bar_left >= chart.plot_left
        assert mark.bar_left + mark.bar_width <= chart.plot_left + chart.plot_width
        assert mark.bar_top + mark.bar_height == pytest.approx(chart.baseline_y)


def test_the_plot_the_title_and_the_axis_labels_stay_in_the_safe_box() -> None:
    chart = _chart("bar", 4.0, 8.0)
    assert chart.plot_left >= infographics.SAFE_LEFT
    assert chart.plot_left + chart.plot_width <= infographics.WIDTH - infographics.SAFE_LEFT
    assert chart.title_top >= infographics.SAFE_TOP
    assert chart.title_top + chart.title_font_px <= chart.plot_top
    # the axis labels are outside the plot box, under the baseline, still above the limit
    assert chart.label_top >= chart.baseline_y
    assert chart.label_top + chart.label_font_px <= CARD_LIMIT


def test_a_line_chart_puts_one_dot_per_point_at_the_value_height() -> None:
    chart = _chart("line", 1.0, 2.0, 4.0)
    assert chart.form == "line"
    xs = [m.point_x for m in chart.marks]
    assert xs == sorted(xs)
    lowest, highest = chart.marks[0], chart.marks[2]
    assert highest.point_y == pytest.approx(chart.baseline_y - chart.plot_height)
    assert lowest.point_y == pytest.approx(chart.baseline_y - chart.plot_height * 0.25)
    assert all(m.bar_width == m.bar_height for m in chart.marks)  # dots, not bars


def test_a_comparison_draws_two_equal_columns_in_two_colours() -> None:
    chart = _chart("comparison", 40.0, 60.0)
    assert len(chart.marks) == 2
    left, right = chart.marks
    assert left.bar_width == right.bar_width
    assert left.color != right.color
    assert right.bar_height > left.bar_height


def test_the_largest_bar_takes_the_style_accent() -> None:
    chart = _chart("bar", 3.0, 9.0, 4.0)
    accent = NUMBERS.palette.accent
    assert [m.color == accent for m in chart.marks] == [False, True, False]


@pytest.mark.parametrize(
    ("value", "decimals", "grouping", "expected"),
    [
        (1234567, 0, "indian", "12,34,567"),
        (1234567, 0, "western", "1,234,567"),
        (1234567, 0, "plain", "1234567"),
        (12345.678, 1, "indian", "12,345.7"),
        (999, 0, "indian", "999"),
        (0, 0, "western", "0"),
    ],
)
def test_values_are_formatted_in_the_styles_grouping_and_decimals(
    value: float, decimals: int, grouping: str, expected: str
) -> None:
    assert infographics.format_value(value, decimals=decimals, grouping=grouping) == expected


def test_the_value_text_uses_the_style_format_and_the_beats_unit() -> None:
    chart = _chart("bar", 1200000.0, 400000.0, unit="crore")
    assert [m.value_text for m in chart.marks] == ["12,00,000 crore", "4,00,000 crore"]
    percent = _chart("bar", 40.0, 60.0, unit="%")
    assert [m.value_text for m in percent.marks] == ["40%", "60%"]


def test_the_chart_carries_the_styles_draw_on_time_and_its_title() -> None:
    chart = _chart("bar", 1.0, 2.0, title="Two years")
    assert chart.title == "Two years"
    assert chart.grow_s == NUMBERS.chart.draw_s
    delays = [m.delay_s for m in chart.marks]
    assert delays == sorted(delays) and len(set(delays)) == len(delays)


@pytest.mark.parametrize(
    ("form", "values", "message"),
    [
        ("bar", (), "empty"),
        ("bar", (5.0,), "at least two"),
        ("comparison", (5.0, 6.0, 7.0), "exactly two"),
        ("line", (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0), "marks_max"),
        ("bar", (5.0, -1.0), "negative"),
        ("bar", (0.0, 0.0), "no scale"),
    ],
)
def test_a_mismatched_series_is_refused(
    form: str, values: tuple[float, ...], message: str
) -> None:
    with pytest.raises(infographics.InfographicError, match=message):
        _chart(form, *values)


def test_a_point_with_no_label_is_refused() -> None:
    recipe = infographics.ChartRecipe(
        form="bar", series=(SeriesPoint(label="", value=1.0), SeriesPoint(label="b", value=2.0))
    )
    with pytest.raises(infographics.InfographicError, match="label"):
        infographics.resolve_chart(recipe, numbers=NUMBERS)


# --- labelled diagrams (9.2, 9.3, 5.5) ------------------------------------------------


def test_percentage_positions_become_pixels_on_the_base_picture() -> None:
    diagram = _diagram(PlanLabel(text="Rotor", x=50.0, y=30.0, anchor="center"))
    (label,) = diagram.labels
    assert diagram.box_width == infographics.WIDTH  # a full-bleed base fills the frame
    assert diagram.box_height == infographics.HEIGHT
    assert label.left + label.width / 2 == pytest.approx(540.0)
    assert label.top + label.height / 2 == pytest.approx(0.30 * infographics.HEIGHT)


@pytest.mark.parametrize("anchor", ["left", "center", "right"])
def test_the_anchor_decides_which_edge_the_position_pins(anchor: str) -> None:
    label = PlanLabel(text="Intake", x=50.0, y=40.0, anchor=anchor)  # pyright: ignore[reportArgumentType]
    (placed,) = _diagram(label).labels
    x = 0.5 * infographics.WIDTH
    edge = {"left": placed.left, "center": placed.left + placed.width / 2,
            "right": placed.left + placed.width}[anchor]  # fmt: skip
    assert edge == pytest.approx(x)
    assert placed.anchor == anchor


def test_a_label_below_the_safe_area_is_refused() -> None:
    with pytest.raises(infographics.InfographicError, match="safe area"):
        _diagram(PlanLabel(text="Exhaust", x=50.0, y=95.0))


def test_a_label_running_off_the_right_rail_is_refused() -> None:
    with pytest.raises(infographics.InfographicError, match="safe area"):
        _diagram(PlanLabel(text="A long label that will not fit", x=98.0, y=40.0, anchor="left"))


def test_the_base_still_takes_the_styles_ken_burns_and_dim() -> None:
    diagram = _diagram(PlanLabel(text="Rotor", x=40.0, y=40.0))
    d = NUMBERS.diagram
    assert (diagram.scale_from, diagram.scale_to) == (d.scale_from, d.scale_to)
    assert diagram.dim == d.dim > 0
    assert diagram.fly_s == d.fly_s
    assert diagram.src == "/tmp/base.png"


def test_a_card_shaped_base_is_boxed_above_the_card_limit() -> None:
    diagram = _diagram(
        PlanLabel(text="Rotor", x=50.0, y=50.0), base=_base(1200, 900, treatment="card")
    )
    assert diagram.left >= infographics.SAFE_LEFT
    assert diagram.left + diagram.box_width <= infographics.WIDTH - infographics.SAFE_LEFT
    assert diagram.top + diagram.box_height <= CARD_LIMIT
    # the labels ride on the box, not on the frame
    (label,) = diagram.labels
    assert label.top + label.height / 2 == pytest.approx(diagram.top + diagram.box_height / 2)


def test_labels_beyond_the_style_maximum_are_cut_to_it() -> None:
    labels = [PlanLabel(text=f"L{i}", x=30.0, y=30.0 + i) for i in range(9)]
    diagram = _diagram(*labels)
    assert len(diagram.labels) == NUMBERS.diagram.labels_max == 5
    delays = [label.delay_s for label in diagram.labels]
    assert delays == sorted(delays) and len(set(delays)) == len(delays)


# --- label fly-ins (ticket 029; decisions 9.2, 9.3) ------------------------------------


def test_labels_enter_one_after_another_inside_the_first_part_of_the_beat() -> None:
    labels = [PlanLabel(text=f"L{i}", x=40.0, y=20.0 + 8 * i) for i in range(4)]
    for length in (0.5, 1.2, 3.0, 6.0):
        diagram = _diagram(*labels, length_s=length)
        delays = [label.delay_s for label in diagram.labels]
        assert delays[0] == 0.0
        assert all(b > a for a, b in zip(delays, delays[1:], strict=False)), (length, delays)
        # the last label has landed by the style's share of the beat, so it is read
        landed = delays[-1] + diagram.fly_s
        assert landed <= length * infographics.LABELS_IN_FRACTION + 1e-9, (length, landed)


def test_the_stagger_grows_with_the_beat_and_stops_at_its_ceiling() -> None:
    short = infographics.label_stagger(3, length_s=0.5, fly_s=0.35)
    longer = infographics.label_stagger(3, length_s=2.0, fly_s=0.35)
    longest = infographics.label_stagger(3, length_s=30.0, fly_s=0.35)
    assert 0 < short[0] < longer[0] <= longest[0] == infographics.LABEL_STAGGER_MAX_S
    # a beat with room keeps the style's fly-in time; a short one shortens it to fit
    assert longer[1] == longest[1] == 0.35
    assert short[1] < 0.35
    assert infographics.label_stagger(1, length_s=3.0, fly_s=0.35) == (0.0, 0.35)


@pytest.mark.parametrize(
    ("x", "y", "anchor", "edge"),
    [
        (20.0, 45.0, "left", "left"),
        (85.0, 45.0, "right", "right"),
        (50.0, 16.0, "center", "top"),
    ],
)
def test_each_label_flies_in_from_its_nearest_frame_edge(
    x: float, y: float, anchor: str, edge: str
) -> None:
    label = PlanLabel(text="Rotor", x=x, y=y, anchor=anchor)  # pyright: ignore[reportArgumentType]
    (placed,) = _diagram(label).labels
    start_left, start_top = placed.left + placed.from_x, placed.top + placed.from_y
    if edge == "left":
        assert placed.from_y == 0 and start_left + placed.width <= 0
    elif edge == "right":
        assert placed.from_y == 0 and start_left >= infographics.WIDTH
    else:
        assert placed.from_x == 0 and start_top + placed.height <= 0


# --- the counter (ticket 029; decisions 4.2, 9.2) ---------------------------------------


def _count(start: float, target: float, *, frames: int = 30, land: int = 5,
           decimals: int = 0, grouping: str = "indian", unit: str = "") -> list[str]:  # fmt: skip
    return infographics.counter_texts(
        start, target, frames=frames, land_frames=land, decimals=decimals,
        grouping=grouping, unit=unit,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("grouping", "target", "expected"),
    [
        ("indian", 1250000, "12,50,000 crore"),
        ("western", 1250000, "1,250,000 crore"),
        ("indian", 850, "850 crore"),
    ],
)
def test_the_counter_writes_its_numbers_in_the_styles_digit_grouping(
    grouping: str, target: float, expected: str
) -> None:
    texts = _count(0, target, grouping=grouping, unit="crore")
    assert texts[0] == ("0 crore")
    assert texts[-1] == expected


def test_the_counter_eases_to_the_target_and_holds_it_through_the_landing() -> None:
    texts = _count(0, 1000, frames=30, land=5, grouping="plain")
    assert len(texts) == 30
    values = [int(t) for t in texts]
    assert values == sorted(values)
    assert values[24] == 1000  # there by the landing
    assert set(values[25:]) == {1000}  # the last 0.16 s is the landing, not counting
    assert values[1] - values[0] > values[23] - values[22]  # eases out


def test_the_counter_keeps_the_plans_decimals_and_counts_down_too() -> None:
    texts = _count(12.5, 2.5, frames=20, land=4, decimals=1, grouping="western", unit="%")
    assert texts[0] == "12.5%" and texts[-1] == "2.5%"
    assert all(t.endswith("%") and "." in t for t in texts)
    values = [float(t.rstrip("%")) for t in texts]
    assert values == sorted(values, reverse=True)


# --- the style numbers (1.2) ----------------------------------------------------------


def test_every_chart_and_diagram_number_comes_from_the_front_matter() -> None:
    spec = render.loaded_styles()["explainer"]
    chart = spec.broll.motion["chart"]
    diagram = spec.broll.motion["infographic"]
    assert NUMBERS.chart.marks_max == int(chart["marks_max"])
    assert NUMBERS.chart.decimals == int(chart["decimals"])
    assert NUMBERS.chart.grouping == str(chart["grouping"])
    assert NUMBERS.chart.draw_s == float(chart["duration_s"])
    assert NUMBERS.diagram.labels_max == int(diagram["labels_max"])
    assert NUMBERS.diagram.fly_s == float(diagram["duration_s"])


# --- maps (ticket 020; decisions 9.3, 12.1) ----------------------------------------------------


def _request() -> PlanRequest:
    return PlanRequest(
        brief="Topic: a six-second synthetic clip.", style=PlanStyle(name="explainer"),
        style_note="explainer", transcript=FakeTranscriber().transcribe(Path("unused.mp4")),
        references=[], asset_policy="any",
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
    )  # fmt: skip


def _map(
    *markers: str, region: str = "India", bbox: tuple[float, float, float, float] | None = None,
    route: tuple[str, ...] = (), geocoder: geo.Geocoder | None = None,
    lat_lon: dict[str, tuple[float, float]] | None = None,
) -> infographics.MapLayout:  # fmt: skip
    given = lat_lon or {}
    recipe = infographics.MapRecipe(
        region=region, bbox=bbox,
        markers=tuple(
            infographics.MapMarkerRecipe(name=m, lat=given.get(m, (None, None))[0],
                                         lon=given.get(m, (None, None))[1])
            for m in markers
        ),
        route=route,
    )  # fmt: skip
    return infographics.resolve_map(
        recipe, numbers=NUMBERS, geocoder=geocoder or geo.FakeGeocoder()
    )


BAND_TOP = infographics.DIAGRAM_BAND_TOP


def test_markers_are_placed_by_the_geocoders_points_inside_the_map_band() -> None:
    layout = _map("Delhi", "Mumbai")
    assert [m.name for m in layout.markers] == ["Delhi", "Mumbai"]
    delhi, mumbai = layout.markers
    assert (delhi.lat, delhi.lon) == (28.672, 77.228) and delhi.source == "fake"
    assert delhi.x > mumbai.x and delhi.y < mumbai.y  # east of, north of
    for m in layout.markers:
        assert infographics.SAFE_LEFT <= m.x <= infographics.WIDTH - infographics.SAFE_RIGHT_PX
        assert BAND_TOP <= m.y <= CARD_LIMIT


def test_planner_coordinates_are_ignored_the_gazetteer_places_the_marker() -> None:
    honest = _map("Delhi", "Mumbai")
    lying = _map("Delhi", "Mumbai", lat_lon={"Delhi": (0.0, 0.0), "Mumbai": (51.5, -0.1)})
    assert [(m.x, m.y) for m in lying.markers] == [(m.x, m.y) for m in honest.markers]
    assert [(m.lat, m.lon) for m in lying.markers] == [(m.lat, m.lon) for m in honest.markers]


def test_a_geocoding_miss_is_an_error_naming_the_place_never_a_guessed_point() -> None:
    with pytest.raises(infographics.InfographicError, match="Atlantis"):
        _map("Delhi", "Atlantis")
    with pytest.raises(infographics.InfographicError, match="Narnia"):
        _map("Delhi", region="Narnia")
    with pytest.raises(infographics.InfographicError, match="Shangri-La"):
        _map("Delhi", "Mumbai", route=("Delhi", "Shangri-La"))


def test_the_region_is_cropped_with_the_styles_padding_and_fitted_in_the_band() -> None:
    layout = _map("Delhi", "Mumbai")
    india = geo.FakeGeocoder().lookup("India")
    assert india is not None and india.bbox is not None
    west, south, east, north = layout.bbox
    padding = NUMBERS.map.padding
    assert west == pytest.approx(india.bbox[0] - (india.bbox[2] - india.bbox[0]) * padding)
    assert east == pytest.approx(india.bbox[2] + (india.bbox[2] - india.bbox[0]) * padding)
    assert south == pytest.approx(india.bbox[1] - (india.bbox[3] - india.bbox[1]) * padding)
    assert north == pytest.approx(india.bbox[3] + (india.bbox[3] - india.bbox[1]) * padding)
    assert (layout.left, layout.top) == (infographics.SAFE_LEFT, BAND_TOP)
    assert layout.left + layout.width == infographics.WIDTH - infographics.SAFE_RIGHT_PX
    assert layout.top + layout.height == CARD_LIMIT
    assert layout.region == "India"


def test_a_marker_outside_the_region_widens_the_crop_rather_than_falling_off_the_map() -> None:
    layout = _map("Delhi", "London")
    west, _south, _east, north = layout.bbox
    assert west < -0.117 and north > 51.5
    for m in layout.markers:
        assert infographics.SAFE_LEFT <= m.x <= infographics.WIDTH - infographics.SAFE_RIGHT_PX
        assert BAND_TOP <= m.y <= CARD_LIMIT


def test_a_bbox_in_the_recipe_is_the_crop_and_a_city_region_gets_a_span() -> None:
    boxed = _map("Delhi", region="", bbox=(70.0, 20.0, 90.0, 35.0))
    padding = NUMBERS.map.padding
    assert boxed.bbox[0] == pytest.approx(70.0 - 20.0 * padding)
    assert boxed.region == ""
    city = _map("Mumbai", region="Mumbai")
    west, south, east, north = city.bbox
    assert west < 72.876 < east and south < 19.068 < north
    assert (east - west) >= infographics.CITY_SPAN_DEG


def test_the_base_is_drawn_from_the_bundled_land_coast_and_borders() -> None:
    layout = _map("Delhi", "Mumbai")
    assert layout.land and layout.coast and layout.borders
    assert all(p.startswith("M") and p.endswith("Z") for p in layout.land)
    assert layout.land_color == NUMBERS.map.land
    assert layout.marker_color == NUMBERS.palette.accent
    # the projection is on the layout so 028 can place its animations on the same maths
    projection = geo.Mercator(layout.scale, layout.center_lon, layout.center_merc,
                              layout.center_x, layout.center_y)  # fmt: skip
    delhi = layout.markers[0]
    assert projection.project(delhi.lon, delhi.lat) == pytest.approx((delhi.x, delhi.y))


def test_marker_labels_sit_beside_the_dot_inside_the_safe_area_and_flip_at_the_edge() -> None:
    # a crop whose east edge is just past Kolkata puts that dot near the right rail
    layout = _map("Delhi", "Mumbai", "Kolkata", bbox=(60.0, 10.0, 88.5, 30.0))
    for m in layout.markers:
        assert m.label_left >= infographics.SAFE_LEFT
        assert m.label_left + m.label_width <= infographics.WIDTH - infographics.SAFE_RIGHT_PX
        assert m.label_top >= infographics.SAFE_TOP
        assert m.label_top + m.label_height <= CARD_LIMIT
        assert m.label_top + m.label_height / 2 == pytest.approx(m.y)
    kolkata = layout.markers[2]  # the easternmost: its label would leave the right rail
    assert kolkata.label_left + kolkata.label_width < kolkata.x
    delhi = layout.markers[0]
    assert delhi.label_left > delhi.x


def test_a_route_is_projected_in_order_and_the_object_rides_along() -> None:
    recipe = infographics.MapRecipe(
        region="India",
        markers=(infographics.MapMarkerRecipe("Delhi"), infographics.MapMarkerRecipe("Mumbai")),
        route=("Delhi", "Chennai", "Mumbai"), object="plane",
    )  # fmt: skip
    layout = infographics.resolve_map(recipe, numbers=NUMBERS, geocoder=geo.FakeGeocoder())
    assert len(layout.route) == 3
    assert layout.route[0] == pytest.approx((layout.markers[0].x, layout.markers[0].y))
    assert layout.route[-1] == pytest.approx((layout.markers[1].x, layout.markers[1].y))
    assert layout.object == "plane"
    assert _map("Delhi").route == []


def test_too_many_markers_or_none_are_refused_with_the_style_number() -> None:
    top = NUMBERS.map.markers_max
    names = ["Delhi", "Mumbai", "Chennai", "Kolkata", "Bengaluru", "London", "Tokyo", "Dubai"]
    with pytest.raises(infographics.InfographicError, match="markers_max"):
        _map(*names[: top + 1])
    with pytest.raises(infographics.InfographicError, match="no markers"):
        _map()


def test_map_recipe_reads_the_beats_map_plan() -> None:
    beat = next(b for b in FakePlanner().plan_picture(_request()).beats if b.kind == "map")
    recipe = infographics.map_recipe(beat)
    assert recipe.region == "India"
    assert [m.name for m in recipe.markers] == ["Delhi", "Mumbai"]
    assert recipe.route == ("Delhi", "Mumbai") and recipe.object == "plane"
    bare = beat.model_copy(update={"map": None})
    with pytest.raises(infographics.InfographicError, match="map"):
        infographics.map_recipe(bare)


# --- map animations (ticket 028; decisions 9.2, 9.3, 4.1) ---------------------------------

ALL_MAP_OVERLAYS = ("pin_drop", "route_arrow", "object_path")


def _timeline(length_s: float, *, pins: bool = True, route: bool = True, obj: bool = True,
              markers: int = 2) -> infographics.MapTimeline:  # fmt: skip
    return infographics.map_timeline(length_s, markers=markers, pins=pins, route=route, obj=obj)


def test_the_three_map_motions_share_the_beat_in_order_pins_route_object() -> None:
    tl = _timeline(5.0)
    # a long beat (its window past the 3.0 s the ceilings add up to) keeps every
    # ceiling: the stagger, the drop, the draw and the travel
    assert tl.pin_delays == (0.0, pytest.approx(infographics.PIN_STAGGER_MAX_S))
    assert tl.pin_drop_s == pytest.approx(infographics.PIN_DROP_MAX_S)
    assert tl.route_draw_s == pytest.approx(infographics.ROUTE_DRAW_MAX_S)
    assert tl.object_travel_s == pytest.approx(infographics.OBJECT_TRAVEL_MAX_S)
    pins_end = tl.pin_delays[-1] + tl.pin_drop_s + tl.label_pop_s
    assert tl.route_start_s == pytest.approx(pins_end)
    assert tl.object_start_s == pytest.approx(tl.route_start_s + tl.route_draw_s)
    assert tl.landed_s == pytest.approx(tl.object_start_s + tl.object_travel_s)
    assert tl.landed_s <= 5.0 * infographics.MOTIONS_IN_FRACTION
    # and lands well inside the beat, with the ceilings' 3.0 s of motion
    assert tl.landed_s == pytest.approx(3.0)


def test_a_short_beat_scales_every_phase_by_one_factor_so_the_object_lands_in_time() -> None:
    short, long = _timeline(0.5), _timeline(5.0)
    assert short.landed_s == pytest.approx(0.5 * infographics.MOTIONS_IN_FRACTION)
    factor = short.pin_drop_s / long.pin_drop_s
    assert 0 < factor < 1
    assert short.route_draw_s / long.route_draw_s == pytest.approx(factor)
    assert short.object_travel_s / long.object_travel_s == pytest.approx(factor)
    assert short.label_pop_s / long.label_pop_s == pytest.approx(factor)
    assert short.pin_delays[1] / long.pin_delays[1] == pytest.approx(factor)


def test_more_markers_stagger_the_pins_and_push_the_route_later() -> None:
    two, five = _timeline(5.0, markers=2), _timeline(5.0, markers=5)
    assert len(five.pin_delays) == 5
    assert five.pin_delays == tuple(
        pytest.approx(i * infographics.PIN_STAGGER_MAX_S) for i in range(5)
    )
    assert five.route_start_s > two.route_start_s


def test_an_absent_motion_takes_no_time_and_the_rest_close_up() -> None:
    no_pins = _timeline(3.0, pins=False)
    assert no_pins.pin_delays == (0.0, 0.0) and no_pins.pin_drop_s == 0.0
    assert no_pins.label_pop_s == 0.0 and no_pins.route_start_s == 0.0
    no_object = _timeline(3.0, obj=False)
    assert no_object.object_travel_s == 0.0
    assert no_object.landed_s == pytest.approx(no_object.route_start_s + no_object.route_draw_s)
    object_only = _timeline(3.0, pins=False, route=False)
    assert object_only.object_start_s == 0.0 and object_only.route_draw_s == 0.0
    assert object_only.landed_s == pytest.approx(object_only.object_travel_s)
    nothing = _timeline(3.0, pins=False, route=False, obj=False)
    assert nothing.landed_s == 0.0 and nothing.pin_delays == (0.0, 0.0)


def test_route_segments_carry_the_tangent_heading_and_the_length_fractions() -> None:
    segments = infographics.route_segments(
        [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (100.0, 100.0), (0.0, 100.0)]
    )
    # screen degrees: 0 east, 90 south (y grows downward), 180 west; the repeated
    # point is a zero-length segment and is dropped
    assert [s.heading_deg for s in segments] == pytest.approx([0.0, 90.0, 180.0])
    assert [(s.t0, s.t1) for s in segments] == [
        (pytest.approx(0.0), pytest.approx(1 / 3)),
        (pytest.approx(1 / 3), pytest.approx(2 / 3)),
        (pytest.approx(2 / 3), pytest.approx(1.0)),
    ]
    assert (segments[1].x0, segments[1].y0, segments[1].x1, segments[1].y1) == (100, 0, 100, 100)
    north_west = infographics.route_segments([(100.0, 100.0), (0.0, 0.0)])
    assert north_west[0].heading_deg == pytest.approx(-135.0)
    assert infographics.route_segments([(5.0, 5.0)]) == []
    assert infographics.route_segments([(5.0, 5.0), (5.0, 5.0)]) == []
    assert infographics.route_segments([]) == []


def _routed(
    overlays: tuple[str, ...] = ALL_MAP_OVERLAYS, *, length_s: float = 2.0,
    route: tuple[str, ...] = ("Delhi", "Mumbai"), obj: str | None = "plane",
) -> infographics.MapLayout:  # fmt: skip
    recipe = infographics.MapRecipe(
        region="India",
        markers=(infographics.MapMarkerRecipe("Delhi"), infographics.MapMarkerRecipe("Mumbai")),
        route=route,
        object=obj,  # pyright: ignore[reportArgumentType]
    )
    return infographics.resolve_map(
        recipe, numbers=NUMBERS, geocoder=geo.FakeGeocoder(),
        overlays=overlays,  # pyright: ignore[reportArgumentType]
        length_s=length_s,
    )  # fmt: skip


def test_the_map_overlays_are_laid_out_on_the_layout_from_the_beat_length() -> None:
    layout = _routed()
    assert layout.pin_drop and layout.route_arrow and layout.object_path
    timeline = _timeline(2.0)
    assert [m.delay_s for m in layout.markers] == [pytest.approx(d) for d in timeline.pin_delays]
    assert layout.pin_drop_s == pytest.approx(timeline.pin_drop_s)
    assert layout.pin_drop_px == infographics.PIN_DROP_PX
    assert layout.route_start_s == pytest.approx(timeline.route_start_s)
    assert layout.object_start_s == pytest.approx(timeline.object_start_s)
    assert layout.landed_s == pytest.approx(timeline.landed_s)
    assert layout.landed_s <= 2.0 * infographics.MOTIONS_IN_FRACTION
    # the route's pixels are the projected polyline, and its segments the tangent
    (x0, y0), (x1, y1) = layout.route
    assert layout.route_path == f"M {x0:.1f} {y0:.1f} L {x1:.1f} {y1:.1f}"
    assert layout.route_length_px == pytest.approx(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    assert len(layout.segments) == 1
    assert 90.0 < layout.segments[0].heading_deg < 180.0  # Mumbai is south-west of Delhi
    assert layout.route_px > 0 and layout.arrow_px > 0 and layout.object_px > 0


def test_a_map_with_no_overlays_stays_static() -> None:
    static = _map("Delhi", "Mumbai")
    assert not (static.pin_drop or static.route_arrow or static.object_path)
    assert all(m.delay_s == 0.0 for m in static.markers)
    assert static.landed_s == 0.0 and static.segments == [] and static.route_path == ""
    pins_only = _routed(("pin_drop",))
    assert pins_only.pin_drop and not pins_only.route_arrow and not pins_only.object_path
    assert pins_only.landed_s == pytest.approx(_timeline(2.0, route=False, obj=False).landed_s)


def test_the_route_overlays_are_refused_without_a_route_or_an_object() -> None:
    with pytest.raises(infographics.InfographicError, match="route"):
        _routed(("route_arrow",), route=())
    with pytest.raises(infographics.InfographicError, match="object"):
        _routed(("object_path",), obj=None)
