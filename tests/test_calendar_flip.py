"""Calendar flip and kinetic dates (ticket 108; 083 part 3), and stamps kept off a map's
content (the fold-in: run05 b07's stamp landed over Saudi Arabia).

A year or date beat may carry a `calendar` instead of a stamp (`Beat.calendar`): a page
showing `from_text` peels away to `to_text`, landing on the spoken word. Its numbers are
the style's `broll.calendar` row, offered where the references use it. On a map beat the
stamp (and a calendar) keeps off the named country's area, the target circle, the angled
tag and the marker pills, or goes to the corner with the least map content; the margin is
`broll.motion.map.stamp_margin_px`. No network, no key."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shortsmith import captions, ffmpeg, fixture, geo, grammar, render, styles
from shortsmith.contracts import (
    Beat,
    BeatSpec,
    CalendarPlan,
    Captions,
    Constraints,
    Event,
    MapLayout,
    MapMarker,
    MapPlan,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    Violation,
)
from shortsmith.planner import FakePlanner
from shortsmith.reference.examples import load_effect_map
from shortsmith.safe_area import SAFE_LEFT, SAFE_RIGHT_PX, SAFE_TOP_PX, WIDTH
from shortsmith.transcriber import FakeTranscriber

TRANSCRIPT = FakeTranscriber().transcribe(Path("unused.mp4"))
WORDS = TRANSCRIPT.words
REGISTRY = render.registry()
SPECS = styles.load_all(REGISTRY)
EXPLAINER = SPECS["explainer"]
NUMBERS = render.numbers_for(EXPLAINER)
OFFER = ("explainer", "vishva")
MAP_STYLES = ("explainer", "fastfacts", "footage", "vishva", "hitech")
GAZETTEER = geo.GazetteerGeocoder()
YEAR = CalendarPlan(from_text="1937", to_text="1938", word=1)


def _smoke(name: str = "explainer") -> styles.StyleSpec:
    return fixture.smoke_specs(SPECS, name)[name]


def _plan(spec: styles.StyleSpec | None = None) -> PicturePlan:
    spec = spec or _smoke()
    request = PlanRequest(
        brief="Topic: a six-second synthetic clip.",
        style=PlanStyle(name=spec.name, numbers=spec.numbers(), prose=spec.prose),
        style_note=spec.name, transcript=TRANSCRIPT, references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=fixture.DURATION_S),
        asset_policy="any",
    )  # fmt: skip
    return FakePlanner().plan_picture(request)


def _with(plan: PicturePlan, beat_id: str, **update: Any) -> PicturePlan:
    return plan.model_copy(update={"beats": [
        b.model_copy(update=update) if b.id == beat_id else b for b in plan.beats
    ]})  # fmt: skip


Checked = grammar.PictureCheck | grammar.Violations


def _check(plan: PicturePlan, spec: styles.StyleSpec | None = None) -> Checked:
    return grammar.validate_picture(plan, TRANSCRIPT, spec or _smoke())


def _problems(result: Checked, needle: str) -> list[Violation]:
    assert isinstance(result, grammar.Violations), "the plan passed"
    return [v for v in result.items if needle in v.message]


# --- the styles -------------------------------------------------------------------------


def test_the_calendar_row_carries_the_reference_numbers_where_offered() -> None:
    for name in OFFER:
        row = SPECS[name].broll.calendar
        assert row is not None, name
        # QjwDTLPLJ6c calendar_flip 1.4 s, M78CO3Ybr7U calendar_page_peel 1.5 s on screen:
        # the lead, the flip and the hold after the word add up to 1.5 s
        assert row.lead_s + row.flip_s + row.hold_max_s == pytest.approx(1.5), name
        assert "calendar" in SPECS[name].requires_components, name
    assert SPECS["explainer"].broll.calendar.max_per_60s == 1  # type: ignore[union-attr]
    for name, spec in SPECS.items():
        if name not in OFFER:
            assert spec.broll.calendar is None, name


def test_every_map_style_carries_the_stamp_margin() -> None:
    for name in MAP_STYLES:
        assert render.numbers_for(SPECS[name]).info.map.stamp_margin_px == 24, name


def test_the_calendar_is_registered_and_the_effect_map_points_both_names_at_it() -> None:
    assert "calendar" in REGISTRY
    mapped = load_effect_map()
    assert mapped["calendar_flip"] == mapped["calendar_page_peel"] == "calendar"


# --- the grammar ------------------------------------------------------------------------


def test_a_calendar_on_a_year_beat_passes_and_lands_on_its_word() -> None:
    result = _check(_with(_plan(), "b01", calendar=YEAR))
    assert isinstance(result, grammar.PictureCheck), result
    landed = result.picture.beats[0].calendar
    assert landed is not None and landed.at_s == pytest.approx(WORDS[1].start)
    assert WORDS[1].start in grammar.change_times(result.picture.beats[0])


def test_a_calendar_replaces_the_stamp_never_rides_with_it() -> None:
    plan = _with(_plan(), "b04", calendar=YEAR.model_copy(update={"word": 5}))
    found = _problems(_check(plan), "instead of a stamp")
    assert found and found[0].beat_id == "b04"


def test_a_calendar_under_a_style_that_offers_none_fails() -> None:
    footage = _smoke("footage")
    found = _problems(_check(_with(_plan(footage), "b01", calendar=YEAR), footage), "calendar")
    assert found and "offers no calendar" in found[0].message


def test_a_calendar_over_the_cap_off_its_beat_or_unchanged_fails() -> None:
    plan = _with(_with(_plan(), "b01", calendar=YEAR), "b03",
                 calendar=YEAR.model_copy(update={"word": 2}))  # fmt: skip
    assert [v.beat_id for v in _problems(_check(plan), "broll.calendar.max_per_60s")] == ["b03"]
    elsewhere = _with(_plan(), "b01", calendar=YEAR.model_copy(update={"word": 5}))
    assert _problems(_check(elsewhere), "does not cover")
    same = _with(_plan(), "b01", calendar=YEAR.model_copy(update={"from_text": "1938"}))
    assert _problems(_check(same), "flips to what it shows")
    long = _with(_plan(), "b01", calendar=YEAR.model_copy(update={"to_text": "X" * 30}))
    assert _problems(_check(long), "chars_max")


# --- the render spec: timing and placement ------------------------------------------------


ROW = EXPLAINER.broll.calendar


def _calendar(at_s: float, *, end_s: float = 6.0) -> Any:
    planned = YEAR.model_copy(update={"at_s": at_s})
    return render.calendar_spec(planned, beat_start_s=0.0, beat_end_s=end_s, numbers=NUMBERS)


def test_the_page_flips_and_lands_on_the_spoken_word() -> None:
    assert ROW is not None
    spec = _calendar(2.0)
    assert spec.land_s == pytest.approx(2.0)
    assert spec.flip_start_s == pytest.approx(2.0 - ROW.flip_s)
    assert spec.appear_s == pytest.approx(2.0 - ROW.flip_s - ROW.lead_s)
    assert spec.until_s == pytest.approx(2.0 + ROW.hold_max_s)
    assert (spec.from_text, spec.to_text) == ("1937", "1938")
    early = _calendar(0.2)  # a word near the beat's start: the flip starts with the beat
    assert (early.appear_s, early.flip_start_s, early.land_s) == (0.0, 0.0, pytest.approx(0.2))
    short = _calendar(0.2, end_s=0.5)
    assert short.until_s == pytest.approx(0.5)


def test_the_calendar_sits_in_the_stamp_band_inside_the_safe_area() -> None:
    assert ROW is not None
    spec = _calendar(1.0)
    assert (spec.width, spec.height) == (ROW.width_px, ROW.height_px)
    assert spec.left >= SAFE_LEFT and spec.left + spec.width <= WIDTH - SAFE_RIGHT_PX
    assert spec.top >= SAFE_TOP_PX
    assert spec.top + spec.height <= EXPLAINER.broll.stamp_max_y_fraction * 1920
    assert ROW.min_size_px <= spec.font_px <= ROW.size_px
    assert (spec.page, spec.ink, spec.header, spec.header_ink) == (
        ROW.page, ROW.ink, ROW.header, ROW.header_ink,
    )  # fmt: skip


# --- the stamp keeps off the map's content (the fold-in) ------------------------------------


Edges = tuple[float, float, float, float]


def _meet(a: Edges, b: Edges, margin: float = 0.0) -> bool:
    return (a[0] < b[2] + margin and b[0] < a[2] + margin
            and a[1] < b[3] + margin and b[1] < a[3] + margin)  # fmt: skip


def _map_content(layout: MapLayout) -> dict[str, Edges]:
    t = layout.target
    assert t is not None and t.tag == "Saudi Arabia"
    assert layout.highlight_box is not None
    boxes: dict[str, Edges] = {
        "the named country": layout.highlight_box,
        "the circle": (t.x - t.radius, t.y - t.radius, t.x + t.radius, t.y + t.radius),
        "the tag": (t.tag_box_left, t.tag_box_top, t.tag_box_right, t.tag_box_bottom),
    }
    for m in layout.markers:
        boxes[f"the {m.name} pill"] = (m.label_left, m.label_top, m.label_left + m.label_width,
                                       m.label_top + m.label_height)  # fmt: skip
    return boxes


def _map_beat(**update: Any) -> Beat:
    return Beat.model_validate({
        "id": "b07", "start": 0.0, "end": 2.9, "mode": "off", "kind": "map",
        "overlays": ["pin_drop"], "event": {"kind": "stamp", "text": "1938"},
        "map": MapPlan(region="Saudi Arabia", markers=[MapMarker(name="Riyadh")]).model_dump(),
        **update,
    })  # fmt: skip


def _edges(box: render.Box) -> Edges:
    return (box.left, box.top, box.right, box.bottom)


def test_the_named_country_has_its_box_on_the_map() -> None:
    layout = render.map_layout(_map_beat(), numbers=NUMBERS, geocoder=GAZETTEER)
    assert layout is not None and layout.highlight_box is not None
    left, top, right, bottom = layout.highlight_box
    t = layout.target
    assert t is not None and left < t.x < right and top < t.y < bottom


def test_a_stamp_on_a_saudi_arabia_map_keeps_off_the_country_the_circle_the_tag_and_pills() -> None:
    """run05 b07: the stamp lands clear of every piece of the map's content, with the
    style's margin, and the tag and names still keep clear of the stamp."""
    stamp = render.stamp_spec("1938", numbers=NUMBERS)
    bare = render.map_layout(_map_beat(), numbers=NUMBERS, geocoder=GAZETTEER)
    assert bare is not None
    moved, how = render.stamp_off_map(stamp, bare, numbers=NUMBERS)
    margin = NUMBERS.info.map.stamp_margin_px
    box = _edges(render.stamp_box(moved))
    assert how == "clear"
    for name, content in _map_content(bare).items():
        assert not _meet(box, content, margin - 1e-6), name
    # inside the safe area and the stamp band
    assert box[0] >= SAFE_LEFT - 1e-6 and box[2] <= WIDTH - SAFE_RIGHT_PX + 1e-6
    assert box[1] >= SAFE_TOP_PX - 1e-6
    assert box[3] <= EXPLAINER.broll.stamp_max_y_fraction * 1920 + 1e-6


def test_the_build_moves_the_map_beats_stamp_and_lays_the_map_round_it(tmp_path: Path) -> None:
    plan = _plan()
    plan = plan.model_copy(update={"beats": [
        _map_beat(id="b05", start=b.start, end=b.end, enter=b.enter) if b.id == "b05" else b
        for b in plan.beats
    ]})  # fmt: skip
    lines: list[str] = []
    spec = render.build_spec(
        plan, captions.build(TRANSCRIPT, plan, EXPLAINER), presenter=Path("work/cut.mp4"),
        source_size=(fixture.WIDTH, fixture.HEIGHT), duration_s=fixture.DURATION_S,
        numbers=NUMBERS, geocoder=GAZETTEER, log=lines.append,
    )  # fmt: skip
    beat = next(b for b in spec.beats if b.id == "b05")
    assert beat.stamp is not None and beat.map is not None
    box = _edges(render.stamp_box(beat.stamp))
    for name, content in _map_content(beat.map).items():
        assert not _meet(box, content), name
    t = beat.map.target
    assert t is not None
    assert not _meet((t.tag_box_left, t.tag_box_top, t.tag_box_right, t.tag_box_bottom), box)
    for n in beat.map.names:
        assert not _meet((n.left, n.top, n.left + n.width, n.top + n.height), box), n.name
    assert any("b05" in line and "(108)" in line for line in lines), lines


def test_with_no_free_spot_the_box_goes_to_the_emptiest_corner() -> None:
    """The whole stamp band is map content; the top-left corner holds the least."""
    band = (SAFE_LEFT, SAFE_TOP_PX, WIDTH - SAFE_RIGHT_PX, 1152.0)
    heavy_right = (500.0, SAFE_TOP_PX, WIDTH - SAFE_RIGHT_PX, 1152.0)
    low = (SAFE_LEFT, 700.0, 500.0, 1152.0)
    start = render.Box(300.0, 600.0, 200.0, 120.0)
    placed, how = render.clear_spot(start, [band, heavy_right, low], margin=24.0,
                                    top=SAFE_TOP_PX, bottom=1152.0)  # fmt: skip
    assert how == "corner"
    assert (placed.left, placed.top) == (SAFE_LEFT, SAFE_TOP_PX)


def test_a_calendar_on_a_map_keeps_off_its_content_too() -> None:
    bare = render.map_layout(_map_beat(event=Event()), numbers=NUMBERS, geocoder=GAZETTEER)
    assert bare is not None
    spec = _calendar(1.0, end_s=2.9)
    moved, how = render.calendar_off_map(spec, bare, numbers=NUMBERS)
    # the 340 px page has no free spot above Saudi Arabia: the emptiest corner of the band
    assert how == "corner"
    margin = NUMBERS.info.map.stamp_margin_px
    content = render.map_content(bare)

    def covered(box: render.Box) -> float:
        return sum(render._covered(box, c, margin) for c in content)  # pyright: ignore[reportPrivateUsage]

    limit = EXPLAINER.broll.stamp_max_y_fraction * 1920
    corners = [render.Box(x, y, spec.width, spec.height)
               for y in (SAFE_TOP_PX, limit - spec.height)
               for x in (SAFE_LEFT, WIDTH - SAFE_RIGHT_PX - spec.width)]  # fmt: skip
    assert covered(render.calendar_box(moved)) == min(covered(c) for c in corners)


def test_a_calendar_keeps_off_a_face_on_the_picture() -> None:
    spec = _calendar(1.0)
    face = render.Box(spec.left - 20, spec.top - 20, spec.width + 40, spec.height + 40)
    moved, how = render.calendar_clear_of(spec, face, numbers=NUMBERS)
    assert how is not None
    box = (moved.left, moved.top, moved.left + moved.width, moved.top + moved.height)
    assert not _meet(box, (face.left, face.top, face.right, face.bottom))


# --- one real render (Remotion) ------------------------------------------------------------


Frame = tuple[int, int, bytes]
CAL_FRAMES = 45


def _region_diff(a: Frame, b: Frame, box: tuple[float, float, float, float]) -> float:
    width, _, da = a
    _, _, db = b
    left, top, w, h = (round(v) for v in box)
    total, n = 0, 0
    for y in range(top, top + h, 4):
        for x in range(left, left + w, 4):
            i = 3 * (y * width + x)
            total += sum(abs(da[i + k] - db[i + k]) for k in range(3))
            n += 3
    return total / max(1, n)


def test_the_page_flips_from_one_year_to_the_next_on_the_word(
    tmp_path: Path, fixture_clip: Path
) -> None:
    """108 through Remotion: one 1.5 s `off` beat whose word lands at 1.0 s. Before the
    flip the page shows 1937; while it flips it changes; from the landing on it holds
    1938, still; before it appears there is no page."""
    assert ROW is not None
    base = render.build_spec(
        PicturePlan.model_validate({
            "prompt_version": "t", "cut": {"keep": [{"start": 0.0, "end": 1.5}]},
            "beats": [{"id": "b01", "start": 0.0, "end": 1.5, "mode": "off", "kind": "photo"}],
            "finale": {"beat_id": "none", "text": ""}, "title": "t", "description": "t",
        }),
        Captions(pages=[]), presenter=fixture_clip,
        source_size=ffmpeg.video_size(fixture_clip), duration_s=1.5, numbers=NUMBERS,
    )  # fmt: skip
    cal = render.calendar_spec(YEAR.model_copy(update={"at_s": 1.0}), beat_start_s=0.0,
                               beat_end_s=1.5, numbers=NUMBERS)  # fmt: skip
    beat = BeatSpec(id="b01", start_frame=0, end_frame=CAL_FRAMES, mode="off", kind="photo",
                    calendar=cal)  # fmt: skip
    spec = base.model_copy(update={"beats": [beat], "frames": CAL_FRAMES})
    work = tmp_path / "cal"
    work.mkdir()
    render.run_driver(spec, spec_path=work / "spec.json", out_path=work / "p.mp4",
                      log_path=work / "r.log")  # fmt: skip
    frames = ffmpeg.frames_rgb(work / "p.mp4", fps=30, width=1080, duration_s=1.5)
    page = (cal.left, cal.top + cal.header_px, cal.width, cal.height - cal.header_px)
    before = round(cal.appear_s * 30) + 2  # showing 1937
    flip = round((cal.flip_start_s + cal.land_s) / 2 * 30)
    landed = round(cal.land_s * 30) + 1
    assert _region_diff(frames[0], frames[before], page) > 20  # no page, then 1937
    assert _region_diff(frames[before], frames[landed], page) > 3  # 1937 -> 1938
    assert _region_diff(frames[before], frames[flip], page) > 3  # mid-flip
    assert _region_diff(frames[landed], frames[landed + 5], page) < 1.0  # it holds, still


# --- the prompt and the editor ------------------------------------------------------------


def test_the_picture_prompt_names_the_calendar() -> None:
    text = (Path(__file__).parents[1] / "src" / "shortsmith" / "planner" / "prompts"
            / "picture_v20.md").read_text(encoding="utf-8")  # fmt: skip
    assert "`calendar`" in text and "broll.calendar.max_per_60s" in text
    assert "broll.calendar.chars_max" in text and "instead of a stamp" in text


def test_the_editor_can_drop_a_calendar() -> None:
    from shortsmith.editor import repairs

    plan = _with(_plan(), "b01", calendar=YEAR)
    assert "calendar" in repairs.layers_of(plan.beats[0])
    assert repairs.drop_layer(plan, "b01", "calendar").beats[0].calendar is None
    assert repairs.strip_overlays(plan).beats[0].calendar is None
