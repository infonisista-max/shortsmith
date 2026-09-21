"""Subprocess launching that a job's watchdog can kill (decision 11.2, `MAX_JOB_MINUTES`).

`run(argv)` is `subprocess.run` without a shell that registers the child with the
`Watchdog` guarding the current thread's job, if any. When the watchdog reaches its
deadline it kills every registered child and `run` raises `Killed` instead of
returning, so the step ends promptly and the worker fails the job at that step. A
child launched after the deadline is killed at once. Steps that never spawn a
process cannot be interrupted; the worker fails those on return.

The watchdog polls an injected clock so tests drive it with a fake; ffmpeg, the
Remotion CLI and the Claude CLI all go through `run`, which is what makes them
killable without threading a handle through every adapter interface.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime

Clock = Callable[[], datetime]


class Killed(Exception):
    """The job's watchdog killed this process because the job ran past its limit."""


class Watchdog:
    def __init__(self, *, deadline: datetime, clock: Clock, interval_s: float = 1.0) -> None:
        self._deadline = deadline
        self._clock = clock
        self._interval_s = interval_s
        self._procs: set[subprocess.Popen[bytes]] = set()
        self._lock = threading.Lock()
        self._expired = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def expired(self) -> bool:
        return self._expired.is_set()

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
        """Consult the clock now (not the poll thread) and fire if the deadline passed."""
        if not self._expired.is_set() and self._clock() >= self._deadline:
            self._fire()
        return self._expired.is_set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self.check():
                return
            self._stop.wait(self._interval_s)

    def _fire(self) -> None:
        with self._lock:
            self._expired.set()
            for proc in self._procs:
                proc.kill()


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


def run(argv: list[str], *, timeout_s: float | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run `argv` with captured output; the return code is the caller's to judge.

    Raises `Killed` when the current watchdog stopped the child, and
    `subprocess.TimeoutExpired` past `timeout_s` (the child is killed first).
    """
    watchdog = current()
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if watchdog is not None:
        watchdog.register(proc)
    try:
        try:
            out, err = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
    finally:
        if watchdog is not None:
            watchdog.unregister(proc)
    if watchdog is not None and watchdog.expired:
        raise Killed(f"{argv[0]} was stopped: the job ran past its time limit")
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)
