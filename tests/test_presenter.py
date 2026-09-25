"""presenter (ticket 005): the cut list on the output timeline from the plan's kept and
dropped spans and the cold-open lift with `keep | drop` (decisions 3.4, 8.1).

Ticket 013 (decision 3.3): the face measured once per job from eight stills at the
research strip times with the Haar detector, the median box, the early failure under
six hits, and the square full-width PIP window with the chin at `pip.chin_anchor` and
the circle grown for a large face. The window maths is pure and boundary-tested at
44.9 / 45.1 % of the source width; the detector runs for real on the fixture's drawn
face and on the faceless variant."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from shortsmith import fixture, jobs, presenter, render, styles
from shortsmith.contracts import (
    Constraints,
    CutPlan,
    FaceBox,
    Hook,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    Span,
)
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber

EXPLAINER = render.loaded_styles()[styles.DEFAULT]
PORTRAIT = (1080, 1920)


def _fake_plan() -> PicturePlan:
    transcript = FakeTranscriber().transcribe(Path("unused.mp4"))
    request = PlanRequest(
        brief="Topic: nothing.",
        style=PlanStyle(name="explainer"),
        style_note="explainer",
        transcript=transcript,
        references=[],
        constraints=Constraints(max_duration_s=60.0, target_duration_s=6.0),
        asset_policy="any",
    )
    return FakePlanner().plan_picture(request)


def _plan(
    *,
    keep: list[tuple[float, float]],
    drop: list[tuple[float, float]] | None = None,
    cold_open: tuple[float, float],
    original_position: str,
) -> PicturePlan:
    base = _fake_plan()
    return base.model_copy(
        update={
            "cut": CutPlan(
                keep=[Span(start=a, end=b) for a, b in keep],
                drop=[Span(start=a, end=b) for a, b in drop or []],
            ),
            "hook": Hook(
                title=base.hook.title,
                cold_open_span=Span(start=cold_open[0], end=cold_open[1]),
                original_position=original_position,  # type: ignore[arg-type]
                card_asset_ids=base.hook.card_asset_ids,
            ),
        }
    )


def _pairs(spans: list[Span]) -> list[tuple[float, float]]:
    return [(s.start, s.end) for s in spans]


def test_fake_plan_cut_list_is_the_whole_fixture_in_order() -> None:
    """The fake lifts its cold open from the head and drops it there: a no-op reorder,
    so the cut is the six seconds in source order and the smoke short stays 6 s."""
    spans = presenter.cut_list(_fake_plan())
    assert _pairs(spans) == [(0.0, 0.5), (0.5, 6.0)]
    assert presenter.total_duration(spans) == 6.0


def test_cold_open_lifted_from_the_middle_with_drop_is_absent_at_its_place() -> None:
    plan = _plan(keep=[(0.0, 6.0)], cold_open=(3.0, 3.5), original_position="drop")
    assert _pairs(presenter.cut_list(plan)) == [(3.0, 3.5), (0.0, 3.0), (3.5, 6.0)]


def test_cold_open_lifted_from_the_middle_with_keep_stays_at_its_place() -> None:
    plan = _plan(keep=[(0.0, 6.0)], cold_open=(3.0, 3.5), original_position="keep")
    spans = presenter.cut_list(plan)
    assert _pairs(spans) == [(3.0, 3.5), (0.0, 6.0)]
    assert presenter.total_duration(spans) == 6.5


def test_dropped_spans_are_removed_from_the_kept_spans() -> None:
    plan = _plan(
        keep=[(0.0, 6.0)],
        drop=[(1.0, 2.0), (4.5, 5.0)],
        cold_open=(0.0, 0.5),
        original_position="drop",
    )
    assert _pairs(presenter.cut_list(plan)) == [(0.0, 0.5), (0.5, 1.0), (2.0, 4.5), (5.0, 6.0)]


def test_kept_spans_are_sorted_and_a_drop_that_swallows_a_span_removes_it() -> None:
    plan = _plan(
        keep=[(4.0, 6.0), (0.0, 2.0), (2.5, 3.0)],
        drop=[(2.4, 3.1)],
        cold_open=(0.0, 0.5),
        original_position="drop",
    )
    assert _pairs(presenter.cut_list(plan)) == [(0.0, 0.5), (0.5, 2.0), (4.0, 6.0)]


def test_output_time_maps_a_source_time_onto_the_cut_timeline() -> None:
    plan = _plan(keep=[(0.0, 6.0)], cold_open=(3.0, 3.5), original_position="drop")
    spans = presenter.cut_list(plan)  # [3.0-3.5] [0.0-3.0] [3.5-6.0]
    assert presenter.output_time(spans, 3.2) == pytest.approx(0.2)
    assert presenter.output_time(spans, 0.0) == pytest.approx(0.5)
    assert presenter.output_time(spans, 4.0) == pytest.approx(4.0)
    assert presenter.output_time(spans, 3.5) == pytest.approx(3.5)  # a boundary is the later span


def test_source_time_is_the_inverse_of_output_time() -> None:
    """009: the grammar maps a beat boundary (output seconds) back to the recording
    before it looks for the nearest word end."""
    plan = _plan(keep=[(0.0, 6.0)], cold_open=(3.0, 3.5), original_position="drop")
    spans = presenter.cut_list(plan)  # [3.0-3.5] [0.0-3.0] [3.5-6.0]
    assert presenter.source_time(spans, 0.2) == pytest.approx(3.2)
    assert presenter.source_time(spans, 0.5) == pytest.approx(0.0)  # a boundary is the later span
    assert presenter.source_time(spans, 4.0) == pytest.approx(4.0)
    assert presenter.source_time(spans, 6.0) == pytest.approx(6.0)  # the runtime's end
    assert presenter.source_time(spans, 7.0) == pytest.approx(6.0)  # past the end clamps
    for t in (0.0, 0.2, 0.5, 1.7, 3.5, 5.9):
        assert presenter.output_time(spans, presenter.source_time(spans, t)) == pytest.approx(t)
    assert presenter.source_time([], 1.5) == 1.5


# --- ticket 013: the PIP window maths (decision 3.3) ---------------------------------


def _face(*, top: int, height: int, left: int = 300, width: int = 400) -> FaceBox:
    return FaceBox(left=left, top=top, width=width, height=height)


def test_window_is_full_source_width_square_with_the_chin_at_the_anchor() -> None:
    face = _face(top=800, height=400)  # chin at y 1200
    pip = presenter.pip_geometry(face, PORTRAIT, EXPLAINER)
    assert (pip.window_left, pip.window_size) == (0, 1080)
    chin_in_window = face.top + face.height - pip.window_top
    assert chin_in_window == pytest.approx(EXPLAINER.pip.chin_anchor * 1080, abs=1.0)
    assert pip.window_top == 314


@pytest.mark.parametrize(
    ("height", "diameter"),
    [
        (485, 300),  # 44.9 % of the source width: the style diameter
        (486, 300),  # exactly 45.0 %: still the style diameter (the rule is "more than")
        (487, 340),  # 45.1 %: the large-face diameter
    ],
)
def test_face_box_height_over_45_percent_of_the_width_grows_the_circle(
    height: int, diameter: int
) -> None:
    pip = presenter.pip_geometry(_face(top=600, height=height), PORTRAIT, EXPLAINER)
    assert pip.diameter == diameter
    assert diameter in (EXPLAINER.pip.diameter, EXPLAINER.pip.large_face_diameter)


def test_the_large_circle_grows_upward_from_the_same_bottom_edge() -> None:
    small = presenter.pip_geometry(_face(top=600, height=400), PORTRAIT, EXPLAINER)
    large = presenter.pip_geometry(_face(top=600, height=600), PORTRAIT, EXPLAINER)
    assert small.top + small.diameter == large.top + large.diameter == 1260
    assert (small.left, large.left) == (EXPLAINER.pip.left, EXPLAINER.pip.left)
    assert small.top == 960 and large.top == 920
    assert small.ring_px == EXPLAINER.pip.ring_px and small.ring_color == EXPLAINER.pip.ring_color


@pytest.mark.parametrize(
    ("face", "source", "expected"),
    [
        (_face(top=100, height=200), PORTRAIT, (0, 0)),  # chin near the top: no room above
        (_face(top=1700, height=200), PORTRAIT, (0, 840)),  # chin near the bottom: clamped
        (_face(top=100, height=300), (1920, 1080), (420, 0)),  # landscape: centred square
        (_face(top=1500, height=300), (1080, 2400), (0, 914)),  # tall: room below, not clamped
        (_face(top=2200, height=200), (1080, 2400), (0, 1320)),  # tall: clamped at 2400-1080
    ],
)
def test_window_never_leaves_the_source(
    face: FaceBox, source: tuple[int, int], expected: tuple[int, int]
) -> None:
    pip = presenter.pip_geometry(face, source, EXPLAINER)
    assert (pip.window_left, pip.window_top) == expected
    assert pip.window_size == min(source)
    assert 0 <= pip.window_left <= source[0] - pip.window_size
    assert 0 <= pip.window_top <= source[1] - pip.window_size


def test_the_median_box_is_per_edge_over_the_stills_with_a_face() -> None:
    boxes = [
        _face(top=100, height=400, left=300, width=400),
        None,
        _face(top=110, height=420, left=310, width=380),
        _face(top=90, height=440, left=290, width=390),
    ]
    assert presenter.median_box(boxes) == _face(top=100, height=420, left=300, width=390)


# --- the research strip times ----------------------------------------------------------


def test_strip_times_are_the_research_strip_on_the_research_runtime() -> None:
    assert presenter.STRIP_TIMES_S == (3.8, 6.5, 9.5, 17.0, 25.0, 36.0, 44.0, 53.0)
    assert presenter.strip_times(presenter.STRIP_RUNTIME_S) == presenter.STRIP_TIMES_S


def test_strip_times_scale_to_the_recording_and_stay_inside_it() -> None:
    times = presenter.strip_times(fixture.DURATION_S)
    assert len(times) == 8
    assert all(0 < a < b < fixture.DURATION_S for a, b in zip(times, times[1:], strict=False))
    assert times[0] == pytest.approx(3.8 * 6.0 / presenter.STRIP_RUNTIME_S, abs=1e-3)
    long = presenter.strip_times(480.0)
    assert long[-1] < 480.0 and long[-1] == pytest.approx(53.0 * 480.0 / 57.5, abs=1e-3)


# --- measure: the stills, the detector and the early failure ---------------------------


def _job(tmp_path: Path, clip: Path) -> jobs.Job:
    job = jobs.create(tmp_path, style=styles.DEFAULT)
    shutil.copyfile(clip, job.input_dir / "raw.mp4")
    return job


def test_measure_finds_the_fixture_face_on_all_eight_stills(
    tmp_path: Path, fixture_clip: Path
) -> None:
    job = _job(tmp_path, fixture_clip)
    pip = presenter.measure(job, EXPLAINER, detector=presenter.HaarDetector())
    stills = sorted(p.name for p in (job.work_dir / "frames").glob("strip_*.jpg"))
    assert stills == [f"strip_{n}.jpg" for n in range(1, 9)]
    measured = jobs.load(job.path).record.presenter
    assert measured is not None
    assert len(measured.faces) == 8 and all(f is not None for f in measured.faces)
    assert measured.times_s == list(presenter.strip_times(fixture.DURATION_S))
    assert (measured.source_width, measured.source_height) == PORTRAIT
    # The median box holds the drawn ellipse's centre and is about its size.
    cx, cy = fixture.FACE_CENTER
    face = measured.face
    assert face.left < cx < face.left + face.width and face.top < cy < face.top + face.height
    assert abs(face.height - 2 * fixture.FACE_HALF[1]) < 120
    assert pip == measured.pip == presenter.pip_geometry(face, PORTRAIT, EXPLAINER)
    assert (pip.window_left, pip.window_size) == (0, 1080)


def test_measure_fails_early_on_the_faceless_fixture(tmp_path: Path, faceless_clip: Path) -> None:
    job = _job(tmp_path, faceless_clip)
    with pytest.raises(presenter.NoFace, match="could not find your face"):
        presenter.measure(job, EXPLAINER, detector=presenter.HaarDetector())
    assert jobs.load(job.path).record.presenter is None
    assert len(list((job.work_dir / "frames").glob("strip_*.jpg"))) == 8


@pytest.mark.parametrize(("found", "ok"), [(6, True), (5, False)])
def test_six_of_eight_stills_with_a_face_is_the_floor(
    tmp_path: Path, fixture_clip: Path, found: int, ok: bool
) -> None:
    job = _job(tmp_path, fixture_clip)
    detector = presenter.FakeFaceDetector(found=found)
    if ok:
        presenter.measure(job, EXPLAINER, detector=detector)
        measured = jobs.load(job.path).record.presenter
        assert measured is not None and sum(f is not None for f in measured.faces) == 6
    else:
        with pytest.raises(presenter.NoFace):
            presenter.measure(job, EXPLAINER, detector=detector)
    assert len(detector.seen) == 8


def test_the_haar_detector_returns_none_on_a_flat_still(tmp_path: Path) -> None:
    from shortsmith.fixture import make_image

    still = make_image(tmp_path / "flat.jpg", width=640, height=640)
    assert presenter.HaarDetector().detect(still) is None
