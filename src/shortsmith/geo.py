"""Bundled geodata, the gazetteer and the geocoders (ticket 020; decisions 9.3, 12.1,
13.1), plus the projection and clipping maths `infographics.resolve_map` lays a map
out with.

Everything the map base needs is under `assets/geo/` and loads with no network: three
Natural Earth 1:50m layers rewritten gzipped (`land` from admin-0 countries, `coast`,
`borders` from the land boundary lines) and `gazetteer.json`, built by `geo_build` from
the countries layer, the admin-1 states layer and the 1:10m populated places. Every
place is a name, a kind (`country`, `region`, `state`, `city`), a point and, for an area,
a bbox; a name is found by any of its columns (English, local, Hindi, ISO codes) after
`normalise`, and a name that is both a state and a city ("Delhi") answers with the
area-sized one, so a `region` gets a bbox and a marker still gets a point.

The geocoders share one interface (12.1): `GazetteerGeocoder` is the bundled table,
`NominatimGeocoder` the network fallback (one request a second, the documented
User-Agent, every hit and miss cached under the job's `work/geo/`, a failure an error
naming the place), `ChainGeocoder` asks them in order, and `FakeGeocoder` holds ten
places for tests and the smoke. The planner is never trusted for coordinates (9.3): a
marker's point comes from here or the build fails.

`Mercator` is the projection (Web-Mercator maths, latitude clamped at `MAX_LAT`),
`fit` to a bbox inside a pixel box; `clip_ring` / `clip_line` cut the projected
geometry to the frame (Sutherland-Hodgman and Liang-Barsky against an axis-aligned
rectangle), and `svg_path` writes it as an SVG path string the `map` component draws.
"""

from __future__ import annotations

import gzip
import json
import math
import time
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from typing import Any, Literal

import httpx

from shortsmith.config import Settings

GEO_DIR = Path(__file__).resolve().parents[2] / "assets" / "geo"
LAYER_FILES: Mapping[str, str] = {
    "land": "ne_50m_admin_0_countries.geojson.gz",
    "coast": "ne_50m_coastline.geojson.gz",
    "borders": "ne_50m_admin_0_boundary_lines_land.geojson.gz",
}
GAZETTEER_FILE = "gazetteer.json"
CACHE_DIR = Path("work") / "geo"  # under the job directory
CACHE_FILE = "nominatim.json"
# Nominatim's usage policy: identify the application, at most one request a second.
USER_AGENT = "shortsmith/0.1 (self-hosted YouTube Shorts editor; single operator)"
NOMINATIM_MIN_INTERVAL_S = 1.0
NOMINATIM_TIMEOUT_S = 20.0
WORLD_BBOX: BBox = (-180.0, -60.0, 180.0, 80.0)
MAX_LAT = 85.05113  # Web Mercator's edge; the poles are not on the map

PlaceKind = Literal["country", "region", "state", "city", "place"]
# The order a shared name resolves in: the area-sized answer first, so a region name
# gets a bbox; among cities the biggest.
KIND_RANK: Mapping[str, int] = {"country": 0, "region": 1, "state": 2, "city": 3, "place": 4}
BBox = tuple[float, float, float, float]  # west, south, east, north
Point = tuple[float, float]  # x, y in pixels, or lon, lat in degrees
Rect = tuple[float, float, float, float]  # left, top, width, height


class GeocodeError(RuntimeError):
    """The fallback could not answer for a place: a network or service failure. Never
    a miss (a miss is None) and never a guessed point."""


# --- places and the gazetteer ------------------------------------------------------------


@dataclass(frozen=True)
class Place:
    """One geocoded name: where it is and, for an area, how far it reaches."""

    name: str
    kind: PlaceKind
    lat: float
    lon: float
    country: str = ""
    bbox: BBox | None = None
    population: int = 0
    source: str = "gazetteer"
    source_url: str = ""


_LATIN_COMBINING = range(0x0300, 0x0370)


def normalise(name: str) -> str:
    """The key a name is looked up by: NFKD, Latin diacritics dropped (a Devanagari
    matra is a combining mark too, and stays), case folded, punctuation to spaces,
    apostrophes removed, whitespace collapsed."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if ord(ch) not in _LATIN_COMBINING)
    text = text.replace("'", "").replace("’", "").casefold()
    text = "".join(
        ch if ch.isalnum() or ch.isspace() or unicodedata.category(ch).startswith("M") else " "
        for ch in text
    )
    return " ".join(text.split())


def _place(entry: Mapping[str, Any]) -> Place:
    bbox = entry.get("bbox")
    return Place(
        name=str(entry["name"]),
        kind=entry["kind"],
        lat=float(entry["lat"]),
        lon=float(entry["lon"]),
        country=str(entry.get("country", "")),
        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])) if bbox else None,
        population=int(entry.get("pop", 0)),
    )


class Gazetteer:
    """The place table with its name index; `entries` are the JSON rows `geo_build`
    wrote (`name`, `kind`, `country`, `lat`, `lon`, `pop`, `aliases`, `bbox`)."""

    def __init__(self, entries: Sequence[Mapping[str, Any]], *, version: str = "") -> None:
        self.entries = list(entries)
        self.version = version
        self._index: dict[str, list[int]] = {}
        for i, entry in enumerate(self.entries):
            names = [str(entry["name"]), *(str(a) for a in entry.get("aliases", []))]
            for key in {normalise(n) for n in names}:
                if key:
                    self._index.setdefault(key, []).append(i)

    def lookup(self, name: str) -> Place | None:
        key = normalise(name)
        if not key or key not in self._index:
            return None
        best = min(
            (self.entries[i] for i in self._index[key]),
            key=lambda e: (KIND_RANK[e["kind"]], -int(e.get("pop", 0)), str(e["name"])),
        )
        return _place(best)


def load_gazetteer(path: Path | None = None) -> Gazetteer:
    path = path or GEO_DIR / GAZETTEER_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    return Gazetteer(data["places"], version=str(data.get("version", "")))


@cache
def default_gazetteer() -> Gazetteer:
    """The bundled table, loaded once per process."""
    return load_gazetteer()


# --- the geocoders (12.1) -----------------------------------------------------------------


class Geocoder(ABC):
    """`lookup(name)` is the place or None on a miss; a miss is never a guess (9.3).
    `for_job(job_dir)` is the geocoder bound to one job's cache (the fallback's); the
    others return themselves."""

    @abstractmethod
    def lookup(self, name: str) -> Place | None: ...

    def for_job(self, job_dir: Path) -> Geocoder:
        return self


class GazetteerGeocoder(Geocoder):
    def __init__(self, gazetteer: Gazetteer | None = None) -> None:
        self._gazetteer = gazetteer

    @property
    def gazetteer(self) -> Gazetteer:
        if self._gazetteer is None:
            self._gazetteer = default_gazetteer()
        return self._gazetteer

    def lookup(self, name: str) -> Place | None:
        return self.gazetteer.lookup(name)


FAKE_PLACES: tuple[Place, ...] = (
    Place("India", "country", 22.7, 79.4, "India", (68.1, 6.7, 97.4, 35.5), 1_400_000_000, "fake"),
    Place("Delhi", "city", 28.672, 77.228, "India", None, 15_926_000, "fake"),
    Place("Mumbai", "city", 19.068, 72.876, "India", None, 18_978_000, "fake"),
    Place("Chennai", "city", 13.083, 80.283, "India", None, 7_163_000, "fake"),
    Place("Kolkata", "city", 22.567, 88.367, "India", None, 14_787_000, "fake"),
    Place("Bengaluru", "city", 12.967, 77.567, "India", None, 6_787_000, "fake"),
    Place("London", "city", 51.5, -0.117, "United Kingdom", None, 8_567_000, "fake"),
    Place("New York", "city", 40.75, -73.98, "United States of America", None, 19_040_000, "fake"),
    Place("Tokyo", "city", 35.685, 139.751, "Japan", None, 35_676_000, "fake"),
    Place("Dubai", "city", 25.23, 55.28, "United Arab Emirates", None, 1_379_000, "fake"),
)


class FakeGeocoder(Geocoder):
    """Ten places, no network: the fake plan's region and markers plus a few more."""

    def __init__(self, places: Sequence[Place] = FAKE_PLACES) -> None:
        self._table = {normalise(p.name): p for p in places}

    def lookup(self, name: str) -> Place | None:
        return self._table.get(normalise(name))


class NominatimGeocoder(Geocoder):
    """The network fallback: `GET <base_url>/search?q=<name>&format=jsonv2&limit=1`
    with the documented User-Agent, at most one request a second (`sleep` and `clock`
    are injectable), every answer - hit or miss - cached in `<job>/work/geo/nominatim.json`
    so a retry of the job asks nothing twice. Unbound to a job, it caches in memory."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        cache_dir: Path | None = None,
        user_agent: str = USER_AGENT,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval_s: float = NOMINATIM_MIN_INTERVAL_S,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.cache_dir = cache_dir
        self._user_agent = user_agent
        self._sleep = sleep
        self._clock = clock
        self._min_interval_s = min_interval_s
        self._last: float | None = None
        self._memory: dict[str, dict[str, Any] | None] = {}

    def for_job(self, job_dir: Path) -> Geocoder:
        bound = NominatimGeocoder(
            self.base_url, client=self._client, cache_dir=job_dir / CACHE_DIR,
            user_agent=self._user_agent, sleep=self._sleep, clock=self._clock,
            min_interval_s=self._min_interval_s,
        )  # fmt: skip
        return bound

    # the cache

    def _cache_path(self) -> Path | None:
        return self.cache_dir / CACHE_FILE if self.cache_dir is not None else None

    def _read_cache(self) -> dict[str, dict[str, Any] | None]:
        path = self._cache_path()
        if path is None:
            return self._memory
        if path.is_file():
            loaded: dict[str, dict[str, Any] | None] = json.loads(path.read_text(encoding="utf-8"))
            return loaded
        return {}

    def _write_cache(self, cache: dict[str, dict[str, Any] | None]) -> None:
        path = self._cache_path()
        if path is None:
            self._memory = cache
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

    # the request

    def _throttle(self) -> None:
        now = self._clock()
        if self._last is not None:
            wait = self._min_interval_s - (now - self._last)
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
        self._last = now

    def _ask(self, name: str) -> dict[str, Any] | None:
        self._throttle()
        params = {"q": name, "format": "jsonv2", "limit": "1"}
        headers = {"User-Agent": self._user_agent, "Accept-Language": "en"}
        try:
            if self._client is not None:
                response = self._client.get(f"{self.base_url}/search", params=params,
                                            headers=headers)  # fmt: skip
            else:
                with httpx.Client(timeout=NOMINATIM_TIMEOUT_S, follow_redirects=True) as owned:
                    response = owned.get(f"{self.base_url}/search", params=params,
                                         headers=headers)  # fmt: skip
            response.raise_for_status()
            rows: list[dict[str, Any]] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GeocodeError(f"Nominatim could not answer for {name!r}: {exc}") from None
        if not rows:
            return None
        row = rows[0]
        south, north, west, east = (float(v) for v in row["boundingbox"])
        return {
            "name": str(row.get("display_name", name)).split(",")[0].strip() or name,
            "kind": "place",
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "bbox": [west, south, east, north],
            "source_url": str(response.url),
        }

    def lookup(self, name: str) -> Place | None:
        key = normalise(name)
        if not key:
            return None
        cache = self._read_cache()
        if key not in cache:
            cache[key] = self._ask(name.strip())
            self._write_cache(cache)
        entry = cache[key]
        if entry is None:
            return None
        url = str(entry.get("source_url", ""))
        return replace(_place(entry), source="nominatim", source_url=url)


class ChainGeocoder(Geocoder):
    """The geocoders in order; the first hit answers."""

    def __init__(self, geocoders: Sequence[Geocoder]) -> None:
        self.geocoders = list(geocoders)

    def lookup(self, name: str) -> Place | None:
        for coder in self.geocoders:
            found = coder.lookup(name)
            if found is not None:
                return found
        return None

    def for_job(self, job_dir: Path) -> Geocoder:
        return ChainGeocoder([c.for_job(job_dir) for c in self.geocoders])


def from_settings(settings: Settings) -> Geocoder:
    """The bundled gazetteer, with Nominatim behind it when `GEOCODER_FALLBACK=nominatim`."""
    gazetteer = GazetteerGeocoder()
    if settings.geocoder_fallback == "nominatim":
        return ChainGeocoder([gazetteer, NominatimGeocoder(settings.nominatim_url)])
    return gazetteer


# --- the drawing layers -----------------------------------------------------------------


@dataclass(frozen=True)
class Shape:
    """One ring or line of a layer in degrees, with its bbox for the quick reject."""

    points: tuple[Point, ...]
    bbox: BBox
    name: str = ""


@dataclass(frozen=True)
class Layers:
    land: tuple[Shape, ...]  # exterior rings of the country polygons
    coast: tuple[Shape, ...]
    borders: tuple[Shape, ...]


def _shape(coords: Sequence[Sequence[float]], name: str = "") -> Shape:
    points = tuple((float(c[0]), float(c[1])) for c in coords)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return Shape(points, (min(xs), min(ys), max(xs), max(ys)), name)


Coords = list[Any]


def _shapes(feature: Mapping[str, Any], *, rings: bool) -> list[Shape]:
    geometry: Mapping[str, Any] = feature.get("geometry") or {}
    properties: Mapping[str, Any] = feature.get("properties") or {}
    kind = str(geometry.get("type", ""))
    coords: Coords = geometry.get("coordinates", [])
    name = str(properties.get("NAME") or "")
    if rings:
        polygons: list[Coords] = (
            coords if kind == "MultiPolygon" else [coords] if kind == "Polygon" else []
        )
        return [_shape(poly[0], name) for poly in polygons if poly]
    lines: list[Coords] = (
        coords if kind == "MultiLineString" else [coords] if kind == "LineString" else []
    )
    return [_shape(line, name) for line in lines if len(line) >= 2]


def load_layer(path: Path, *, rings: bool) -> tuple[Shape, ...]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    return tuple(s for f in data["features"] for s in _shapes(f, rings=rings))


@cache
def load_layers(geo_dir: Path = GEO_DIR) -> Layers:
    """The three bundled layers, loaded once per process."""
    return Layers(
        land=load_layer(geo_dir / LAYER_FILES["land"], rings=True),
        coast=load_layer(geo_dir / LAYER_FILES["coast"], rings=False),
        borders=load_layer(geo_dir / LAYER_FILES["borders"], rings=False),
    )


# --- projection --------------------------------------------------------------------------


def _merc(lat: float) -> float:
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


@dataclass(frozen=True)
class Mercator:
    """Web-Mercator maths: `scale` pixels per radian, the bbox centre at the box centre.
    `fit` picks the scale that fits the bbox in the box and centres the leftover."""

    scale: float
    center_lon: float
    center_merc: float
    center_x: float
    center_y: float

    @classmethod
    def fit(cls, bbox: BBox, box: Rect) -> Mercator:
        west, south, east, north = bbox
        left, top, width, height = box
        lon_span = math.radians(east - west)
        merc_span = _merc(north) - _merc(south)
        if lon_span <= 0 or merc_span <= 0:
            raise ValueError(f"the bbox {bbox} has no area to fit")
        scale = min(width / lon_span, height / merc_span)
        return cls(
            scale=scale,
            center_lon=(west + east) / 2,
            center_merc=(_merc(north) + _merc(south)) / 2,
            center_x=left + width / 2,
            center_y=top + height / 2,
        )

    def project(self, lon: float, lat: float) -> Point:
        x = self.center_x + self.scale * math.radians(lon - self.center_lon)
        y = self.center_y - self.scale * (_merc(lat) - self.center_merc)
        return x, y

    def invert(self, x: float, y: float) -> Point:
        lon = self.center_lon + math.degrees((x - self.center_x) / self.scale)
        merc = self.center_merc - (y - self.center_y) / self.scale
        lat = math.degrees(2 * math.atan(math.exp(merc)) - math.pi / 2)
        return lon, lat

    def geo_bbox(self, rect: Rect) -> BBox:
        """The degrees a pixel rectangle covers (for the quick reject)."""
        left, top, width, height = rect
        west, south = self.invert(left, top + height)
        east, north = self.invert(left + width, top)
        return west, south, east, north


# --- clipping and paths ------------------------------------------------------------------


def _inside(p: Point, edge: int, rect: Rect) -> bool:
    left, top, width, height = rect
    x, y = p
    return (x >= left, x <= left + width, y >= top, y <= top + height)[edge]


def _intersect(a: Point, b: Point, edge: int, rect: Rect) -> Point:
    left, top, width, height = rect
    (x1, y1), (x2, y2) = a, b
    if edge < 2:
        x = left if edge == 0 else left + width
        t = (x - x1) / (x2 - x1) if x2 != x1 else 0.0
        return x, y1 + (y2 - y1) * t
    y = top if edge == 2 else top + height
    t = (y - y1) / (y2 - y1) if y2 != y1 else 0.0
    return x1 + (x2 - x1) * t, y


def clip_ring(ring: Sequence[Point], rect: Rect) -> list[Point]:
    """Sutherland-Hodgman: the polygon `ring` cut to the rectangle; empty when it lies
    wholly outside."""
    output = [p for p in ring]
    for edge in range(4):
        if not output:
            return []
        clipped: list[Point] = []
        previous = output[-1]
        for current in output:
            if _inside(current, edge, rect):
                if not _inside(previous, edge, rect):
                    clipped.append(_intersect(previous, current, edge, rect))
                clipped.append(current)
            elif _inside(previous, edge, rect):
                clipped.append(_intersect(previous, current, edge, rect))
            previous = current
        output = clipped
    return output


def _clip_segment(a: Point, b: Point, rect: Rect) -> tuple[Point, Point] | None:
    """Liang-Barsky: the part of segment a-b inside the rectangle, or None."""
    left, top, width, height = rect
    (x1, y1), (x2, y2) = a, b
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    edges = ((-dx, x1 - left), (dx, left + width - x1), (-dy, y1 - top), (dy, top + height - y1))
    for p, q in edges:
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    return (x1 + dx * t0, y1 + dy * t0), (x1 + dx * t1, y1 + dy * t1)


def clip_line(line: Sequence[Point], rect: Rect) -> list[list[Point]]:
    """The polyline cut into the pieces inside the rectangle, in order."""
    pieces: list[list[Point]] = []
    current: list[Point] = []
    for a, b in zip(line, line[1:], strict=False):
        cut = _clip_segment(a, b, rect)
        if cut is None:
            if current:
                pieces.append(current)
                current = []
            continue
        start, end = cut
        if current and current[-1] == start:
            current.append(end)
        else:
            if current:
                pieces.append(current)
            current = [start, end]
        if end != b:  # the segment left the rectangle: the piece ends here
            pieces.append(current)
            current = []
    if current:
        pieces.append(current)
    return pieces


MIN_STEP_PX = 0.5  # consecutive points closer than this are one point


def _fmt(v: float) -> str:
    text = f"{v:.1f}"
    return text[:-2] if text.endswith(".0") else text


def svg_path(points: Sequence[Point], *, close: bool) -> str:
    """`M x y L x y ... [Z]`, coordinates to a tenth of a pixel, sub-pixel steps
    dropped; empty when fewer than two points survive."""
    kept: list[Point] = []
    for p in points:
        if kept and abs(p[0] - kept[-1][0]) < MIN_STEP_PX and abs(p[1] - kept[-1][1]) < MIN_STEP_PX:
            continue
        kept.append(p)
    if close and len(kept) > 1 and abs(kept[0][0] - kept[-1][0]) < MIN_STEP_PX \
            and abs(kept[0][1] - kept[-1][1]) < MIN_STEP_PX:  # fmt: skip
        kept.pop()
    if len(kept) < 2:
        return ""
    body = "".join(f"L{_fmt(x)} {_fmt(y)}" for x, y in kept[1:])
    return f"M{_fmt(kept[0][0])} {_fmt(kept[0][1])}{body}{'Z' if close else ''}"


@dataclass(frozen=True)
class BasePaths:
    """The map base as SVG path strings in composition pixels."""

    land: list[str] = field(default_factory=lambda: [])
    coast: list[str] = field(default_factory=lambda: [])
    borders: list[str] = field(default_factory=lambda: [])
    land_names: set[str] = field(default_factory=lambda: set())


def _overlaps(a: BBox, b: BBox) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def base_paths(layers: Layers, projection: Mercator, rect: Rect) -> BasePaths:
    """Every layer projected, clipped to `rect` and written as paths; shapes whose
    bbox misses the rectangle's degrees are skipped before projection."""
    window = projection.geo_bbox(rect)
    out = BasePaths()
    for shape in layers.land:
        if not _overlaps(shape.bbox, window):
            continue
        ring = clip_ring([projection.project(*p) for p in shape.points], rect)
        path = svg_path(ring, close=True)
        if path:
            out.land.append(path)
            out.land_names.add(shape.name)
    for shapes, target in ((layers.coast, out.coast), (layers.borders, out.borders)):
        for shape in shapes:
            if not _overlaps(shape.bbox, window):
                continue
            for piece in clip_line([projection.project(*p) for p in shape.points], rect):
                path = svg_path(piece, close=False)
                if path:
                    target.append(path)
    return out
