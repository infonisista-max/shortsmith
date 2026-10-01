"""Subprocess launching that a job's watchdog can kill (decision 11.2; budgets per step, 111e).

`run(argv)` is `subprocess.run` without a shell that registers the child with the
`Watchdog` guarding the current thread's job, if any. When the watchdog reaches a
limit (the step's budget, a stall, the job's backstop) it kills every registered child
and `run` raises `Killed` instead of returning, so the step ends promptly and the
worker fails the job at that step. A child launched after a limit is killed at once.
Steps that never spawn a process cannot be interrupted; the worker fails those on
return.

The watchdog polls an injected clock so tests drive it with a fake; ffmpeg, the
Remotion CLI and the Claude CLI all go through `run`, which is what makes them
killable without threading a handle through every adapter interface.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO

Clock = Callable[[], datetime]
LineSink = Callable[[str, str], None]  # (stream: "out" | "err", line without its newline)


class Killed(Exception):
    """The job's watchdog killed this process: its step ran out of time, it stopped
    making progress, or the job reached its overall backstop (111e)."""


Reason = str  # "step" | "stall" | "job"
_KILLED_TEXT: dict[Reason, str] = {
    "step": "its step ran past its time budget",
    "stall": "it made no progress for too long",
    "job": "the job ran past its overall time cap",
}


class Watchdog:
    """111e: one per job. `arm(seconds)` gives the step being entered its own budget
    (a retry or a rescue rewind arms afresh); `hard_deadline` is the job's backstop,
    which nothing re-arms. While a child that reports progress runs
    (`progress_started` .. `progress_ended`), the step deadline is suspended and the
    stall clock rules instead: it kills only after `stall_s` with no `beat`. When such
    a child ends, the step keeps at least the `tail_s` it was armed with, so the work
    after a long render (the next net round, the mux) is never dead on arrival."""

    def __init__(
        self,
        *,
        clock: Clock,
        deadline: datetime | None = None,
        interval_s: float = 1.0,
        hard_deadline: datetime | None = None,
        stall_s: float | None = None,
    ) -> None:
        self._deadline = deadline
        self._hard = hard_deadline
        self._stall = timedelta(seconds=stall_s) if stall_s is not None else None
        self._tail = timedelta(0)
        self._beat: datetime | None = None
        self._clock = clock
        self._interval_s = interval_s
        self._procs: set[subprocess.Popen[bytes]] = set()
        self._lock = threading.Lock()
        self._expired = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.reason: Reason | None = None

    @property
    def expired(self) -> bool:
        return self._expired.is_set()

    def arm(self, seconds: float, *, tail_s: float = 0.0) -> None:
        """A fresh budget of `seconds` from now for the step being entered; a budget
        that ran out is forgiven, the backstop never is."""
        now = self._clock()
        with self._lock:
            self._deadline = now + timedelta(seconds=seconds)
            self._tail = timedelta(seconds=tail_s)
            self._beat = None
            if self.reason != "job":
                self._expired.clear()
                self.reason = None

    def progress_started(self) -> None:
        """A child that reports progress starts; the stall clock starts with it."""
        self.beat()

    def beat(self) -> None:
        with self._lock:
            self._beat = self._clock()

    def progress_ended(self) -> None:
        now = self._clock()
        with self._lock:
            self._beat = None
            if self._deadline is not None:
                self._deadline = max(self._deadline, now + self._tail)

    def register(self, proc: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._procs.add(proc)
            if self._expired.is_set():
                proc.kill()

    def unregister(self, proc: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._procs.discard(proc)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="shortsmith-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_s * 5))
            self._thread = None

    def check(self) -> bool:
        """Consult the clock now (not the poll thread) and fire if a limit passed."""
        if not self._expired.is_set():
            reason = self._due(self._clock())
            if reason is not None:
                self._fire(reason)
        return self._expired.is_set()

    def _due(self, now: datetime) -> Reason | None:
        with self._lock:
            if self._hard is not None and now >= self._hard:
                return "job"
            if self._beat is not None and self._stall is not None:
                return "stall" if now - self._beat >= self._stall else None
            if self._deadline is not None and now >= self._deadline:
                return "step"
            return None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.check()
            self._stop.wait(self._interval_s)

    def _fire(self, reason: Reason) -> None:
        with self._lock:
            self.reason = reason
            self._expired.set()
            for proc in self._procs:
                proc.kill()

    def killed(self, argv0: str) -> Killed:
        return Killed(f"{argv0} was stopped: {_KILLED_TEXT.get(self.reason or 'step')}")


_current = threading.local()


def current() -> Watchdog | None:
    return getattr(_current, "watchdog", None)


@contextmanager
def guarded(watchdog: Watchdog | None) -> Generator[None]:
    """Make `watchdog` the one `run` registers with on this thread; None guards nothing."""
    previous = current()
    _current.watchdog = watchdog
    try:
        yield
    finally:
        _current.watchdog = previous


def run(
    argv: list[str],
    *,
    timeout_s: float | None = None,
    input: str | None = None,  # noqa: A002 - subprocess's own name for stdin text
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run `argv` with captured output; the return code is the caller's to judge.
    `input` is written to stdin as UTF-8; `env` replaces the inherited environment.

    Raises `Killed` when the current watchdog stopped the child, and
    `subprocess.TimeoutExpired` past `timeout_s` (the child is killed first).
    """
    watchdog = current()
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if input is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=dict(env) if env is not None else None,
    )
    if watchdog is not None:
        watchdog.register(proc)
    try:
        try:
            data = input.encode("utf-8") if input is not None else None
            out, err = proc.communicate(input=data, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
    finally:
        if watchdog is not None:
            watchdog.unregister(proc)
    if watchdog is not None and watchdog.expired:
        raise watchdog.killed(argv[0])
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def stream(
    argv: list[str],
    on_line: LineSink,
    *,
    timeout_s: float | None = None,
    cwd: Path | None = None,
    progress: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    """Like `run`, but every stdout and stderr line reaches `on_line` as it arrives
    (the render driver reports frame progress this way). Output is not returned; the
    caller keeps what it needs from the lines.

    `progress` (111e): the child reports progress on stdout, so each stdout line is the
    watchdog's heartbeat; while it runs the stall clock rules, not the step deadline."""
    watchdog = current()
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    pacer = watchdog if progress else None
    if watchdog is not None:
        watchdog.register(proc)
    sink = on_line if pacer is None else _beating(pacer, on_line)
    if pacer is not None:
        pacer.progress_started()
    assert proc.stdout is not None and proc.stderr is not None
    err_thread = threading.Thread(
        target=_pump, args=(proc.stderr, "err", sink), name="shortsmith-stderr", daemon=True
    )
    err_thread.start()
    timer: threading.Timer | None = None
    timed_out = False

    def expire() -> None:
        nonlocal timed_out
        timed_out = True
        proc.kill()

    if timeout_s is not None:
        timer = threading.Timer(timeout_s, expire)
        timer.start()
    try:
        _pump(proc.stdout, "out", sink)
        proc.wait()
        err_thread.join()
    finally:
        if timer is not None:
            timer.cancel()
        if pacer is not None:
            pacer.progress_ended()
        if watchdog is not None:
            watchdog.unregister(proc)
    if watchdog is not None and watchdog.expired:
        raise watchdog.killed(argv[0])
    if timed_out:
        raise subprocess.TimeoutExpired(argv, timeout_s or 0)
    return subprocess.CompletedProcess(argv, proc.returncode, b"", b"")


def _beating(watchdog: Watchdog, on_line: LineSink) -> LineSink:
    def sink(stream: str, line: str) -> None:
        if stream == "out":
            watchdog.beat()
        on_line(stream, line)

    return sink


def _pump(pipe: IO[bytes], name: str, on_line: LineSink) -> None:
    with pipe:
        for raw in iter(pipe.readline, b""):
            on_line(name, raw.decode("utf-8", errors="replace").rstrip("\r\n"))
