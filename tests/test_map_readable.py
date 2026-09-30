"""Maps a viewer can read (ticket 104; run05 b07/b09, operator finding 1, 30 Sep 2026).

Run05's b09 repair framed Kuwait-Riyadh on a 3 x 5 degree box, so Riyadh sat on empty
blue; b07 showed a lone Riyadh dot with no country named; the land `#2F5597` was hard to
tell from the `#1F3B73` sea; the arrow ended on Riyadh's dot. Here: every map is at least
`map.min_span_deg` across; the named country is filled and named with the target circle
and its angled tag (the numbers of ePTZVwipoAM's `red_circle_india` and
`indus_war_tag` cards); the countries in view are named from the local geodata; a marker
with no name is dropped; the object stops beside the endpoint dot; land and sea differ.
"""

from __future__ import annotations

import json
import math

import pytest

from shortsmith import geo, infographics, render
from shortsmith.contracts import Beat, MapLayout, MapMarker, MapPlan
from shortsmith.reference import INVENTORY_DIR

EXPLAINER = render.loaded_styles()["explainer"]
NUMBERS = infographics.numbers_for(EXPLAINER)
CARD_LIMIT = EXPLAINER.broll.card_max_bottom_y
RIGHT = infographics.WIDTH - infographics.SAFE_RIGHT_PX
GAZETTEER = geo.GazetteerGeocoder()

Box = tuple[float, float, float, float]  # left, top, right, bottom


def _meet(a: Box, b: Box) -> bool:
    eps = 1e-6
    return a[0] < b[2] - eps and b[0] < a[2] - eps and a[1] < b[3] - eps and b[1] < a[3] - eps


def _inside_band(box: Box) -> bool:
    return (
        box[0] >= infographics.SAFE_LEFT - 1e-6
        and box[2] <= RIGHT + 1e-6
        and box[1] >= infographics.SAFE_TOP_PX - 1e-6
        and box[3] <= CARD_LIMIT + 1e-6
    )


def _markers_boxes(layout: MapLayout) -> list[Box]:
    r = layout.dot_px / 2 + layout.ring_px
    out: list[Box] = []
    for m in layout.markers:
        out.append((m.label_left, m.label_top, m.label_left + m.label_width,
                    m.label_top + m.label_height))  # fmt: skip
        out.append((m.x - r, m.y - r, m.x + r, m.y + r))
    return out


def _resolve(recipe: infographics.MapRecipe, **kw: object) -> MapLayout:
    return infographics.resolve_map(
        recipe, numbers=NUMBERS, geocoder=GAZETTEER, **kw  # pyright: ignore[reportArgumentType]
    )


def _run05_b09(**kw: object) -> MapLayout:
    recipe = infographics.MapRecipe(
        bbox=(45.5172, 24.6345, 48.5172, 29.4136),
        markers=(infographics.MapMarkerRecipe("Kuwait"), infographics.MapMarkerRecipe("Riyadh")),
        route=("Kuwait", "Riyadh"), object="arrow",
    )  # fmt: skip
    return _resolve(recipe, **kw)


def _run05_b07() -> MapLayout:
    recipe = infographics.MapRecipe(
        region="Saudi Arabia", markers=(infographics.MapMarkerRecipe("Riyadh"),)
    )
    return _resolve(recipe, overlays=("pin_drop",), length_s=2.9)


def test_the_minimum_span_is_a_style_number() -> None:
    for name in ("explainer", "fastfacts", "footage", "vishva", "hitech"):
        numbers = infographics.numbers_for(render.loaded_styles()[name])
        assert numbers.map.min_span_deg >= 8.0, name


def test_a_3_by_5_degree_repair_bbox_renders_at_the_minimum_span() -> None:
    layout = _run05_b09()
    west, south, east, north = layout.bbox
    assert east - west >= NUMBERS.map.min_span_deg
    assert north - south >= NUMBERS.map.min_span_deg
    # both markers still on the map, well inside the band
    for m in layout.markers:
        assert infographics.SAFE_LEFT < m.x < RIGHT
        assert infographics.DIAGRAM_BAND_TOP < m.y < CARD_LIMIT


def test_a_saudi_arabia_map_fills_and_names_saudi_arabia_and_names_its_neighbours() -> None:
    layout = _run05_b07()
    assert layout.highlight and all(p.startswith("M") for p in layout.highlight)
    assert layout.highlight_color == NUMBERS.map.highlight
    assert layout.target is not None and layout.target.tag == "Saudi Arabia"
    neighbours = {n.name for n in layout.names}
    assert "Saudi Arabia" not in neighbours
    assert len(neighbours & {"Iraq", "Kuwait", "Yemen", "Oman", "Jordan", "Qatar", "Iran",
                             "United Arab Emirates", "Egypt", "Eritrea", "Sudan"}) >= 3  # fmt: skip
    assert len(layout.names) <= NUMBERS.map.names_max


def test_names_and_the_tag_stay_in_the_band_clear_of_the_markers_and_each_other() -> None:
    for layout in (_run05_b07(), _run05_b09()):
        taken = _markers_boxes(layout)
        if layout.target is not None:
            t = layout.target
            tag: Box = (t.tag_box_left, t.tag_box_top, t.tag_box_right, t.tag_box_bottom)
            assert _inside_band(tag)
            assert not any(_meet(tag, b) for b in taken)
            taken.append(tag)
        for n in layout.names:
            box: Box = (n.left, n.top, n.left + n.width, n.top + n.height)
            assert _inside_band(box), n.name
            assert not any(_meet(box, b) for b in taken), n.name
            taken.append(box)


def test_a_country_that_is_a_marker_is_not_named_twice() -> None:
    layout = _run05_b09()
    assert "Kuwait" not in {n.name for n in layout.names}
    assert "Saudi Arabia" in {n.name for n in layout.names}  # the repair's map is named too
    assert layout.target is None and layout.highlight == []  # no region named


def test_the_target_circle_and_tag_take_the_reference_cards_numbers() -> None:
    card = json.loads((INVENTORY_DIR / "ePTZVwipoAM.json").read_text(encoding="utf-8"))
    effects = {e["name"]: e for e in card["effects"]}
    circle, tag = effects["red_circle_india"]["motion"], effects["indus_war_tag"]["motion"]
    m = NUMBERS.map
    assert m.circle_draw_s == circle["entrance_s"] and m.circle_size == circle["size"]
    assert m.tag_slide_s == tag["entrance_s"]
    layout = _run05_b07()
    t = layout.target
    assert t is not None
    band_width = RIGHT - infographics.SAFE_LEFT
    assert t.radius <= m.circle_size * band_width / 2 + 1e-6
    assert t.draw_s == m.circle_draw_s and t.slide_s == m.tag_slide_s
    assert t.rotate_deg == m.tag_tilt_deg != 0
    assert (t.color, t.stroke_px) == (m.circle_color, m.circle_px)
    riyadh = GAZETTEER.lookup("Saudi Arabia")
    assert riyadh is not None
    projection = geo.Mercator(layout.scale, layout.center_lon, layout.center_merc,
                              layout.center_x, layout.center_y)  # fmt: skip
    assert (t.x, t.y) == pytest.approx(projection.project(riyadh.lon, riyadh.lat))


def test_a_marker_with_no_name_is_dropped_never_drawn() -> None:
    recipe = infographics.MapRecipe(
        region="Saudi Arabia",
        markers=(infographics.MapMarkerRecipe("Riyadh"), infographics.MapMarkerRecipe("  ")),
    )
    layout = _resolve(recipe)
    assert [m.name for m in layout.markers] == ["Riyadh"]
    beat = Beat.model_validate({
        "id": "b07", "start": 0.0, "end": 2.0, "mode": "off", "kind": "map",
        "map": MapPlan(region="Saudi Arabia",
                       markers=[MapMarker(name="Riyadh"), MapMarker(name="")]).model_dump(),
    })  # fmt: skip
    assert [m.name for m in infographics.map_recipe(beat).markers] == ["Riyadh"]


def test_the_object_stops_beside_the_endpoint_dot_never_on_it() -> None:
    layout = _run05_b09(overlays=("pin_drop", "route_arrow", "object_path"), length_s=3.8)
    assert 0 < layout.object_end_t < 1
    last = layout.segments[-1]
    total = layout.route_length_px
    # the object's centre at object_end_t, on the last leg
    along = (layout.object_end_t - last.t0) / (last.t1 - last.t0)
    x = last.x0 + (last.x1 - last.x0) * along
    y = last.y0 + (last.y1 - last.y0) * along
    end = layout.markers[-1]
    clear = layout.dot_px / 2 + layout.ring_px + layout.object_px / 2
    assert math.dist((x, y), (end.x, end.y)) >= clear - 1e-6
    assert total > clear


def _luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_land_and_sea_can_be_told_apart_on_a_phone() -> None:
    for name in ("explainer", "fastfacts", "footage", "vishva", "hitech"):
        spec = render.loaded_styles()[name]
        m = infographics.numbers_for(spec).map
        for sea in spec.palette.gradient:
            assert _contrast(m.land, sea) >= 3.0, (name, m.land, sea)
        assert _contrast(m.highlight, m.land) >= 1.5, (name, m.highlight, m.land)
        assert _contrast(m.name_color, m.land) >= 4.5, (name, m.name_color, m.land)


def test_the_tag_and_the_names_keep_clear_of_the_beats_stamp() -> None:
    # run05 b07: the stamp "प्राइम मिनिस्टर + किंग" landed across the circle's top rim
    stamp: Box = (76.0, 520.0, 940.0, 720.0)
    recipe = infographics.MapRecipe(
        region="Saudi Arabia", markers=(infographics.MapMarkerRecipe("Riyadh"),)
    )
    layout = _resolve(recipe, overlays=("pin_drop",), length_s=2.9, avoid=(stamp,))
    t = layout.target
    assert t is not None and t.tag == "Saudi Arabia"
    assert not _meet((t.tag_box_left, t.tag_box_top, t.tag_box_right, t.tag_box_bottom), stamp)
    for n in layout.names:
        assert not _meet((n.left, n.top, n.left + n.width, n.top + n.height), stamp), n.name


def test_the_render_passes_the_stamp_to_the_map() -> None:
    from shortsmith.contracts import StampSpec  # noqa: PLC0415

    beat = Beat.model_validate({
        "id": "b07", "start": 0.0, "end": 2.9, "mode": "off", "kind": "map",
        "overlays": ["pin_drop"],
        "map": MapPlan(region="Saudi Arabia", markers=[MapMarker(name="Riyadh")]).model_dump(),
    })  # fmt: skip
    numbers = render.style_numbers("explainer")
    stamp: StampSpec = render.stamp_spec("PRIME MINISTER + KING", numbers=numbers)
    box = render.stamp_box(stamp)
    layout = render.map_layout(beat, numbers=numbers, geocoder=GAZETTEER, stamp=stamp)
    assert layout is not None and layout.target is not None
    t = layout.target
    assert not _meet((t.tag_box_left, t.tag_box_top, t.tag_box_right, t.tag_box_bottom),
                     (box.left, box.top, box.left + box.width, box.top + box.height))  # fmt: skip
