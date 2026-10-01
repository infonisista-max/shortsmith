"""subproc.stream: line-by-line stdout with stderr kept, under the same watchdog
registration as `subproc.run` (ticket 004 needs it for render progress)."""

from __future__ import annotations

import os
import sys
import time
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


# --- 111e: the step budget, the stall clock and the backstop -------------------------------

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def at(self, seconds: float) -> None:
        self.now = T0 + timedelta(seconds=seconds)


def test_a_child_making_progress_is_never_killed_by_the_step_deadline() -> None:
    clock = _Clock()
    watchdog = subproc.Watchdog(deadline=T0 + timedelta(seconds=10), clock=clock, stall_s=60)
    watchdog.progress_started()
    for t in range(30, 600, 30):  # a beat every 30 s, far past the 10 s step deadline
        clock.at(t)
        watchdog.beat()
        assert not watchdog.check()
    clock.at(570 + 59)
    assert not watchdog.check()
    clock.at(570 + 60)  # 60 s with no new frame: a stall
    assert watchdog.check()
    assert watchdog.reason == "stall"


def test_after_a_progressing_child_the_step_keeps_its_tail() -> None:
    clock = _Clock()
    watchdog = subproc.Watchdog(clock=clock, stall_s=60)
    watchdog.arm(10, tail_s=5)
    watchdog.progress_started()
    clock.at(100)
    watchdog.beat()
    watchdog.progress_ended()  # past the deadline: the work after it still gets 5 s
    clock.at(104)
    assert not watchdog.check()
    clock.at(105)
    assert watchdog.check()
    assert watchdog.reason == "step"


def test_the_backstop_kills_even_a_child_making_progress() -> None:
    clock = _Clock()
    watchdog = subproc.Watchdog(clock=clock, stall_s=60, hard_deadline=T0 + timedelta(seconds=50))
    watchdog.arm(1000)
    watchdog.progress_started()
    clock.at(49)
    watchdog.beat()
    assert not watchdog.check()
    clock.at(50)
    assert watchdog.check()
    assert watchdog.reason == "job"


def test_arm_gives_a_fresh_step_budget_after_one_ran_out() -> None:
    clock = _Clock()
    watchdog = subproc.Watchdog(deadline=T0 + timedelta(seconds=10), clock=clock)
    clock.at(10)
    assert watchdog.check()
    assert watchdog.reason == "step"
    watchdog.arm(10)  # a retry or a rescue rewind enters the step afresh
    assert not watchdog.expired and watchdog.reason is None
    clock.at(19)
    assert not watchdog.check()
    clock.at(20)
    assert watchdog.check()


TICKER = (
    "import time\n"
    "for i in range(30):\n"
    "    print(f'progress {i}/30', flush=True)\n"
    "    time.sleep(0.05)\n"
)


def test_a_process_printing_progress_past_the_old_cap_is_not_killed() -> None:
    watchdog = subproc.Watchdog(
        deadline=datetime.now(UTC) + timedelta(seconds=0.2),
        clock=lambda: datetime.now(UTC), interval_s=0.02, stall_s=1.0,
    )  # fmt: skip
    seen: list[str] = []
    watchdog.start()
    try:
        with subproc.guarded(watchdog):
            proc = subproc.stream(
                [sys.executable, "-c", TICKER], lambda s, line: seen.append(line), progress=True
            )
    finally:
        watchdog.stop()
    assert proc.returncode == 0
    assert len(seen) == 30  # ~1.5 s of progress, well past the 0.2 s step deadline


def test_a_silent_process_is_killed_at_the_stall_limit() -> None:
    watchdog = subproc.Watchdog(
        deadline=datetime.now(UTC) + timedelta(hours=1),
        clock=lambda: datetime.now(UTC), interval_s=0.02, stall_s=0.5,
    )  # fmt: skip
    started = time.monotonic()
    watchdog.start()
    try:
        with subproc.guarded(watchdog), pytest.raises(subproc.Killed, match="no progress"):
            subproc.stream(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                lambda s, line: None, progress=True,
            )  # fmt: skip
    finally:
        watchdog.stop()
    assert time.monotonic() - started < 15
    assert watchdog.reason == "stall"
