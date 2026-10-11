"""Slice 6 — health-snapshot: snapshot() combines monitor scores/quarantines,
circuit breaker states, and FallbackChain.health() into one dict."""

from hugrgate.circuit import CircuitRegistry
from hugrgate.fallback import FallbackChain
from hugrgate.health import HealthMonitor, snapshot
from tests.conftest import StubBackend


def _wired():
    """Healthy + sick backends through all three sources."""
    monitor = HealthMonitor(quarantine_threshold=0.3,
                            max_consecutive_failures=5)
    registry = CircuitRegistry(failure_threshold=3)
    healthy = StubBackend(name="healthy")
    sick = StubBackend(name="sick")
    chain = FallbackChain([healthy, sick])

    # "healthy" backend: clean record -> high score, not quarantined.
    for _ in range(10):
        monitor.record("healthy", 20.0, ok=True)
    registry.get("healthy")

    # "sick" backend: repeated failures -> quarantined AND open circuit.
    for _ in range(6):
        monitor.record("sick", 5000.0, ok=False)
    breaker = registry.get("sick")
    for _ in range(3):
        breaker.record_failure()
    return monitor, registry, chain


def test_snapshot_reflects_quarantined_backend():
    monitor, registry, chain = _wired()
    snap = snapshot(monitor, registry, chain)

    sick = snap["backends"]["sick"]
    assert sick["quarantined"] is True
    assert sick["score"] < 0.3
    assert "sick" in snap["quarantined"]

    healthy = snap["backends"]["healthy"]
    assert healthy["quarantined"] is False
    assert healthy["score"] > 0.9
    assert "healthy" not in snap["quarantined"]


def test_snapshot_reflects_open_circuit():
    monitor, registry, chain = _wired()
    snap = snapshot(monitor, registry, chain)

    assert snap["backends"]["sick"]["circuit"] == "open"
    assert snap["backends"]["healthy"]["circuit"] == "closed"


def test_snapshot_includes_fallback_chain_health():
    monitor, registry, chain = _wired()
    snap = snapshot(monitor, registry, chain)

    for name in ("healthy", "sick"):
        entry = snap["backends"][name]["fallback_health"]
        assert entry["backend"] == name
        assert entry["status"] == "ok"

    # The snapshot mirrors exactly what FallbackChain.health() reports.
    chain_health = chain.health()["chain"]
    assert len(chain_health) == 2
    assert {e["backend"] for e in chain_health} == set(snap["backends"])


def test_snapshot_unknown_backend_scores_optimistic():
    monitor, registry, chain = _wired()
    monitor.record("ghost", 10.0, ok=True)  # only 1 sample < min_samples
    snap = snapshot(monitor, registry, chain)

    ghost = snap["backends"]["ghost"]
    assert ghost["score"] == 1.0
    assert ghost["quarantined"] is False
    assert ghost["circuit"] is None      # no breaker was created
    assert ghost["fallback_health"] is None  # not in the chain


def test_snapshot_after_recovery_unquarantines():
    monitor, registry, chain = _wired()
    # Successes reset the consecutive failure count -> auto-recovery.
    for _ in range(10):
        monitor.record("sick", 15.0, ok=True)
    snap = snapshot(monitor, registry, chain)
    assert snap["backends"]["sick"]["quarantined"] is False
    # The circuit state is honest too: still open (nothing touched it).
    assert snap["backends"]["sick"]["circuit"] == "open"
