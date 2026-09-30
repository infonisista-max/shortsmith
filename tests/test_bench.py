"""`python -m shortsmith.bench` (ticket 004): renders the fixture composition and
prints seconds per frame and total seconds; ticket 007 records the figure."""

from __future__ import annotations

from pathlib import Path

import pytest

from shortsmith import bench, render
from shortsmith.contracts import PICTURE_TREATMENTS, FaceBox
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


def test_the_treatment_bench_draws_one_beat_per_picture_treatment() -> None:
    """103: `python -m shortsmith.bench --treatments OUT` renders one short beat per
    treatment over the fixture's presenter and saves each landed frame as a PNG."""
    numbers = render.style_numbers("explainer")
    face = FaceBox(left=400, top=150, width=120, height=140)
    beats = bench.treatment_beats("image.jpg", (870, 614), numbers=numbers, pip_top=960,
                                  face=face)  # fmt: skip
    assert [b.visual.treatment for b in beats if b.visual] == list(PICTURE_TREATMENTS)
    assert [b.start_frame for b in beats] == [i * bench.TREATMENT_FRAMES for i in range(5)]
    assert all(b.end_frame - b.start_frame == bench.TREATMENT_FRAMES for b in beats)
    pl = numbers.broll.polaroid
    assert pl is not None and pl.drop_s < bench.TREATMENT_FRAMES / render.FPS  # landed
    assert bench.parse_args(["--treatments", "out"]) == (render.CONCURRENCY, Path("out"), None)
    with_image = bench.parse_args(["--treatments", "out", "--image", "a.jpg"])
    assert with_image is not None and with_image[2] == Path("a.jpg")
    assert bench.parse_args(["--bogus"]) is None
