"""Rate limiter tests."""

from __future__ import annotations

import time

from stx.translate.rate_limit import AdaptiveLimiter, TokenBucket


def test_token_bucket_allows_burst_then_paces() -> None:
    bucket = TokenBucket(capacity=3, period_seconds=1.0)
    started = time.monotonic()
    for _ in range(3):
        bucket.acquire()
    fast_elapsed = time.monotonic() - started
    assert fast_elapsed < 0.2  # burst absorbed instantly

    started = time.monotonic()
    bucket.acquire()
    slow_elapsed = time.monotonic() - started
    assert slow_elapsed > 0.2  # 4th token had to wait for refill


def test_adaptive_limiter_grows_on_success_and_shrinks_on_failure() -> None:
    limiter = AdaptiveLimiter(max_capacity=10, min_capacity=1, period_seconds=1.0)
    initial = limiter.current_capacity
    for _ in range(10):
        limiter.report_failure()
    assert limiter.current_capacity < initial
    assert limiter.current_capacity >= 1.0  # respects min
    for _ in range(20):
        limiter.report_success()
    assert limiter.current_capacity <= 10.0  # respects max
