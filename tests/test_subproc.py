"""subproc.stream: line-by-line stdout with stderr kept, under the same watchdog
registration as `subproc.run` (ticket 004 needs it for render progress)."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shortsmith import subproc

SCRIPT = (
    "import sys, time\n"
    "for i in range(3):\n"
    "    print(f'progress {i}/3', flush=True)\n"
    "print('warn', file=sys.stderr, flush=True)\n"
    "print('done', flush=True)\n"
)


def test_stream_delivers_stdout_lines_in_order_and_tags_stderr() -> None:
    seen: list[tuple[str, str]] = []
    proc = subproc.stream(
        [sys.executable, "-c", SCRIPT], lambda s, line: seen.append((s, line)), timeout_s=30
    )
    assert proc.returncode == 0
    assert [line for s, line in seen if s == "out"] == [
        "progress 0/3",
        "progress 1/3",
        "progress 2/3",
        "done",
    ]
    assert ("err", "warn") in seen


def test_run_feeds_stdin_and_honours_cwd_and_env(tmp_path: Path) -> None:
    """014: the Claude CLI gets its prompt on stdin, runs in the job's planner
    directory and sees only the environment the adapter hands it."""
    script = (
        "import os, sys\n"
        "print(sys.stdin.read().upper())\n"
        "print(os.getcwd())\n"
        "print(os.environ.get('SHORTSMITH_PROBE', 'absent'))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "SHORTSMITH_PROBE"}
    done = subproc.run(
        [sys.executable, "-c", script], input="plan this", cwd=tmp_path, env=env, timeout_s=30
    )
    lines = done.stdout.decode().splitlines()
    assert lines[0] == "PLAN THIS"
    assert Path(lines[1]).resolve() == tmp_path.resolve()
    assert lines[2] == "absent"


def test_stream_is_killed_by_an_expired_watchdog() -> None:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    watchdog = subproc.Watchdog(deadline=now - timedelta(seconds=1), clock=lambda: now)
    assert watchdog.check()  # the deadline has passed; a child registered now is killed
    with subproc.guarded(watchdog), pytest.raises(subproc.Killed):
        subproc.stream(
            [sys.executable, "-c", "import time; time.sleep(30)"], lambda s, line: None
        )
