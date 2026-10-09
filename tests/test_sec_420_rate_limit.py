"""Slice 420 — per-key rate limiting.

Flood tests: a burst past capacity is rejected with a
retry-after hint, keys are isolated, anonymous callers get the
harshest budget, and a key-spoofing flood cannot grow the table
without bound.
"""

from __future__ import annotations

import threading
import time

import pytest

from hugrgate.errors import RateLimitExceeded
from hugrgate.security.ratelimit import RateLimiter


def test_burst_then_reject_with_retry_after():
    limiter = RateLimiter(capacity=3, refill_per_second=1000.0)
    for _ in range(3):
        limiter.throttle("alice")
    with pytest.raises(RateLimitExceeded) as exc:
        limiter.throttle("alice")
    assert exc.value.recoverable is True
    assert exc.value.code == "rate_limit_exceeded"
    assert exc.value.details["retry_after_ms"] >= 0
    assert exc.value.details["key"] == "alice"


def test_refill_recovers():
    limiter = RateLimiter(capacity=2, refill_per_second=50.0)
    limiter.throttle("bob")
    limiter.throttle("bob")
    with pytest.raises(RateLimitExceeded):
        limiter.throttle("bob")
    time.sleep(0.05)  # ~2.5 tokens refill
    limiter.throttle("bob")  # no raise


def test_keys_are_isolated():
    limiter = RateLimiter(capacity=1, refill_per_second=0.01)
    limiter.throttle("alice")
    with pytest.raises(RateLimitExceeded):
        limiter.throttle("alice")
    limiter.throttle("bob")  # unaffected


def test_anonymous_tier_is_harsher():
    limiter = RateLimiter(capacity=100, refill_per_second=100.0)
    # Anonymous tier defaults to capacity//10 = 10.
    for _ in range(10):
        limiter.throttle("anon-1", tier=RateLimiter.ANONYMOUS)
    with pytest.raises(RateLimitExceeded):
        limiter.throttle("anon-1", tier=RateLimiter.ANONYMOUS)
    # The same key under the default tier still has budget.
    limiter.throttle("anon-1")


def test_custom_tier():
    limiter = RateLimiter(capacity=1, refill_per_second=0.01)
    limiter.set_tier("operator", 5, 5.0)
    for _ in range(5):
        limiter.throttle("op-1", tier="operator")
    with pytest.raises(RateLimitExceeded):
        limiter.throttle("op-1", tier="operator")


def test_key_table_bounded_under_spoof_flood():
    limiter = RateLimiter(capacity=5, refill_per_second=5.0,
                          max_keys=500)
    for i in range(5000):
        limiter.throttle(f"spoof-{i:05d}")
    assert limiter.stats()["tracked_keys"] <= 500


def test_rejected_counter():
    limiter = RateLimiter(capacity=1, refill_per_second=0.01)
    limiter.throttle("k")
    for _ in range(4):
        with pytest.raises(RateLimitExceeded):
            limiter.throttle("k")
    assert limiter.stats()["rejected"] == 4


def test_bad_arguments():
    limiter = RateLimiter()
    with pytest.raises(ValueError):
        limiter.throttle("")
    with pytest.raises(ValueError):
        limiter.throttle("k", n=0)
    with pytest.raises(ValueError):
        RateLimiter(capacity=0)
    with pytest.raises(ValueError):
        RateLimiter(refill_per_second=0)
    with pytest.raises(ValueError):
        limiter.set_tier("x", 0, 1.0)


def test_thread_safe():
    limiter = RateLimiter(capacity=10_000, refill_per_second=10_000.0,
                          max_keys=1000)
    admitted = 0
    lock = threading.Lock()

    def worker(n: int) -> None:
        nonlocal admitted
        for _i in range(200):
            try:
                limiter.throttle(f"w{n}")
            except RateLimitExceeded:  # expected once buckets drain
                pass
            else:
                with lock:
                    admitted += 1

    threads = [threading.Thread(target=worker, args=(n,))
               for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert admitted == 1600
    assert limiter.stats()["tracked_keys"] == 8
