"""`python -m shortsmith.bench` (ticket 004): renders the fixture composition and
prints seconds per frame and total seconds; ticket 007 records the figure."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import bench
from shortsmith.render import DriverResult


def test_report_prints_seconds_per_frame_and_totals() -> None:
    result = DriverResult(frames=180, render_s=13.5, bundle_s=4.0, wall_s=18.2)
    line = bench.report(result, concurrency=2)
    assert "0.075 s/frame" in line
    assert "180 frames" in line and "13.5 s render" in line
    assert "4.0 s bundle" in line and "18.2 s total" in line and "concurrency 2" in line


def test_bench_renders_the_fixture_and_prints_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bench.main([], root=tmp_path) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and "s/frame" in out and "180 frames" in out
    assert (tmp_path / "bench" / "picture.mp4").is_file()
