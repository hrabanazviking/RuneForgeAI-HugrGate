"""Slice 265 — clock-skew simulation and audit tests."""

from __future__ import annotations

import pytest

from hugrgate.chaos import SkewedClock, audit_deadline_clocks
from hugrgate.circuit import CircuitRegistry
from hugrgate.cluster.discovery import DEFAULT_STALE_AFTER_S, PeerRecord
from hugrgate.errors import SpecError

# --- SkewedClock semantics ----------------------------------------------------------------------------

def test_skewed_clock_jump_and_advance():
    base = [1000.0]
    clock = SkewedClock(base=lambda: base[0])
    assert clock.now() == pytest.approx(1000.0)
    assert clock() == pytest.approx(1000.0)  # callable
    clock.jump(3600.0)  # NTP steps an hour forward
    assert clock.now() == pytest.approx(4600.0)
    assert clock.offset == pytest.approx(3600.0)
    clock.jump(-7200.0)  # ...then two hours back
    assert clock.now() == pytest.approx(-2600.0)
    base[0] += 10.0  # base still moves underneath
    assert clock.now() == pytest.approx(-2590.0)
    clock.advance(5.0)
    assert clock.now() == pytest.approx(-2585.0)
    with pytest.raises(SpecError, match="seconds >= 0"):
        clock.advance(-1.0)


def test_skewed_clock_defaults_to_monotonic():
    import time
    clock = SkewedClock()
    before = time.monotonic()
    assert before <= clock.now() <= time.monotonic()


# --- the audit: every enforcement path is monotonic --------------------------------------------------------

def test_audit_reports_monotonic_everywhere():
    report = audit_deadline_clocks()
    assert set(report) == {
        "hugrgate.circuit.CircuitRegistry",
        "hugrgate.chaos.framework.ExperimentRunner",
        "hugrgate.edge.watchdog.EdgeWatchdog",
        "hugrgate.cache.DecisionCache",
        "hugrgate.timeout.run_with_deadline",
    }
    for component, kind in report.items():
        assert "monotonic" in kind, f"{component} uses {kind}"
        assert "UNEXPECTED" not in kind, component


# --- injected clocks are followed (production default is what immunizes) -----------------------------------

def test_breaker_follows_its_given_clock():
    base = [0.0]
    skewed = SkewedClock(base=lambda: base[0])
    circuits = CircuitRegistry(failure_threshold=1, reset_timeout_s=60.0,
                               clock=skewed)
    breaker = circuits.get("b")
    breaker.record_failure()
    assert breaker.state == "open"
    base[0] += 30.0  # only 30s elapsed: still open
    assert breaker.allow() is False
    skewed.jump(3600.0)  # the given clock jumps an hour...
    assert breaker.allow() is True  # ...and the breaker follows it
    # The lesson, not a bug: injected clocks are obeyed. Production
    # wires time.monotonic (see audit), which never jumps.


# --- wall-clock durations degrade gracefully under skew ------------------------------------------------------

def test_peer_staleness_under_clock_skew():
    # A peer last seen 61s ago (stale threshold 60s).
    peer = PeerRecord(node_id="n1", host="h", port=1, last_seen=1000.0)
    assert peer.is_stale(now=1061.0) is True
    # Wall clock jumps BACKWARD an hour: the dead peer looks alive
    # again. Degraded routing until heartbeats resume — bounded and
    # self-healing, never a wrong decision.
    assert peer.is_stale(now=1061.0 - 3600.0) is False
    # Wall clock jumps FORWARD an hour: a live peer looks dead.
    fresh = PeerRecord(node_id="n2", host="h", port=1, last_seen=1060.0)
    assert fresh.is_stale(now=1060.0) is False
    assert fresh.is_stale(now=1060.0 + 3600.0,
                          stale_after_s=DEFAULT_STALE_AFTER_S) is True
