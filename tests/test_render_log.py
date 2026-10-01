"""111e: work/render.log is appended to, never overwritten; every line carries a UTC ISO
timestamp like job.log, and each phase writes a start line and an end line with its
elapsed seconds."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import render
from shortsmith.render import RenderLog

T0 = datetime(2026, 10, 1, 8, 20, 5, tzinfo=UTC)
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?\+00:00 ")


class _Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def test_every_line_is_timestamped_and_appended(tmp_path: Path) -> None:
    path = tmp_path / "render.log"
    path.write_text("2026-10-01T08:00:00+00:00 an earlier attempt\n", encoding="utf-8")
    clock = _Clock()
    log = RenderLog(path, now=clock)
    log.write("picture attempt 1/4: as planned")
    with log.lines() as write:
        write("[out] progress 1/10")
        clock.now = T0 + timedelta(seconds=2)
        write("[err] warn")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "2026-10-01T08:00:00+00:00 an earlier attempt"  # kept
    assert lines[1:] == [
        "2026-10-01T08:20:05+00:00 picture attempt 1/4: as planned",
        "2026-10-01T08:20:05+00:00 [out] progress 1/10",
        "2026-10-01T08:20:07+00:00 [err] warn",
    ]
    assert all(STAMP.match(line) for line in lines)


def test_a_phase_writes_its_start_and_its_end_with_the_elapsed_seconds(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    log = RenderLog(tmp_path / "render.log", now=clock)
    with log.phase("mux"):
        clock.now = T0 + timedelta(seconds=12.5)
    assert (tmp_path / "render.log").read_text(encoding="utf-8").splitlines() == [
        "2026-10-01T08:20:05+00:00 phase mux: start",
        "2026-10-01T08:20:17.500000+00:00 phase mux: end after 12.5 s",
    ]


def test_a_failing_phase_still_writes_its_end(tmp_path: Path) -> None:
    clock = _Clock()
    log = RenderLog(tmp_path / "render.log", now=clock)
    with pytest.raises(RuntimeError), log.phase("picture"):
        clock.now = T0 + timedelta(seconds=3)
        raise RuntimeError("driver died")
    last = (tmp_path / "render.log").read_text(encoding="utf-8").splitlines()[-1]
    assert last == "2026-10-01T08:20:08+00:00 phase picture: failed after 3.0 s"


def test_the_last_attempt_is_the_text_from_its_header_on() -> None:
    """QA's NetworkError check (T8) judges the render that made the picture, not a
    failed attempt the net or a retry already replaced."""
    text = (
        "t phase cut: start\n"
        "t picture attempt 1/4: as planned\n"
        "t [err] NetworkError: lost\n"
        "t picture attempt 2/4: b52 simplified\n"
        "t [out] done frames=10 render_s=1.0 bundle_s=0.0\n"
        "t phase mux: start\n"
    )
    last = render.last_attempt(text)
    assert "NetworkError" not in last
    assert last.startswith("t picture attempt 2/4")
    assert render.last_attempt("no header\n") == "no header\n"
