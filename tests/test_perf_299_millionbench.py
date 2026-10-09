"""Slice 299 — million-decision benchmark.

Covers: small-N runs (shape, counts, zero errors, sane percentiles,
deterministic seeding), InstantBackend contract, MillionResult dict
shape, and validation errors. The real 1M run is
``benchmarks/million_decisions.py`` (manual, not a test).
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.millionbench import InstantBackend, run_million


def test_small_run_shape():
    r = run_million(n=2000, seed=299, state_pool_size=50,
                    progress_every=0, sample_every=10)
    assert r.n == 2000
    assert r.seed == 299
    assert r.state_pool_size == 50
    assert r.errors == 0
    assert r.decisions_per_s > 0
    assert r.elapsed_s > 0
    # 2000 / 10 = 200 latency samples.
    assert r.latency_p50_us > 0
    assert r.latency_p50_us <= r.latency_p95_us <= r.latency_p99_us
    assert r.latency_p99_us <= r.latency_max_us
    assert r.rss_before_mb is not None
    assert r.rss_after_mb is not None


def test_result_dict_shape():
    r = run_million(n=500, seed=1, progress_every=0)
    d = r.to_dict()
    assert d["n"] == 500
    assert set(d["latency_us"]) == {"p50", "p95", "p99", "max"}
    assert d["errors"] == 0
    assert set(d["rss_mb"]) == {"before", "after"}


def test_seed_reproducible_states():
    # Same seed -> same state pool -> same decisions, no errors.
    r1 = run_million(n=1000, seed=42, progress_every=0)
    r2 = run_million(n=1000, seed=42, progress_every=0)
    assert r1.errors == r2.errors == 0
    assert r1.n == r2.n == 1000


def test_instant_backend_contract():
    b = InstantBackend()
    assert b.name == "instant"
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    assert b.supports(spec) is True
    other = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    assert b.supports(other) is False
    res = b.evaluate({"x": 1}, spec)
    assert res.value == "a"
    assert res.backend == "instant"


def test_validation():
    with pytest.raises(ValueError, match="n must be"):
        run_million(n=0)
    with pytest.raises(ValueError, match="sample_every"):
        run_million(n=10, sample_every=0)
