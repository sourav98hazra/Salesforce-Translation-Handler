"""Adaptive rate limiting for translator backends.

The free Google endpoint and other public APIs return ``429 Too Many
Requests`` (or simply hang) when the caller exceeds an undocumented
per-second / per-minute budget.  This module gives the runner a
gentle, self-correcting pacer:

* :class:`TokenBucket` -- classic leaky-bucket; ``acquire()`` blocks
  until a token is available.
* :class:`AdaptiveLimiter` -- wraps a bucket and reacts to translator
  errors.  Successful runs gradually relax the bucket; transient
  failures shrink it.  The result is that a fixed-rate worker pool
  self-tunes to whatever rate the backend tolerates today.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class TokenBucket:
    """Thread-safe token bucket.  ``capacity`` tokens leak in over ``period``."""

    capacity: float = 8.0
    period_seconds: float = 1.0

    def __post_init__(self) -> None:
        self._tokens = float(self.capacity)
        self._lock = threading.Lock()
        self._last = time.monotonic()

    def acquire(self) -> None:
        """Block until a token is available, then consume it."""
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # Compute the shortest sleep that yields one token.
                rate = self.capacity / self.period_seconds
                sleep_for = (1.0 - self._tokens) / rate
            time.sleep(max(sleep_for, 0.001))

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        rate = self.capacity / self.period_seconds
        self._tokens = min(self.capacity, self._tokens + elapsed * rate)
        self._last = now


class AdaptiveLimiter:
    """Self-tuning wrapper around a :class:`TokenBucket`.

    * Every successful call gradually grows ``capacity`` back to the
      original value (cap at ``max_capacity``).
    * Every failure shrinks ``capacity`` by ``shrink_factor``, never
      below ``min_capacity``.

    The runner doesn't have to reason about specific HTTP response
    codes -- any exception or retry-fallback counts as a failure
    signal.
    """

    def __init__(
        self,
        max_capacity: float = 8.0,
        min_capacity: float = 1.0,
        period_seconds: float = 1.0,
        shrink_factor: float = 0.5,
        grow_increment: float = 0.25,
    ) -> None:
        self.max_capacity = max_capacity
        self.min_capacity = min_capacity
        self.shrink_factor = shrink_factor
        self.grow_increment = grow_increment
        self._period_seconds = period_seconds
        self._lock = threading.Lock()
        self._bucket = TokenBucket(capacity=max_capacity, period_seconds=period_seconds)

    def acquire(self) -> None:
        self._bucket.acquire()

    def report_success(self) -> None:
        with self._lock:
            current = self._bucket.capacity
            new_capacity = min(self.max_capacity, current + self.grow_increment)
            if new_capacity != current:
                self._bucket = TokenBucket(capacity=new_capacity, period_seconds=self._period_seconds)

    def report_failure(self) -> None:
        with self._lock:
            current = self._bucket.capacity
            new_capacity = max(self.min_capacity, current * self.shrink_factor)
            if new_capacity != current:
                self._bucket = TokenBucket(capacity=new_capacity, period_seconds=self._period_seconds)

    @property
    def current_capacity(self) -> float:
        with self._lock:
            return self._bucket.capacity
