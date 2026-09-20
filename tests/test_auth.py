"""auth (decision 11.2): a cookie signed with a key derived from the passcode, 7-day
life measured from the signed timestamp, constant-time checks, and the per-IP
failure log with a fake clock: 10 failures in 10 min -> one hour block."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shortsmith import auth
from shortsmith.auth import FailureLog

T0 = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
PASSCODE = "open-sesame-for-tests"


class Ticker:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


def test_cookie_round_trips_and_carries_no_passcode() -> None:
    value = auth.issue_cookie(PASSCODE, now=T0)
    assert auth.verify_cookie(value, PASSCODE, now=T0)
    assert auth.verify_cookie(value, PASSCODE, now=T0 + timedelta(days=3))
    assert PASSCODE not in value
    assert value.isascii() and ";" not in value and " " not in value


def test_cookie_expires_seven_days_after_it_was_signed() -> None:
    value = auth.issue_cookie(PASSCODE, now=T0)
    assert auth.verify_cookie(value, PASSCODE, now=T0 + timedelta(days=7) - timedelta(seconds=1))
    assert not auth.verify_cookie(value, PASSCODE, now=T0 + timedelta(days=7, seconds=1))


def test_cookie_from_the_future_or_tampered_or_garbage_is_rejected() -> None:
    value = auth.issue_cookie(PASSCODE, now=T0)
    stamp, mac = value.split(".")
    assert not auth.verify_cookie(f"{int(stamp) + 60}.{mac}", PASSCODE, now=T0)
    assert not auth.verify_cookie(f"{stamp}.{'0' * len(mac)}", PASSCODE, now=T0)
    assert not auth.verify_cookie(value, PASSCODE, now=T0 - timedelta(seconds=120))
    for garbage in (None, "", ".", "abc", "123", "123.", ".abc", "x.y.z", stamp + ".zz"):
        assert not auth.verify_cookie(garbage, PASSCODE, now=T0)


def test_rotating_the_passcode_invalidates_every_cookie() -> None:
    old = auth.issue_cookie(PASSCODE, now=T0)
    assert not auth.verify_cookie(old, "a-new-passcode", now=T0)
    assert auth.issue_cookie(PASSCODE, now=T0) != auth.issue_cookie("a-new-passcode", now=T0)


def test_passcode_check_is_exact() -> None:
    assert auth.passcode_matches(PASSCODE, PASSCODE)
    assert not auth.passcode_matches(PASSCODE + " ", PASSCODE)
    assert not auth.passcode_matches("", PASSCODE)
    assert not auth.passcode_matches(PASSCODE.upper(), PASSCODE)


def test_ten_failures_in_ten_minutes_block_for_an_hour() -> None:
    clock = Ticker(T0)
    log = FailureLog(clock)
    for _ in range(9):
        log.record_failure("10.0.0.1")
        clock.advance(seconds=30)
    assert log.blocked_for("10.0.0.1") is None
    log.record_failure("10.0.0.1")  # tenth inside the window
    assert log.blocked_for("10.0.0.1") == 3600.0
    clock.advance(minutes=59, seconds=59)
    assert log.blocked_for("10.0.0.1") == 1.0
    clock.advance(seconds=1)
    assert log.blocked_for("10.0.0.1") is None
    # The block cleared the counter: one more failure does not re-block.
    log.record_failure("10.0.0.1")
    assert log.blocked_for("10.0.0.1") is None


def test_failures_older_than_ten_minutes_fall_out_of_the_window() -> None:
    clock = Ticker(T0)
    log = FailureLog(clock)
    for _ in range(9):
        log.record_failure("10.0.0.1")
    clock.advance(minutes=10, seconds=1)
    log.record_failure("10.0.0.1")  # only one inside the last ten minutes
    assert log.blocked_for("10.0.0.1") is None
    for _ in range(8):
        log.record_failure("10.0.0.1")
    assert log.blocked_for("10.0.0.1") is None
    log.record_failure("10.0.0.1")
    assert log.blocked_for("10.0.0.1") == 3600.0


def test_counters_are_per_ip() -> None:
    clock = Ticker(T0)
    log = FailureLog(clock)
    for _ in range(10):
        log.record_failure("10.0.0.1")
    assert log.blocked_for("10.0.0.1") == 3600.0
    assert log.blocked_for("10.0.0.2") is None
    log.record_failure("10.0.0.2")
    assert log.blocked_for("10.0.0.2") is None
