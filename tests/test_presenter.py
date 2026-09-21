"""presenter (ticket 005): the cut list on the output timeline from the plan's kept and
dropped spans and the cold-open lift with `keep | drop` (decisions 3.4, 8.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import presenter
from shortsmith.contracts import (
    Constraints,
    CutPlan,
    Hook,
    PicturePlan,
    PlanRequest,
    PlanStyle,
    Span,
)
from shortsmith.planner import FakePlanner
from shortsmith.transcriber import FakeTranscriber


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
