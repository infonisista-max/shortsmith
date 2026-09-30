"""The editor's pure repairs (097, work/editor-design.md "Editor"): each takes a
`PicturePlan` and returns a new one with one targeted change; nothing reads or writes
disk, and nothing invents content. A repair only removes, simplifies or swaps what the
plan already holds, or (`frame_markers`) frames a map by coordinates the geocoder gives.

- `drop_layer(plan, beat, layer)`: one layer off one beat (`LAYERS`).
- `drop_route(plan, beat)`: the map's route and its two route animations off.
- `plain_cut(plan, beat)`: the beat enters on a plain cut.
- `replace_visual(plan, beat)`: the beat becomes a plain `photo` the replacement ladder
  (096) re-sources; the caller adds the beat to `JobRecord.replaced`.
- `frame_markers(plan, beat, geocoder)`: the map's region name is dropped and its bbox
  is framed around the markers' (and route points') REAL coordinates; `marker_bbox`
  is None when any name does not resolve, and then the option is never offered.
- `no_cut(plan, transcript)`: the cut keeps the whole recording (every word kept).
- `place_reference(plan, beat, ref)`: the beat shows the owner's reference.
- `retile(plan, runtime)`: the beats tile 0..runtime with no gap or overlap.
- `strip_overlays(plan)`: every overlay layer off every beat (the plain render fallback).
- `set_treatment(plan, beat, treatment)`: the beat's picture treatment swapped for another
  of the vocabulary (103: a treatment repeated on consecutive beats).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal, get_args

from shortsmith import geo
from shortsmith.contracts import (
    CAMERA_MOVES,
    PICTURE_TREATMENTS,
    Beat,
    CutPlan,
    Event,
    MapPlan,
    Motion,
    PicturePlan,
    Span,
    Transcript,
)
from shortsmith.infographics import CITY_SPAN_DEG

Layer = Literal[
    "text_pops", "bubbles", "stickers", "highlight", "banner", "calendar", "event", "counter",
    "route",
]  # fmt: skip
LAYERS: tuple[Layer, ...] = get_args(Layer)
ROUTE_OVERLAYS = frozenset({"route_arrow", "object_path"})
PHOTO_MOTIONS: frozenset[Motion] = frozenset(CAMERA_MOVES)  # 102: every camera move
PRESENTER_KINDS = frozenset({"presenter_full", "presenter_pip"})
MAX_LAT = 85.0  # the grammar's map edge (grammar.MAX_MAP_LAT)
EPS = 1e-6


class RepairError(ValueError):
    """A repair that cannot apply to this beat (no such beat, nothing to frame)."""


def beat_of(plan: PicturePlan, beat_id: str) -> Beat:
    for b in plan.beats:
        if b.id == beat_id:
            return b
    raise RepairError(f"{beat_id}: no such beat in the plan")


def _with_beat(plan: PicturePlan, beat_id: str, change: Callable[[Beat], Beat]) -> PicturePlan:
    beat_of(plan, beat_id)
    beats = [change(b) if b.id == beat_id else b for b in plan.beats]
    return plan.model_copy(update={"beats": beats})


def layers_of(beat: Beat) -> list[Layer]:
    """The layers this beat carries, in `LAYERS` order (what `drop_layer` can remove)."""
    present: list[Layer] = []
    if beat.text_pops:
        present.append("text_pops")
    if beat.bubbles:
        present.append("bubbles")
    if beat.stickers:
        present.append("stickers")
    if beat.highlight is not None:
        present.append("highlight")
    if beat.banner is not None:
        present.append("banner")
    if beat.calendar is not None:
        present.append("calendar")
    if beat.event.kind != "none":
        present.append("event")
    if beat.counter is not None and beat.kind != "counter":
        present.append("counter")
    if beat.map is not None and (beat.map.route or ROUTE_OVERLAYS & set(beat.overlays)):
        present.append("route")
    return present


def _dropped(beat: Beat, layer: Layer) -> Beat:
    match layer:
        case "text_pops":
            return beat.model_copy(update={"text_pops": []})
        case "bubbles":
            return beat.model_copy(update={"bubbles": []})
        case "stickers":
            return beat.model_copy(update={"stickers": []})
        case "highlight":
            return beat.model_copy(update={"highlight": None})
        case "banner":
            return beat.model_copy(update={"banner": None})
        case "calendar":
            return beat.model_copy(update={"calendar": None})
        case "event":
            return beat.model_copy(update={"event": Event()})
        case "counter":
            overlays = [o for o in beat.overlays if o != "counter"]
            return beat.model_copy(update={"counter": None, "overlays": overlays})
        case "route":
            overlays = [o for o in beat.overlays if o not in ROUTE_OVERLAYS]
            recipe = beat.map.model_copy(update={"route": [], "object": None}) if beat.map else None
            return beat.model_copy(update={"map": recipe, "overlays": overlays})


def drop_layer(plan: PicturePlan, beat_id: str, layer: Layer) -> PicturePlan:
    if layer not in LAYERS:
        raise RepairError(f"{beat_id}: {layer!r} is not a layer the editor can drop")
    return _with_beat(plan, beat_id, lambda b: _dropped(b, layer))


def drop_route(plan: PicturePlan, beat_id: str) -> PicturePlan:
    return drop_layer(plan, beat_id, "route")


def plain_cut(plan: PicturePlan, beat_id: str) -> PicturePlan:
    return _with_beat(plan, beat_id, lambda b: b.model_copy(update={"enter": "cut"}))


def _asset_shared(plan: PicturePlan, beat: Beat) -> bool:
    """Another beat plans the same asset id, or a set-piece item names it: the id stays
    planned so they still resolve (the replaced beat's new picture answers for it)."""
    if beat.asset_id is None:
        return False
    for b in plan.beats:
        if b.id != beat.id and b.asset_id == beat.asset_id:
            return True
        if any(i.asset_id == beat.asset_id for i in b.items):
            return True
    return False


def replace_visual(plan: PicturePlan, beat_id: str) -> PicturePlan:
    """The beat's visual is removed and the beat becomes a plain `photo` the replacement
    ladder re-sources (operator answer 1): no map, chart, labels, set piece, counter,
    overlays or highlight; `ken_burns_in` unless it already has a photo motion; a
    `concept` subject when it had none; the query falls back to `query_fallback`, then
    the set piece's title. The planned asset id is cleared unless another beat or an
    item shares it (then it stays, so they still resolve). A presenter beat moves to
    `pip` so the picture shows."""

    def change(b: Beat) -> Beat:
        query = b.query.strip() or b.query_fallback.strip() or b.set_piece_title.strip()
        return b.model_copy(
            update={
                "kind": "photo",
                "mode": "pip" if b.kind in PRESENTER_KINDS else b.mode,
                "reason": None if b.kind in PRESENTER_KINDS else b.reason,
                "map": None,
                "chart_form": None,
                "series": [],
                "labels": [],
                "items": [],
                "set_piece_title": "",
                "value_unit": "",
                "counter": None,
                "overlays": [],
                "highlight": None,
                "asset_id": b.asset_id if _asset_shared(plan, b) else None,
                "motion": b.motion if b.motion in PHOTO_MOTIONS else "ken_burns_in",
                "subject_kind": b.subject_kind or "concept",
                "query": query,
                "source_intent": "search" if b.source_intent == "reuse" else b.source_intent,
            }
        )

    return _with_beat(plan, beat_id, change)


def marker_bbox(beat: Beat, geocoder: geo.Geocoder) -> geo.BBox | None:
    """The bbox (west, south, east, north) around the map's markers and route points at
    the geocoder's REAL coordinates, or None when the beat has no markers or any name
    does not resolve (never a guess, 9.3). One point is framed `CITY_SPAN_DEG` across;
    a span narrower than that is widened to it around its middle."""
    if beat.map is None or not beat.map.markers:
        return None
    names = [m.name for m in beat.map.markers] + list(beat.map.route)
    points: list[tuple[float, float]] = []
    for name in names:
        try:
            place = geocoder.lookup(name)
        except Exception:  # noqa: BLE001 - a geocoder failure is a miss here, never a guess
            return None
        if place is None:
            return None
        points.append((place.lon, place.lat))
    west, east = min(p[0] for p in points), max(p[0] for p in points)
    south, north = min(p[1] for p in points), max(p[1] for p in points)
    half = CITY_SPAN_DEG / 2
    if east - west < CITY_SPAN_DEG:
        mid = (west + east) / 2
        west, east = mid - half, mid + half
    if north - south < CITY_SPAN_DEG:
        mid = (south + north) / 2
        south, north = mid - half, mid + half
    return (
        round(max(-180.0, west), 4),
        round(max(-MAX_LAT, south), 4),
        round(min(180.0, east), 4),
        round(min(MAX_LAT, north), 4),
    )


def frame_markers(plan: PicturePlan, beat_id: str, geocoder: geo.Geocoder) -> PicturePlan:
    """The map framed by its markers' real coordinates: region "" and the bbox from
    `marker_bbox`. Raises `RepairError` when a name does not resolve (the option is
    only offered when every one does)."""
    beat = beat_of(plan, beat_id)
    box = marker_bbox(beat, geocoder)
    if box is None or beat.map is None:
        raise RepairError(f"{beat_id}: not every map marker resolves; nothing to frame")
    recipe: MapPlan = beat.map.model_copy(update={"region": "", "bbox": box})
    return _with_beat(plan, beat_id, lambda b: b.model_copy(update={"map": recipe}))


def no_cut(plan: PicturePlan, transcript: Transcript) -> PicturePlan:
    """The cut keeps the whole recording: every spoken word, once, in order (the grammar
    still tightens the pauses)."""
    end = max(transcript.duration_s, transcript.words[-1].end if transcript.words else 0.0)
    return plan.model_copy(update={"cut": CutPlan(keep=[Span(start=0.0, end=end)], drop=[])})


def place_reference(plan: PicturePlan, beat_id: str, ref_id: str) -> PicturePlan:
    """The beat shows the owner's reference `ref_id` (a must-use reference no beat used)."""
    return _with_beat(plan, beat_id, lambda b: b.model_copy(update={"asset_id": ref_id}))


def retile(plan: PicturePlan, runtime: float) -> PicturePlan:
    """The beats tile 0..`runtime` on the plan's own timeline: the first starts at 0,
    each boundary is the later beat's start (a gap is closed by the earlier beat, an
    overlap trimmed from it), the last ends at `runtime`. A beat left with no length
    keeps its planned boundary instead."""
    beats = list(plan.beats)
    if not beats:
        return plan
    starts = [0.0] + [b.start for b in beats[1:]]
    ends = [b.start for b in beats[1:]] + [runtime]
    out: list[Beat] = []
    for i, b in enumerate(beats):
        start = out[-1].end if out else starts[i]
        end = ends[i]
        if end - start <= EPS:
            end = max(b.end, start + 0.1) if i < len(beats) - 1 else runtime
        if end - start <= EPS:
            raise RepairError(f"{b.id}: no room left to tile the beat up to {runtime:g} s")
        out.append(b.model_copy(update={"start": round(start, 3), "end": round(end, 3)}))
    return plan.model_copy(update={"beats": out})


def strip_overlays(plan: PicturePlan, beat_ids: Sequence[str] | None = None) -> PicturePlan:
    """Every overlay layer off every beat (or `beat_ids`): text pops, bubbles, stickers,
    the highlight, the banner (107), the calendar (108), the counter (a `counter` beat
    keeps its own), the landed event and the motion-graphics overlays. The plain fallback
    for a render that fails naming no beat."""

    def stripped(b: Beat) -> Beat:
        return b.model_copy(
            update={
                "text_pops": [],
                "bubbles": [],
                "stickers": [],
                "highlight": None,
                "banner": None,
                "calendar": None,
                "counter": b.counter if b.kind == "counter" else None,
                "event": Event(),
                "overlays": [],
            }
        )

    wanted = set(beat_ids) if beat_ids is not None else None
    beats = [stripped(b) if wanted is None or b.id in wanted else b for b in plan.beats]
    return plan.model_copy(update={"beats": beats})


def set_treatment(plan: PicturePlan, beat_id: str, treatment: str) -> PicturePlan:
    """103: the beat shows its picture as `treatment` (one of `PICTURE_TREATMENTS`); the
    renderer still falls back to an allowed one when the image cannot take it."""
    if treatment not in PICTURE_TREATMENTS:
        raise RepairError(f"{beat_id}: {treatment!r} is not a picture treatment")
    return _with_beat(plan, beat_id, lambda b: b.model_copy(update={"treatment": treatment}))
