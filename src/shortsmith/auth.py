"""Passcode auth primitives (decision 11.2), stdlib only.

The session cookie is `<issued_unix>.<hmac_sha256_hex>` signed with a key derived
from the passcode itself, so changing `SHORTSMITH_PASSCODE` invalidates every cookie
without any server-side state. The 7-day life is measured from the signed timestamp,
not from the browser's cookie expiry, so a kept cookie cannot outlive it.

`FailureLog` is the in-memory per-IP counter: the tenth wrong passcode inside ten
minutes blocks that IP for an hour. It takes a clock so tests never sleep.
"""

from __future__ import annotations

import hashlib
import hmac
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from shortsmith.jobs import Clock

COOKIE_NAME = "shortsmith_session"
COOKIE_MAX_AGE_S = 7 * 24 * 60 * 60
WRONG_PASSCODE_DELAY_S = 2.0
FAILURE_LIMIT = 10
FAILURE_WINDOW_S = 10 * 60
BLOCK_S = 60 * 60

_KEY_LABEL = b"shortsmith session cookie v1"


def signing_key(passcode: str) -> bytes:
    """Derive the cookie signing key from the passcode; a new passcode is a new key."""
    return hmac.new(passcode.encode("utf-8"), _KEY_LABEL, hashlib.sha256).digest()


def _mac(passcode: str, stamp: str) -> str:
    return hmac.new(signing_key(passcode), stamp.encode("ascii"), hashlib.sha256).hexdigest()


def issue_cookie(passcode: str, *, now: datetime) -> str:
    stamp = str(int(now.timestamp()))
    return f"{stamp}.{_mac(passcode, stamp)}"


def verify_cookie(value: str | None, passcode: str, *, now: datetime) -> bool:
    """True when `value` was signed with `passcode` at most 7 days ago (and not in the future)."""
    if not value or value.count(".") != 1:
        return False
    stamp, mac = value.split(".")
    if not stamp.isdigit() or not mac:
        return False
    if not hmac.compare_digest(mac, _mac(passcode, stamp)):
        return False
    age = now.timestamp() - int(stamp)
    return 0 <= age <= COOKIE_MAX_AGE_S


def passcode_matches(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


@dataclass
class _IpState:
    failures: deque[float] = field(default_factory=deque[float])
    blocked_until: float | None = None


class FailureLog:
    """Per-IP wrong-passcode counter with a sliding window and a fixed block."""

    def __init__(
        self,
        clock: Clock,
        *,
        limit: int = FAILURE_LIMIT,
        window_s: float = FAILURE_WINDOW_S,
        block_s: float = BLOCK_S,
    ) -> None:
        self._clock = clock
        self._limit = limit
        self._window_s = window_s
        self._block_s = block_s
        self._ips: dict[str, _IpState] = {}

    def blocked_for(self, ip: str) -> float | None:
        """Seconds until `ip` may try again, or None when it is not blocked."""
        state = self._ips.get(ip)
        if state is None or state.blocked_until is None:
            return None
        remaining = state.blocked_until - self._clock().timestamp()
        if remaining <= 0:
            # The block has run its course; the counter starts afresh.
            del self._ips[ip]
            return None
        return remaining

    def record_failure(self, ip: str) -> None:
        if self.blocked_for(ip) is not None:
            return
        now = self._clock().timestamp()
        state = self._ips.setdefault(ip, _IpState())
        state.failures.append(now)
        while state.failures and now - state.failures[0] > self._window_s:
            state.failures.popleft()
        if len(state.failures) >= self._limit:
            state.blocked_until = now + self._block_s
            state.failures.clear()
