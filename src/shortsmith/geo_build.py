"""`python -m shortsmith.geo_build <raw_dir>`: build `assets/geo/` from the Natural
Earth downloads (ticket 020, operator-run once per dataset version).

The raw GeoJSON files the operator fetched (never committed; they live under the
git-ignored `work/`) become the bundled data:

- the three drawing layers, rewritten gzipped with the geometry and a name only
  (`ne_50m_admin_0_countries`, `ne_50m_coastline`, `ne_50m_admin_0_boundary_lines_land`);
- `gazetteer.json`, one row per place from the countries layer (kind `country`, the
  label point, the bbox of its significant land: polygons at least `SIGNIFICANT` of the
  largest, so France's mainland is France and an overseas islet does not stretch it),
  the continents, UN subregions and World Bank regions as the union of their countries
  (kind `region`), the admin-1 states layer (kind `state`, the label point and the full
  bbox), and the 1:10m populated places (kind `city`, the geometry point - the
  LATITUDE / LONGITUDE columns drift from it on a few hundred rows). Every name column
  a viewer might use is an alias: English, local, Hindi, the ISO codes.

`build` prints one line per file with its real size and row count; the README records
them. `VERSION` from the download folder is stamped into the gazetteer.
"""

from __future__ import annotations

import gzip
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from shortsmith import geo

SIGNIFICANT = 0.05  # a polygon smaller than this fraction of the largest is not the country
NONE_CODE = "-99"  # Natural Earth's "no code"
COUNTRY_ALIASES = ("NAME", "NAME_LONG", "ADMIN", "FORMAL_EN", "NAME_EN", "NAME_HI", "NAME_ALT",
                   "ABBREV", "NAME_SORT", "ISO_A3", "ISO_A2")  # fmt: skip
REGION_COLUMNS = ("CONTINENT", "SUBREGION", "REGION_WB")
SKIPPED_REGIONS = frozenset({"Seven seas (open ocean)", "Antarctica"})
STATE_ALIASES = ("name", "name_alt", "name_en", "name_hi", "name_local", "woe_name", "gn_name")
CITY_ALIASES = ("NAME", "NAMEASCII", "NAMEALT", "NAME_EN", "NAME_HI", "MEGANAME", "NAMEPAR")
RAW_FILES: Mapping[str, str] = {
    "land": "ne_50m_admin_0_countries.geojson",
    "coast": "ne_50m_coastline.geojson",
    "borders": "ne_50m_admin_0_boundary_lines_land.geojson",
}
RAW_STATES = "ne_50m_admin_1_states_provinces.geojson"
RAW_PLACES = "ne_10m_populated_places.geojson"
LAYER_KEEP: Mapping[str, tuple[str, ...]] = {"land": ("NAME",), "coast": (), "borders": ()}

Entry = dict[str, Any]


# --- geometry helpers ----------------------------------------------------------------------


def _rings(geometry: Mapping[str, Any]) -> list[list[list[float]]]:
    """The exterior ring of every polygon."""
    kind, coords = geometry.get("type"), geometry.get("coordinates", [])
    if kind == "Polygon":
        return [coords[0]] if coords else []
    if kind == "MultiPolygon":
        return [poly[0] for poly in coords if poly]
    return []


def _area(ring: Sequence[Sequence[float]]) -> float:
    """Shoelace area in square degrees (a size measure, not a real area)."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def _bbox(rings: Iterable[Sequence[Sequence[float]]]) -> list[float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for ring in rings:
        xs += [float(p[0]) for p in ring]
        ys += [float(p[1]) for p in ring]
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def significant_bbox(geometry: Mapping[str, Any]) -> list[float] | None:
    rings = _rings(geometry)
    if not rings:
        return None
    largest = max(_area(r) for r in rings)
    return _bbox(r for r in rings if _area(r) >= SIGNIFICANT * largest)


def _union(boxes: Iterable[Sequence[float]]) -> list[float] | None:
    boxes = list(boxes)
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]  # fmt: skip


def _aliases(props: Mapping[str, Any], columns: Sequence[str], *, primary: str) -> list[str]:
    seen: dict[str, str] = {}
    for column in columns:
        value = props.get(column)
        if not value or not isinstance(value, str) or value == NONE_CODE:
            continue
        for part in str(value).split("|"):
            part = part.strip()
            key = geo.normalise(part)
            if key and key != geo.normalise(primary) and key not in seen:
                seen[key] = part
    return list(seen.values())


# --- the gazetteer ---------------------------------------------------------------------------


def _country_entries(countries: Sequence[Mapping[str, Any]]) -> list[Entry]:
    out: list[Entry] = []
    for feature in countries:
        props = feature["properties"]
        name = str(props["NAME"])
        entry: Entry = {
            "name": name,
            "kind": "country",
            "country": name,
            "lat": float(props["LABEL_Y"]),
            "lon": float(props["LABEL_X"]),
            "pop": int(props.get("POP_EST") or 0),
            "aliases": _aliases(props, COUNTRY_ALIASES, primary=name),
        }
        bbox = significant_bbox(feature.get("geometry") or {})
        if bbox is not None:
            entry["bbox"] = bbox
        out.append(entry)
    return out


def _region_entries(
    countries: Sequence[Mapping[str, Any]], entries: Sequence[Entry]
) -> list[Entry]:
    bboxes = {e["name"]: e["bbox"] for e in entries if "bbox" in e}
    members: dict[str, list[str]] = {}
    for feature in countries:
        props = feature["properties"]
        for column in REGION_COLUMNS:
            region = props.get(column)
            if region and region not in SKIPPED_REGIONS:
                members.setdefault(str(region), []).append(str(props["NAME"]))
    out: list[Entry] = []
    for region, names in members.items():
        bbox = _union(bboxes[n] for n in names if n in bboxes)
        if bbox is None:
            continue
        out.append({
            "name": region, "kind": "region", "country": "",
            "lat": (bbox[1] + bbox[3]) / 2, "lon": (bbox[0] + bbox[2]) / 2,
            "pop": 0, "aliases": [], "bbox": bbox,
        })  # fmt: skip
    out.append({
        "name": "World", "kind": "region", "country": "", "lat": 0.0, "lon": 0.0, "pop": 0,
        "aliases": ["the world", "globe", "earth"], "bbox": list(geo.WORLD_BBOX),
    })  # fmt: skip
    return out


def _state_entries(states: Sequence[Mapping[str, Any]]) -> list[Entry]:
    out: list[Entry] = []
    for feature in states:
        props = feature["properties"]
        name = str(props["name"])
        entry: Entry = {
            "name": name,
            "kind": "state",
            "country": str(props.get("admin") or ""),
            "lat": float(props["latitude"]),
            "lon": float(props["longitude"]),
            "pop": 0,
            "aliases": _aliases(props, STATE_ALIASES, primary=name),
        }
        bbox = _bbox(_rings(feature.get("geometry") or {}))
        if bbox is not None:
            entry["bbox"] = bbox
        out.append(entry)
    return out


def _city_entries(places: Sequence[Mapping[str, Any]]) -> list[Entry]:
    out: list[Entry] = []
    for feature in places:
        props = feature["properties"]
        name = str(props["NAME"])
        lon, lat = feature["geometry"]["coordinates"][:2]
        out.append({
            "name": name, "kind": "city", "country": str(props.get("ADM0NAME") or ""),
            "lat": float(lat), "lon": float(lon), "pop": int(props.get("POP_MAX") or 0),
            "aliases": _aliases(props, CITY_ALIASES, primary=name),
        })  # fmt: skip
    return out


def build_gazetteer(
    *,
    countries: Sequence[Mapping[str, Any]],
    states: Sequence[Mapping[str, Any]],
    places: Sequence[Mapping[str, Any]],
) -> list[Entry]:
    """The gazetteer rows from the three feature lists, countries first."""
    country_entries = _country_entries(countries)
    return [
        *country_entries,
        *_region_entries(countries, country_entries),
        *_state_entries(states),
        *_city_entries(places),
    ]


def write_gazetteer(path: Path, entries: Sequence[Entry], *, version: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "source": "Natural Earth (public domain): ne_50m_admin_0_countries, "
                  "ne_50m_admin_1_states_provinces, ne_10m_populated_places",
        "version": version,
        "places": list(entries),
    }  # fmt: skip
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8")  # fmt: skip
    return path


# --- the drawing layers ------------------------------------------------------------------


def write_layer(raw: Path, out: Path, *, keep: Sequence[str]) -> Path:
    """`raw` rewritten gzipped at `out` with the geometry and the `keep` properties."""
    data = json.loads(raw.read_text(encoding="utf-8"))
    features = [
        {
            "type": "Feature",
            "properties": {k: f["properties"].get(k) for k in keep},
            "geometry": f["geometry"],
        }
        for f in data["features"]
        if f.get("geometry")
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as handle:
        json.dump({"type": "FeatureCollection", "features": features}, handle,
                  separators=(",", ":"))  # fmt: skip
    return out


# --- the command -------------------------------------------------------------------------


def _features(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def build(raw_dir: Path, out_dir: Path = geo.GEO_DIR) -> list[str]:
    """Every bundled file from the downloads; returns the report lines."""
    lines: list[str] = []
    for key, raw_name in RAW_FILES.items():
        raw = raw_dir / raw_name
        out = write_layer(raw, out_dir / geo.LAYER_FILES[key], keep=LAYER_KEEP[key])
        count = len(_features(raw))
        lines.append(f"{out.name}: {count} features, {raw.stat().st_size / 1e6:.2f} MB raw -> "
                     f"{out.stat().st_size / 1e6:.2f} MB gzipped")  # fmt: skip
    version_file = raw_dir / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else ""
    countries = _features(raw_dir / RAW_FILES["land"])
    states = _features(raw_dir / RAW_STATES)
    places = _features(raw_dir / RAW_PLACES)
    entries = build_gazetteer(countries=countries, states=states, places=places)
    out = write_gazetteer(out_dir / geo.GAZETTEER_FILE, entries, version=version)
    kinds = {
        k: sum(1 for e in entries if e["kind"] == k) for k in ("country", "region", "state", "city")
    }
    lines.append(
        f"{out.name}: {len(entries)} places {kinds} from {len(countries)} countries, "
        f"{len(states)} states, {len(places)} populated places; Natural Earth {version or '?'}; "
        f"{out.stat().st_size / 1e6:.2f} MB"
    )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m shortsmith.geo_build <raw_dir>", file=sys.stderr)
        return 2
    for line in build(Path(args[0])):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
