"""Rate limiting for the public endpoint.

A single worker keeps counters in memory, which is enough for the target
deployment (one uvicorn process). The counter is keyed by app_id and a
hash of the client IP, so one noisy phone cannot exhaust another's quota
and no raw IP is stored.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque

from app.config import get_settings


def hash_ip(ip: str) -> str:
    salt = get_settings().ip_hash_salt
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()


class SlidingWindowLimiter:
    """Counts events in a rolling window, per key."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, bucket: deque[float], now: float) -> None:
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def allow(self, key: str) -> bool:
        """True when the event fits in the window; records it when allowed."""
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            self._prune(bucket, now)
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            self._prune(bucket, now)
            return max(0, self.limit - len(bucket))

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_settings = get_settings()
submission_limiter = SlidingWindowLimiter(
    limit=_settings.submissions_per_hour, window_seconds=3600
)
login_limiter = SlidingWindowLimiter(
    limit=_settings.admin_login_attempts_per_15min, window_seconds=900
)


def check_submission_rate(app_id: str, client_ip: str) -> bool:
    return submission_limiter.allow(f"{app_id}:{hash_ip(client_ip)}")


def check_login_rate(client_ip: str) -> bool:
    return login_limiter.allow(hash_ip(client_ip))
