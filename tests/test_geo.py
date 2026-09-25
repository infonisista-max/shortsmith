"""geo (ticket 020; decisions 9.3, 12.1, 13.1): the bundled Natural Earth data, the
gazetteer built from it, the geocoders behind one interface, and the projection and
clipping maths the map layout is built on.

The gazetteer build is tested on synthetic features shaped like the Natural Earth
columns it reads; the bundled `assets/geo/gazetteer.json` is then loaded for real, with
no network, and asked for the places the fake plan names. `NominatimGeocoder` is tested
against a recorded reply through `httpx.MockTransport` (12.1): request construction,
the cache under `work/geo/`, the one-request-per-second throttle, and a miss that stays
a miss. Projection maths is checked on known cities (Delhi is north and east of Mumbai;
the equator and the antimeridian land where Mercator puts them).
"""

from __future__ import annotations

import gzip
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from shortsmith import geo, geo_build
from shortsmith.config import Settings

# --- synthetic Natural Earth features -----------------------------------------------------


def _country(name: str, rings: list[list[list[float]]], **props: Any) -> dict[str, Any]:
    """A country feature with the columns the build reads; `rings` are exterior rings."""
    base = {
        "NAME": name, "NAME_LONG": name, "ADMIN": name, "FORMAL_EN": f"Republic of {name}",
        "NAME_EN": name, "NAME_HI": props.pop("hi", ""), "NAME_ALT": None, "ABBREV": name[:3],
        "NAME_SORT": name, "ISO_A3": props.pop("iso3", "-99"), "ISO_A2": props.pop("iso2", "-99"),
        "LABEL_X": props.pop("label_x", 0.0), "LABEL_Y": props.pop("label_y", 0.0),
        "CONTINENT": props.pop("continent", "Asia"),
        "SUBREGION": props.pop("subregion", "Southern Asia"),
        "REGION_WB": props.pop("region_wb", "South Asia"), "POP_EST": props.pop("pop", 1000),
    }  # fmt: skip
    base.update(props)
    geometry: dict[str, Any] = (
        {"type": "Polygon", "coordinates": rings[0:1]}
        if len(rings) == 1
        else {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}
    )
    return {"type": "Feature", "properties": base, "geometry": geometry}


def _square(x: float, y: float, size: float) -> list[list[float]]:
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]


def _state(name: str, admin: str, lon: float, lat: float, ring: list[list[float]],
           **props: Any) -> dict[str, Any]:  # fmt: skip
    base = {
        "name": name, "name_alt": None, "name_en": name, "name_hi": props.pop("hi", ""),
        "name_local": None, "woe_name": name, "gn_name": name, "admin": admin,
        "latitude": lat, "longitude": lon,
    }  # fmt: skip
    return {
        "type": "Feature",
        "properties": base,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def _city(name: str, admin: str, lon: float, lat: float, pop: int, **props: Any) -> dict[str, Any]:
    base = {
        "NAME": name, "NAMEASCII": name, "NAMEALT": props.pop("alt", None), "NAME_EN": name,
        "NAME_HI": props.pop("hi", ""), "MEGANAME": None, "NAMEPAR": None, "ADM0NAME": admin,
        "POP_MAX": pop, "LATITUDE": lat + 0.05, "LONGITUDE": lon + 0.05,  # the columns drift
    }  # fmt: skip
    return {
        "type": "Feature",
        "properties": base,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


INDIA = _country(
    "India",
    [_square(68.0, 8.0, 29.0), _square(92.0, 6.0, 0.5)],  # mainland plus a tiny island
    hi="भारत", iso3="IND", iso2="IN", label_x=79.4, label_y=22.7, pop=1_400_000_000,
)  # fmt: skip
NEPAL = _country("Nepal", [_square(80.0, 26.0, 8.0)], iso3="NPL", iso2="NP", label_x=84.0,
                 label_y=28.0, pop=30_000_000)  # fmt: skip
FRANCE = _country("France", [_square(-5.0, 42.0, 13.0)], continent="Europe",
                  subregion="Western Europe", region_wb="Europe & Central Asia", label_x=2.0,
                  label_y=46.0, pop=68_000_000)  # fmt: skip
STATES = [_state("Maharashtra", "India", 76.0, 19.5, _square(72.6, 15.6, 8.0), hi="महाराष्ट्र"),
          _state("Delhi", "India", 77.1, 28.6, _square(76.8, 28.4, 0.6))]  # fmt: skip
CITIES = [
    _city("Mumbai", "India", 72.876, 19.068, 18_978_000, alt="Bombay", hi="मुम्बई"),
    _city("Delhi", "India", 77.228, 28.672, 15_926_000, hi="दिल्ली"),
    _city("Victoria", "Canada", -123.37, 48.43, 300_000),
    _city("Victoria", "Seychelles", 55.45, -4.62, 22_000),
]


@pytest.fixture(scope="module")
def entries() -> list[dict[str, Any]]:
    return geo_build.build_gazetteer(countries=[INDIA, NEPAL, FRANCE], states=STATES, places=CITIES)


@pytest.fixture(scope="module")
def gazetteer(entries: list[dict[str, Any]]) -> geo.Gazetteer:
    return geo.Gazetteer(entries)


# --- the gazetteer build ---------------------------------------------------------------


def test_a_country_entry_takes_its_label_point_and_the_bbox_of_its_significant_land(
    gazetteer: geo.Gazetteer,
) -> None:
    india = gazetteer.lookup("India")
    assert india is not None and india.kind == "country"
    assert (india.lon, india.lat) == (79.4, 22.7)
    # the tiny island (a quarter of a square degree) does not widen the mainland's bbox
    assert india.bbox == (68.0, 8.0, 97.0, 37.0)
    assert india.population == 1_400_000_000


def test_countries_are_found_by_every_name_column_and_iso_code(gazetteer: geo.Gazetteer) -> None:
    for name in ("india", "Republic of India", "IND", "in", "भारत"):
        found = gazetteer.lookup(name)
        assert found is not None and found.name == "India", name
    # a -99 code is Natural Earth's "none", never an alias
    assert gazetteer.lookup("-99") is None


def test_continents_subregions_and_bank_regions_are_the_union_of_their_countries(
    gazetteer: geo.Gazetteer,
) -> None:
    asia = gazetteer.lookup("Asia")
    assert asia is not None and asia.kind == "region"
    assert asia.bbox == (68.0, 8.0, 97.0, 37.0)  # India and Nepal, not France
    europe = gazetteer.lookup("Western Europe")
    assert europe is not None and europe.bbox == (-5.0, 42.0, 8.0, 55.0)
    south_asia = gazetteer.lookup("South Asia")
    assert south_asia is not None and south_asia.bbox == asia.bbox
    world = gazetteer.lookup("World")
    assert world is not None and world.bbox == geo.WORLD_BBOX


def test_a_state_has_its_own_bbox_and_country(gazetteer: geo.Gazetteer) -> None:
    state = gazetteer.lookup("Maharashtra")
    assert state is not None and state.kind == "state" and state.country == "India"
    assert state.bbox == (72.6, 15.6, 80.6, 23.6)
    assert gazetteer.lookup("महाराष्ट्र") == state


def test_a_city_takes_the_geometry_point_not_the_drifting_columns(gazetteer: geo.Gazetteer) -> None:
    mumbai = gazetteer.lookup("Mumbai")
    assert mumbai is not None and mumbai.kind == "city"
    assert (mumbai.lon, mumbai.lat) == (72.876, 19.068)
    assert mumbai.bbox is None
    assert gazetteer.lookup("Bombay") == mumbai and gazetteer.lookup("मुम्बई") == mumbai


def test_lookup_ranks_country_over_state_over_city_and_bigger_cities_first(
    gazetteer: geo.Gazetteer,
) -> None:
    # "Delhi" is a state and a city; the region-sized answer wins, and it carries a bbox
    delhi = gazetteer.lookup("Delhi")
    assert delhi is not None and delhi.kind == "state" and delhi.bbox is not None
    # two Victorias: the bigger one
    victoria = gazetteer.lookup("Victoria")
    assert victoria is not None and victoria.country == "Canada"


def test_lookup_ignores_case_latin_accents_punctuation_and_spacing(
    gazetteer: geo.Gazetteer,
) -> None:
    assert gazetteer.lookup("  MUMBAI ") is not None
    assert gazetteer.lookup("mumbaí") is not None
    assert gazetteer.lookup("New-Delhi") is None  # no such place; a hyphen is a space
    assert geo.normalise("São Paulo") == "sao paulo"
    assert geo.normalise("Ma'arat al-Nu'man") == "maarat al numan"
    # Devanagari matras are combining marks too; they are never stripped
    assert geo.normalise("मुम्बई") == "मुम्बई"


def test_a_miss_is_none_never_a_guess(gazetteer: geo.Gazetteer) -> None:
    assert gazetteer.lookup("Atlantis") is None
    assert gazetteer.lookup("") is None


def test_the_gazetteer_round_trips_through_json(
    entries: list[dict[str, Any]], tmp_path: Path
) -> None:
    path = tmp_path / "gazetteer.json"
    geo_build.write_gazetteer(path, entries, version="test-1")
    loaded = geo.load_gazetteer(path)
    assert loaded.version == "test-1"
    assert loaded.lookup("Nepal") == geo.Gazetteer(entries).lookup("Nepal")


def test_a_drawing_layer_is_rewritten_gzipped_with_geometry_and_a_name_only(tmp_path: Path) -> None:
    raw = tmp_path / "ne_50m_admin_0_countries.geojson"
    raw.write_text(json.dumps({"type": "FeatureCollection", "features": [INDIA]}), encoding="utf-8")
    out = geo_build.write_layer(raw, tmp_path / "out" / "land.geojson.gz", keep=("NAME",))
    with gzip.open(out, "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["features"][0]["properties"] == {"NAME": "India"}
    assert data["features"][0]["geometry"]["type"] == "MultiPolygon"


# --- the bundled data, loaded with no network (13.1) ---------------------------------------


def test_the_bundled_gazetteer_knows_the_fake_plans_places() -> None:
    bundled = geo.default_gazetteer()
    assert bundled.version
    delhi, mumbai, india = (bundled.lookup(n) for n in ("Delhi", "Mumbai", "India"))
    assert delhi is not None and mumbai is not None and india is not None
    assert delhi.lat > mumbai.lat and delhi.lon > mumbai.lon
    assert india.kind == "country" and india.bbox is not None
    west, south, east, north = india.bbox
    assert west < mumbai.lon < east and south < mumbai.lat < north
    assert bundled.lookup("Maharashtra") is not None  # admin-1 states are in (operator rider)
    assert bundled.lookup("Southern Asia") is not None
    assert len(bundled.entries) > 7000


def test_the_bundled_layers_load_with_land_coast_and_borders() -> None:
    layers = geo.load_layers()
    assert len(layers.land) > 200 and len(layers.coast) > 1000 and len(layers.borders) > 300
    ring = layers.land[0]
    assert len(ring.points) >= 4 and ring.bbox[0] <= ring.bbox[2]


def test_the_geo_folder_carries_its_licence_note() -> None:
    licence = (geo.GEO_DIR / "LICENSE").read_text(encoding="utf-8")
    assert "Natural Earth" in licence and "public domain" in licence.lower()
    assert (geo.GEO_DIR / "README.md").is_file()


# --- the geocoders behind one interface (12.1) --------------------------------------------


def test_the_fake_geocoder_holds_ten_places_and_misses_the_rest() -> None:
    fake = geo.FakeGeocoder()
    assert len(geo.FAKE_PLACES) == 10
    delhi = fake.lookup("delhi")
    assert delhi is not None and delhi.source == "fake"
    india = fake.lookup("India")
    assert india is not None and india.bbox is not None
    assert fake.lookup("Atlantis") is None
    assert fake.for_job(Path("anywhere")) is fake


def test_the_gazetteer_geocoder_wraps_a_gazetteer(gazetteer: geo.Gazetteer) -> None:
    coder = geo.GazetteerGeocoder(gazetteer)
    found = coder.lookup("Nepal")
    assert found is not None and found.source == "gazetteer"
    assert coder.for_job(Path("anywhere")) is coder


NOMINATIM_REPLY = [
    {
        "place_id": 1, "licence": "Data © OpenStreetMap contributors, ODbL 1.0.",
        "osm_type": "relation", "osm_id": 1, "lat": "18.9733536", "lon": "72.8281049",
        "category": "boundary", "type": "administrative", "importance": 0.8,
        "display_name": "Mumbai, Mumbai Suburban, Maharashtra, India",
        "boundingbox": ["18.8928676", "19.2716339", "72.7758787", "72.9864994"],
    }
]  # fmt: skip


class _Nominatim:
    """A mock Nominatim: records every request, answers Mumbai, misses everything else."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.params.get("q", "").lower().startswith("mumbai"):
            return httpx.Response(200, json=NOMINATIM_REPLY)
        return httpx.Response(200, json=[])


def _no_sleep(_s: float) -> None:
    pass


def _nominatim(
    server: _Nominatim, tmp_path: Path, *, sleep: Callable[[float], None] = _no_sleep,
    clock: Callable[[], float] | None = None,
) -> geo.NominatimGeocoder:  # fmt: skip
    client = httpx.Client(transport=httpx.MockTransport(server.handle))
    coder = geo.NominatimGeocoder(
        "https://nominatim.example.org", client=client, sleep=sleep,
        clock=clock if clock is not None else time.monotonic,
    )  # fmt: skip
    bound = coder.for_job(tmp_path)
    assert isinstance(bound, geo.NominatimGeocoder)
    return bound


def test_nominatim_builds_the_documented_request_and_parses_the_reply(tmp_path: Path) -> None:
    server = _Nominatim()
    coder = _nominatim(server, tmp_path)
    found = coder.lookup("Mumbai")
    assert found is not None
    assert (found.lat, found.lon) == pytest.approx((18.9733536, 72.8281049))
    assert found.bbox == pytest.approx((72.7758787, 18.8928676, 72.9864994, 19.2716339))
    assert found.name == "Mumbai" and found.source == "nominatim"
    assert found.source_url.startswith("https://nominatim.example.org/search?")
    (request,) = server.requests
    assert request.url.path == "/search"
    assert request.url.params["q"] == "Mumbai" and request.url.params["format"] == "jsonv2"
    assert request.url.params["limit"] == "1"
    assert request.headers["User-Agent"] == geo.USER_AGENT


def test_nominatim_caches_hits_and_misses_per_job_under_work_geo(tmp_path: Path) -> None:
    server = _Nominatim()
    coder = _nominatim(server, tmp_path)
    assert coder.lookup("Mumbai") is not None
    assert coder.lookup("Atlantis") is None
    assert coder.lookup("mumbai") is not None  # the same name, normalised
    assert coder.lookup("Atlantis") is None
    assert len(server.requests) == 2
    cache = tmp_path / "work" / "geo" / "nominatim.json"
    assert cache.is_file()
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data["atlantis"] is None and data["mumbai"]["lat"] == pytest.approx(18.9733536)
    # a fresh geocoder on the same job reads the cache and never asks again
    again = _nominatim(server, tmp_path)
    assert again.lookup("Mumbai") is not None and again.lookup("Atlantis") is None
    assert len(server.requests) == 2


def test_nominatim_waits_a_second_between_requests(tmp_path: Path) -> None:
    server = _Nominatim()
    now = [100.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    coder = _nominatim(server, tmp_path, sleep=sleep, clock=lambda: now[0])
    coder.lookup("Mumbai")
    now[0] += 0.25
    coder.lookup("Atlantis")
    coder.lookup("Nowhere")
    assert slept == pytest.approx([0.75, 1.0])


def test_a_nominatim_failure_is_an_error_naming_the_place_never_a_point(tmp_path: Path) -> None:
    def down(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="busy")

    client = httpx.Client(transport=httpx.MockTransport(down))
    coder = geo.NominatimGeocoder("https://nominatim.example.org", client=client,
                                  sleep=_no_sleep).for_job(tmp_path)  # fmt: skip
    with pytest.raises(geo.GeocodeError, match="Mumbai"):
        coder.lookup("Mumbai")


def test_the_chain_asks_the_gazetteer_first_and_the_fallback_on_a_miss(
    gazetteer: geo.Gazetteer, tmp_path: Path
) -> None:
    server = _Nominatim()
    chain = geo.ChainGeocoder([
        geo.GazetteerGeocoder(gazetteer),
        geo.NominatimGeocoder("https://nominatim.example.org",
                              client=httpx.Client(transport=httpx.MockTransport(server.handle)),
                              sleep=_no_sleep),
    ]).for_job(tmp_path)  # fmt: skip
    mumbai = chain.lookup("Mumbai")
    assert mumbai is not None and mumbai.source == "gazetteer"
    assert server.requests == []
    assert chain.lookup("Mumbai Suburban") is not None  # the mock answers "mumbai..."
    assert len(server.requests) == 1
    assert chain.lookup("Atlantis") is None


def test_from_settings_is_the_gazetteer_alone_unless_the_fallback_is_enabled() -> None:
    off = geo.from_settings(Settings(_env_file=None))  # pyright: ignore[reportCallIssue]
    assert isinstance(off, geo.GazetteerGeocoder)
    on = geo.from_settings(
        Settings(_env_file=None, geocoder_fallback="nominatim")  # pyright: ignore[reportCallIssue]
    )
    assert isinstance(on, geo.ChainGeocoder)
    assert [type(c) for c in on.geocoders] == [geo.GazetteerGeocoder, geo.NominatimGeocoder]


def test_settings_default_to_no_fallback_and_the_public_nominatim_url() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.geocoder_fallback == "none"
    assert settings.nominatim_url == "https://nominatim.openstreetmap.org"


# --- projection and clipping maths ---------------------------------------------------------

BOX = (60.0, 330.0, 880.0, 910.0)  # left, top, width, height


def test_mercator_fits_the_bbox_inside_the_box_and_centres_the_leftover() -> None:
    projection = geo.Mercator.fit((68.0, 8.0, 97.0, 37.0), BOX)
    x0, y0 = projection.project(68.0, 37.0)  # north-west corner
    x1, y1 = projection.project(97.0, 8.0)  # south-east corner
    assert 60.0 - 1e-6 <= x0 < x1 <= 940.0 + 1e-6
    assert 330.0 - 1e-6 <= y0 < y1 <= 1240.0 + 1e-6
    # the bbox is taller than wide in Mercator, so the height is filled and x is centred
    assert y0 == pytest.approx(330.0) and y1 == pytest.approx(1240.0)
    assert (x0 - 60.0) == pytest.approx(940.0 - x1)


def test_known_cities_land_where_mercator_puts_them() -> None:
    projection = geo.Mercator.fit((68.0, 8.0, 97.0, 37.0), BOX)
    dx, dy = projection.project(77.228, 28.672)  # Delhi
    mx, my = projection.project(72.876, 19.068)  # Mumbai
    assert dx > mx and dy < my  # Delhi is east of and north of Mumbai
    # Mercator stretches the north: one degree of latitude near Delhi is longer than one
    # near Mumbai, and longitude is linear
    _, y_a = projection.project(77.0, 28.0)
    _, y_b = projection.project(77.0, 29.0)
    _, y_c = projection.project(77.0, 19.0)
    _, y_d = projection.project(77.0, 20.0)
    assert (y_a - y_b) > (y_c - y_d)
    x_a, _ = projection.project(70.0, 20.0)
    x_b, _ = projection.project(71.0, 20.0)
    x_c, _ = projection.project(95.0, 20.0)
    x_d, _ = projection.project(96.0, 20.0)
    assert (x_b - x_a) == pytest.approx(x_d - x_c)


def test_the_equator_and_the_prime_meridian_sit_at_the_centre_of_a_symmetric_box() -> None:
    projection = geo.Mercator.fit((-40.0, -30.0, 40.0, 30.0), BOX)
    x, y = projection.project(0.0, 0.0)
    assert (x, y) == pytest.approx((60.0 + 440.0, 330.0 + 455.0))
    lon, lat = projection.invert(x, y)
    assert (lon, lat) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_projection_inverts_and_clamps_the_poles() -> None:
    projection = geo.Mercator.fit((68.0, 8.0, 97.0, 37.0), BOX)
    for lon, lat in ((77.228, 28.672), (-123.37, 48.43), (151.2, -33.9)):
        assert projection.invert(*projection.project(lon, lat)) == pytest.approx((lon, lat))
    _, top = projection.project(0.0, 90.0)
    _, clamped = projection.project(0.0, geo.MAX_LAT)
    assert top == clamped


def test_a_ring_is_clipped_to_the_rectangle_and_a_far_one_dropped() -> None:
    rect = (0.0, 0.0, 100.0, 100.0)
    square = [(50.0, 50.0), (150.0, 50.0), (150.0, 150.0), (50.0, 150.0), (50.0, 50.0)]
    clipped = geo.clip_ring(square, rect)
    assert set(clipped) == {(50.0, 50.0), (100.0, 50.0), (100.0, 100.0), (50.0, 100.0)}
    far = [(200.0, 200.0), (300.0, 200.0), (300.0, 300.0), (200.0, 200.0)]
    assert geo.clip_ring(far, rect) == []


def test_a_line_is_cut_into_the_pieces_inside_the_rectangle() -> None:
    rect = (0.0, 0.0, 100.0, 100.0)
    line = [(-50.0, 50.0), (50.0, 50.0), (150.0, 50.0), (150.0, 80.0), (50.0, 80.0)]
    pieces = geo.clip_line(line, rect)
    assert len(pieces) == 2
    assert pieces[0][0] == pytest.approx((0.0, 50.0))
    assert pieces[0][-1] == pytest.approx((100.0, 50.0))
    assert pieces[1][0] == pytest.approx((100.0, 80.0))
    assert pieces[1][-1] == (50.0, 80.0)
    assert geo.clip_line([(200.0, 200.0), (300.0, 300.0)], rect) == []


def test_svg_paths_round_to_a_tenth_and_drop_sub_pixel_steps() -> None:
    ring = [(10.0, 10.0), (10.3, 10.2), (60.04, 10.0), (60.0, 60.0), (10.0, 60.0), (10.0, 10.0)]
    assert geo.svg_path(ring, close=True) == "M10 10L60 10L60 60L10 60Z"
    assert geo.svg_path([(1.26, 2.0), (30.0, 40.56)], close=False) == "M1.3 2L30 40.6"
    assert geo.svg_path([(1.0, 1.0)], close=False) == ""


def test_base_paths_for_a_region_hold_only_what_the_frame_can_show() -> None:
    """The India crop draws India's land and the borders on its frontier, none of the
    Americas, and every path string is a pixel path inside the clip rectangle."""
    projection = geo.Mercator.fit((68.0, 8.0, 97.0, 37.0), BOX)
    rect = (-100.0, -100.0, 1180.0, 2020.0)
    paths = geo.base_paths(geo.load_layers(), projection, rect)
    assert paths.land and paths.coast and paths.borders
    assert all(p.startswith("M") for p in paths.land + paths.coast + paths.borders)
    assert all(p.endswith("Z") for p in paths.land)
    assert not any(p.endswith("Z") for p in paths.coast)
    # the bundled layers name their land: India is in the crop, Brazil is not
    assert "India" in paths.land_names and "Brazil" not in paths.land_names
    total = sum(len(p) for p in paths.land + paths.coast + paths.borders)
    assert total < 400_000  # a region-sized crop stays a small render spec
