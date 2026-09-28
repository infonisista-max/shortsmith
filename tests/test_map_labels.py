"""Map labels (ticket 072; decision 9.3, run04 QA 29 Sep 2026): the pill says the name the
planner wrote, never the gazetteer's canonical one; a collision pass flips or steps a pill
until it covers no other pill and no other marker's dot inside the safe area, or the
build fails with `LayoutError` naming the markers.

Run04's b20 (vishva) is the case: "United States" became "United States of America", a
504 px pill that covered Greece's pill and dot on a phone.
"""

from __future__ import annotations

import random
import string

import pytest

from shortsmith import geo, infographics, render
from shortsmith.contracts import MapLayout, MapMarkerLayout

VISHVA = render.loaded_styles()["vishva"]
NUMBERS = infographics.numbers_for(VISHVA)
CARD_LIMIT = VISHVA.broll.card_max_bottom_y
RIGHT = infographics.WIDTH - infographics.SAFE_RIGHT_PX

Box = tuple[float, float, float, float]  # left, top, right, bottom


def _pill(m: MapMarkerLayout) -> Box:
    return (m.label_left, m.label_top, m.label_left + m.label_width, m.label_top + m.label_height)


def _dot(m: MapMarkerLayout, layout: MapLayout) -> Box:
    r = layout.dot_px / 2 + layout.ring_px
    return (m.x - r, m.y - r, m.x + r, m.y + r)


def _meet(a: Box, b: Box) -> bool:
    eps = 1e-6
    return a[0] < b[2] - eps and b[0] < a[2] - eps and a[1] < b[3] - eps and b[1] < a[3] - eps


def _assert_clear(layout: MapLayout) -> None:
    for i, m in enumerate(layout.markers):
        left, top, right, bottom = _pill(m)
        assert left >= infographics.SAFE_LEFT - 1e-6 and right <= RIGHT + 1e-6, m.name
        assert top >= infographics.SAFE_TOP_PX - 1e-6 and bottom <= CARD_LIMIT + 1e-6, m.name
        for j, other in enumerate(layout.markers):
            if i == j:
                continue
            assert not _meet(_pill(m), _pill(other)), (m.name, other.name)
            assert not _meet(_pill(m), _dot(other, layout)), (m.name, "dot of", other.name)


def _run04_b20() -> MapLayout:
    recipe = infographics.MapRecipe(
        bbox=(-125.0, 10.0, 60.0, 65.0),
        markers=tuple(infographics.MapMarkerRecipe(n)
                      for n in ("Riyadh", "Poland", "Greece", "United States")),
    )  # fmt: skip
    return infographics.resolve_map(recipe, numbers=NUMBERS, geocoder=geo.GazetteerGeocoder())


def test_run04_b20_labels_say_the_names_as_written_and_never_overlap() -> None:
    layout = _run04_b20()
    assert [m.name for m in layout.markers] == ["Riyadh", "Poland", "Greece", "United States"]
    usa = layout.markers[3]
    assert (usa.lat, usa.lon) == pytest.approx((39.538479, -97.482602))  # the coordinate only
    _assert_clear(layout)


def test_a_pill_that_would_cover_another_is_flipped_then_stepped() -> None:
    # two dots on one row a short way apart: the western pill runs right into the eastern
    # dot and pill, so the pass moves it
    places = (
        geo.Place("West", "city", 30.0, 10.0, source="fake"),
        geo.Place("East", "city", 30.0, 14.0, source="fake"),
    )
    recipe = infographics.MapRecipe(
        bbox=(-40.0, 0.0, 60.0, 60.0),
        markers=(infographics.MapMarkerRecipe("East"), infographics.MapMarkerRecipe("West")),
    )  # fmt: skip
    layout = infographics.resolve_map(recipe, numbers=NUMBERS, geocoder=geo.FakeGeocoder(places))
    _assert_clear(layout)
    east, west = layout.markers
    assert east.label_left > east.x  # the first pill keeps its place
    assert west.label_left + west.label_width < west.x  # flipped to the free side


def test_the_step_is_the_styles_number_in_every_style_with_a_map() -> None:
    for name, spec in render.loaded_styles().items():
        row = spec.broll.motion.get("map")
        if row is None:
            continue
        numbers = infographics.numbers_for(spec).map
        assert numbers.label_step_px == float(row["label_step_px"]) > 0, name
        assert numbers.label_steps_max == int(row["label_steps_max"]) >= 1, name


def _random_map(rng: random.Random) -> infographics.MapRecipe:
    count = rng.randint(1, NUMBERS.map.markers_max)
    names = [
        "".join(rng.choice(string.ascii_letters) for _ in range(rng.randint(3, 18)))
        + f" {i}"
        for i in range(count)
    ]
    return infographics.MapRecipe(
        bbox=(0.0, 0.0, 40.0, 40.0),
        markers=tuple(infographics.MapMarkerRecipe(n) for n in names),
    )


def test_every_layout_the_pass_accepts_is_clear_and_a_refusal_names_the_markers() -> None:
    rng = random.Random(72)
    layers = geo.Layers(land=(), coast=(), borders=())  # the base is not under test here
    accepted = refused = 0
    for _ in range(300):
        recipe = _random_map(rng)
        places = [
            geo.Place(m.name, "city", rng.uniform(2.0, 38.0), rng.uniform(2.0, 38.0),
                      source="fake")
            for m in recipe.markers
        ]  # fmt: skip
        try:
            layout = infographics.resolve_map(
                recipe, numbers=NUMBERS, geocoder=geo.FakeGeocoder(places), layers=layers
            )
        except infographics.LayoutError as exc:
            refused += 1
            assert any(m.name in str(exc) for m in recipe.markers), str(exc)
            continue
        accepted += 1
        assert [m.name for m in layout.markers] == [m.name for m in recipe.markers]
        _assert_clear(layout)
    assert accepted > 0 and refused > 0


def test_a_set_that_cannot_be_separated_is_a_layout_error_naming_the_markers() -> None:
    # every dot on one point near the west edge, every name too long for the west side:
    # only the east side's few steps are left, fewer than the pills
    names = [f"Place {c} of a long name" for c in "ABCDEF"][: NUMBERS.map.markers_max]
    places = [geo.Place(n, "city", 20.0, 5.0, source="fake") for n in names]
    recipe = infographics.MapRecipe(
        bbox=(0.0, 0.0, 40.0, 40.0),
        markers=tuple(infographics.MapMarkerRecipe(n) for n in names),
    )
    with pytest.raises(infographics.LayoutError) as caught:
        infographics.resolve_map(recipe, numbers=NUMBERS, geocoder=geo.FakeGeocoder(places))
    assert isinstance(caught.value, infographics.InfographicError)
    for n in names:
        assert n in str(caught.value)
