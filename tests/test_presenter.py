"""presenter (ticket 005): the cut list on the output timeline from the plan's kept and
dropped spans (decisions 3.4 as amended by 055, 8.1): nothing is lifted, speech plays in
the speaker's order, and `tighten` removes only silence.

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
    PicturePlan,
    PlanRequest,
    PlanStyle,
    Span,
    Transcript,
    Word,
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
    *, keep: list[tuple[float, float]], drop: list[tuple[float, float]] | None = None
) -> PicturePlan:
    return _fake_plan().model_copy(
        update={
            "cut": CutPlan(
                keep=[Span(start=a, end=b) for a, b in keep],
                drop=[Span(start=a, end=b) for a, b in drop or []],
            ),
        }
    )


def _pairs(spans: list[Span]) -> list[tuple[float, float]]:
    return [(s.start, s.end) for s in spans]


def test_fake_plan_cut_list_is_the_whole_fixture_in_order() -> None:
    """055: nothing is lifted or dropped; the cut is the six seconds in source order and
    the smoke short stays 6 s."""
    spans = presenter.cut_list(_fake_plan())
    assert _pairs(spans) == [(0.0, 6.0)]
    assert presenter.total_duration(spans) == 6.0


def test_cut_list_round_trips_through_work_cut_json(tmp_path: Path) -> None:
    """031: the renderer writes the cut list it applied to `work/cut.json`, so gate T10
    reads the boundaries that were cut, not a re-derivation."""
    job = jobs.create(tmp_path)
    assert presenter.load_cut_list(job) is None
    spans = presenter.cut_list(_fake_plan())
    path = presenter.write_cut_list(job, spans)
    assert path == job.work_dir / "cut.json"
    assert presenter.load_cut_list(job) == spans
    assert '"spans"' in path.read_text(encoding="utf-8")


def test_dropped_spans_are_removed_from_the_kept_spans() -> None:
    plan = _plan(keep=[(0.0, 6.0)], drop=[(1.0, 2.0), (4.5, 5.0)])
    assert _pairs(presenter.cut_list(plan)) == [(0.0, 1.0), (2.0, 4.5), (5.0, 6.0)]


def test_kept_spans_are_sorted_and_a_drop_that_swallows_a_span_removes_it() -> None:
    plan = _plan(keep=[(4.0, 6.0), (0.0, 2.0), (2.5, 3.0)], drop=[(2.4, 3.1)])
    assert _pairs(presenter.cut_list(plan)) == [(0.0, 2.0), (4.0, 6.0)]


def test_output_time_maps_a_source_time_onto_the_cut_timeline() -> None:
    spans = presenter.cut_list(_plan(keep=[(0.0, 6.0)], drop=[(3.0, 3.5)]))  # [0-3.0] [3.5-6.0]
    assert presenter.output_time(spans, 0.2) == pytest.approx(0.2)
    assert presenter.output_time(spans, 3.2) == pytest.approx(3.0)  # inside the drop: its end
    assert presenter.output_time(spans, 4.0) == pytest.approx(3.5)
    assert presenter.output_time(spans, 3.5) == pytest.approx(3.0)  # a boundary is the later span
    assert presenter.output_time(spans, 6.0) == pytest.approx(5.5)  # the recording's end


def test_source_time_is_the_inverse_of_output_time() -> None:
    """009: the grammar maps a beat boundary (output seconds) back to the recording
    before it looks for the nearest word end."""
    spans = presenter.cut_list(_plan(keep=[(0.0, 6.0)], drop=[(3.0, 3.5)]))  # [0-3.0] [3.5-6.0]
    assert presenter.source_time(spans, 0.2) == pytest.approx(0.2)
    assert presenter.source_time(spans, 3.0) == pytest.approx(3.5)  # a boundary is the later span
    assert presenter.source_time(spans, 4.0) == pytest.approx(4.5)
    assert presenter.source_time(spans, 5.5) == pytest.approx(6.0)  # the runtime's end
    assert presenter.source_time(spans, 7.0) == pytest.approx(6.0)  # past the end clamps
    for t in (0.0, 0.2, 0.5, 1.7, 3.0, 5.4):
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


# --- ticket 055: pause tightening (3.4 as amended) ---------------------------------------
#
# `tighten` removes only silence: the head before the first word down to `lead_s`, and
# the middle of every pause between two kept words that runs past `max_pause_s`. No word
# is shortened, the tail after the last word is left alone, and every removed span is
# reported so the grammar can log it as a clamp.

F1_TRANSCRIPT = Path(__file__).parent / "fixtures" / "f1" / "transcript.json"


def _words(*spans: tuple[float, float]) -> list[Word]:
    return [Word(text=f"w{i}", start=a, end=b, segment=0) for i, (a, b) in enumerate(spans)]


def _gaps(spans: list[Span], words: list[Word]) -> list[float]:
    """The silence between consecutive kept words on the output timeline."""
    placed = [w for _, w in presenter.words_on_cut(spans, words)]
    return [round(b.start - a.end, 3) for a, b in zip(placed, placed[1:], strict=False)]


def test_a_pause_over_max_pause_s_loses_its_middle_and_keeps_half_on_each_side() -> None:
    words = _words((0.0, 0.5), (0.7, 1.2), (2.6, 3.0), (3.3, 3.8))  # 0.2, 1.4 and 0.3 s gaps
    spans, trims = presenter.tighten(
        [Span(start=0.0, end=4.5)], words, max_pause_s=0.6, lead_s=0.15
    )
    assert _pairs(spans) == [(0.0, 1.5), (2.3, 4.5)]  # 1.2 + 0.3 ... 2.6 - 0.3
    assert _gaps(spans, words) == [0.2, 0.6, 0.3]
    (trim,) = trims
    assert (trim.start, trim.end, trim.after, trim.gap_s) == (1.5, 2.3, "w1", 1.4)
    assert presenter.total_duration(spans) == pytest.approx(4.5 - 0.8)


def test_a_pause_exactly_at_max_pause_s_is_left_alone() -> None:
    words = _words((0.0, 0.5), (1.1, 1.5))
    spans, trims = presenter.tighten(
        [Span(start=0.0, end=2.0)], words, max_pause_s=0.6, lead_s=0.15
    )
    assert _pairs(spans) == [(0.0, 2.0)] and trims == []


def test_the_head_is_trimmed_to_the_lead_before_the_first_word() -> None:
    words = _words((0.9, 1.3), (1.5, 2.0))
    spans, trims = presenter.tighten(
        [Span(start=0.0, end=2.5)], words, max_pause_s=0.6, lead_s=0.15
    )
    assert _pairs(spans) == [(0.75, 2.5)]
    (trim,) = trims
    assert (trim.start, trim.end, trim.after) == (0.0, 0.75, None)
    # A head shorter than the lead stays, and so does the tail after the last word.
    close, none = presenter.tighten(
        [Span(start=0.8, end=2.5)], words, max_pause_s=0.6, lead_s=0.15
    )
    assert _pairs(close) == [(0.8, 2.5)] and none == []


def test_no_word_is_shortened_and_a_pause_across_a_planned_drop_is_not_touched() -> None:
    """A pause the planner already cut into (a drop between two kept spans) is the
    planner's; only pauses inside one kept span are tightened."""
    words = _words((0.0, 0.5), (0.7, 1.2), (3.0, 3.4), (3.6, 4.0))
    kept = [Span(start=0.0, end=1.4), Span(start=2.8, end=4.5)]
    spans, trims = presenter.tighten(kept, words, max_pause_s=0.6, lead_s=0.15)
    assert _pairs(spans) == [(0.0, 1.4), (2.8, 4.5)] and trims == []
    for word in words:
        assert any(s.start <= word.start and word.end <= s.end for s in spans), word


def test_the_f1_transcript_keeps_every_word_and_no_pause_over_the_explainer_maximum() -> None:
    """The F1 recording (job 20260927-041728-656506) has one pause over 0.6 s, 0.74 s
    after 'खिलाओ' at 19.06 s; tightening removes 0.14 s of silence and nothing else."""
    transcript = Transcript.model_validate_json(F1_TRANSCRIPT.read_text(encoding="utf-8"))
    words = transcript.words
    whole = [Span(start=0.0, end=transcript.duration_s)]
    spans, trims = presenter.tighten(
        whole, words, max_pause_s=EXPLAINER.cut.max_pause_s, lead_s=EXPLAINER.beats.snap_window_s
    )
    assert EXPLAINER.cut.max_pause_s == 0.6
    assert [(t.after, t.gap_s) for t in trims] == [("खिलाओ", 0.74)]
    assert presenter.total_duration(spans) == pytest.approx(transcript.duration_s - 0.14, abs=1e-3)
    assert max(_gaps(spans, words)) <= EXPLAINER.cut.max_pause_s + 1e-9
    placed = presenter.words_on_cut(spans, words)
    assert [i for i, _ in placed] == list(range(len(words)))  # every word, once, in order
    for (_, on_cut), word in zip(placed, words, strict=True):
        assert on_cut.end - on_cut.start == pytest.approx(word.end - word.start, abs=1e-3)
    assert spans[0].start == 0.0  # F1's first word starts at 0.0 s: no head to trim


def test_cut_list_is_the_kept_spans_minus_the_dropped_ones_in_recording_order() -> None:
    """055: no cold open, no lift; the cut is the planner's kept spans sorted, minus
    its drops. The fake plan's cut is the whole six seconds."""
    fake = _fake_plan()
    assert _pairs(presenter.cut_list(fake)) == [(0.0, 6.0)]
    plan = fake.model_copy(update={"cut": CutPlan(
        keep=[Span(start=4.0, end=6.0), Span(start=0.0, end=2.0), Span(start=2.5, end=3.0)],
        drop=[Span(start=2.4, end=3.1), Span(start=1.0, end=1.2)],
    )})  # fmt: skip
    assert _pairs(presenter.cut_list(plan)) == [(0.0, 1.0), (1.2, 2.0), (4.0, 6.0)]
