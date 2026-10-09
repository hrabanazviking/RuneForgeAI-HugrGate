"""Slice 262 — CPU-starvation simulation tests."""

from __future__ import annotations

import time

import pytest

from hugrgate.chaos import CPUStarvationSimulator
from hugrgate.errors import SpecError, TimeoutError
from hugrgate.fallback import FallbackChain
from hugrgate.spec import DecisionSpec
from hugrgate.timeout import TimeoutBackend
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


# --- simulator semantics -----------------------------------------------------------------------------

def test_share_validation():
    with pytest.raises(SpecError, match=r"\(0, 1\]"):
        CPUStarvationSimulator(share=0.0)
    with pytest.raises(SpecError, match=r"\(0, 1\]"):
        CPUStarvationSimulator(share=1.5)
    with pytest.raises(SpecError, match=r"\(0, 1\]"):
        CPUStarvationSimulator(share=-0.5)
    with pytest.raises(SpecError, match=r"\(0, 1\]"):
        CPUStarvationSimulator().set_share("half")  # type: ignore[arg-type]
    assert CPUStarvationSimulator(share=1.0).dilation == pytest.approx(1.0)
    assert CPUStarvationSimulator(share=0.25).dilation == pytest.approx(4.0)


def test_stretched_math():
    sim = CPUStarvationSimulator(share=0.5)
    assert sim.stretched(1.0) == pytest.approx(2.0)
    assert sim.stretched(0.0) == pytest.approx(0.0)
    with pytest.raises(SpecError, match="duration_s"):
        sim.stretched(-1.0)


def test_starve_backend_dilates_work():
    sim = CPUStarvationSimulator(share=0.5)
    starved = sim.starve_backend(StubBackend(name="slow"), base_delay_s=0.1)
    assert starved.name == "slow"
    assert starved.capabilities()["cpu_share"] == pytest.approx(0.5)
    assert starved.supports(_spec()) is True
    start = time.monotonic()
    assert starved.evaluate({}, _spec()).value == "a"
    assert time.monotonic() - start >= 0.2  # 0.1s dilated 2x
    with pytest.raises(SpecError, match="wraps a Backend"):
        sim.starve_backend("nope")  # type: ignore[arg-type]
    with pytest.raises(SpecError, match="base_delay_s"):
        sim.starve_backend(StubBackend(), base_delay_s=-1.0)


# --- resilience: deadlines still fire in real time under starvation ------------------------------------

def test_deadline_fires_in_real_time_under_starvation():
    # 4x starvation: 0.4s of work becomes 1.6s; the 0.5s deadline must
    # still fire at ~0.5s of *real* time, not dilated time.
    sim = CPUStarvationSimulator(share=0.25)
    starved = sim.starve_backend(StubBackend(name="starved"),
                                 base_delay_s=0.4)
    guarded = TimeoutBackend(starved, explicit_deadline_ms=500)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        guarded.evaluate({}, _spec())
    elapsed = time.monotonic() - start
    assert 0.5 <= elapsed < 1.6, f"deadline misfired at {elapsed:.2f}s"


def test_fallback_chain_routes_around_starved_backend():
    sim = CPUStarvationSimulator(share=0.1)  # 10x: 0.3s -> 3s
    starved = TimeoutBackend(
        sim.starve_backend(StubBackend(name="starved"), base_delay_s=0.3),
        explicit_deadline_ms=400)
    chain = FallbackChain([starved, StubBackend(name="healthy", value="b")])
    start = time.monotonic()
    result = chain.evaluate({}, _spec())
    elapsed = time.monotonic() - start
    assert result.value == "b"
    assert result.fallback_used is True
    assert elapsed < 3.0  # never waited out the dilated work
