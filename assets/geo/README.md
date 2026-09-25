# The map data (ticket 020; decisions 9.3, 13.1)

Maps are composed in code, never generated as a picture: the `map` component draws
land, coast and borders from the vector data here, and every marker is placed by a real
coordinate from the gazetteer here (or the Nominatim fallback), never by a number the
planner wrote. Everything loads from this folder with no network, so the renderer and
the Docker image (046) need nothing else.

## What is here

| File | Built from | Rows | Size |
|---|---|---|---|
| `ne_50m_admin_0_countries.geojson.gz` | Natural Earth 1:50m admin-0 countries, geometry + `NAME` | 242 features (99,613 points) | 0.83 MB (3.08 MB raw) |
| `ne_50m_coastline.geojson.gz` | Natural Earth 1:50m coastline, geometry only | 1,428 features (60,416 points) | 0.51 MB (1.64 MB raw) |
| `ne_50m_admin_0_boundary_lines_land.geojson.gz` | Natural Earth 1:50m land boundary lines, geometry only | 390 features (19,859 points) | 0.18 MB (0.76 MB raw) |
| `gazetteer.json` | admin-0 countries + 1:50m admin-1 states + 1:10m populated places | 7,912 places: 242 countries, 34 regions, 294 states, 7,342 cities | 1.18 MB |

Dataset version: Natural Earth **5.2.0-pre** (the mirror's `VERSION` file, stamped into
`gazetteer.json`). Licence: public domain, see `LICENSE`.

The gazetteer rows are `{name, kind, country, lat, lon, pop, aliases, bbox?}`:

- `country`: the label point (`LABEL_X/Y`) and the bbox of its *significant* land
  (polygons at least 5 % of the largest, so an overseas islet does not stretch a
  mainland). Aliases: long and formal names, English and Hindi names, ISO A2/A3.
- `region`: the seven continents, the UN subregions ("Southern Asia") and the World
  Bank regions ("South Asia") as the union of their countries' bboxes, plus `World`.
- `state`: the 294 admin-1 units Natural Earth ships at 1:50m (Russia, USA, India,
  Indonesia, China, Brazil, Canada, Australia, South Africa), label point and full bbox.
- `city`: every 1:10m populated place, the geometry point (the `LATITUDE/LONGITUDE`
  columns drift from it on 297 rows), `POP_MAX`, Hindi and alternate names.

A shared name resolves area first (`country` > `region` > `state` > `city`), then by
population: "Delhi" is the state (with a bbox), "Victoria" the Canadian city. Lookups
ignore case, Latin accents, punctuation and spacing (`geo.normalise`).

## Rebuilding it

Operator-run once per dataset version; the raw downloads never enter the repo
(`work/` is git-ignored):

```powershell
New-Item -ItemType Directory -Force work\geo_raw | Out-Null
$base = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master'
foreach ($f in 'geojson/ne_50m_admin_0_countries.geojson',
               'geojson/ne_50m_admin_0_boundary_lines_land.geojson',
               'geojson/ne_50m_coastline.geojson',
               'geojson/ne_50m_admin_1_states_provinces.geojson',
               'geojson/ne_10m_populated_places.geojson', 'VERSION') {
  Invoke-WebRequest -Uri "$base/$f" -OutFile ("work\geo_raw\" + (Split-Path $f -Leaf))
}
uv run python -m shortsmith.geo_build work\geo_raw
```

The build prints one line per file with the real sizes and counts; update the table
above from it, then delete `work\geo_raw\` (the 19 MB populated-places file is build
input only).

## Tests and the smoke

`tests/test_geo.py` builds a gazetteer from synthetic features shaped like the Natural
Earth columns, then loads the bundled files for real and asks for the fake plan's places.
The smoke renders the fake plan's `map` beat (India, Delhi to Mumbai) with the
`FakeGeocoder`'s ten places over this folder's real land, with no network.
