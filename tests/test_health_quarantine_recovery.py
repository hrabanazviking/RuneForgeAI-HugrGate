"""Slice 19 — quarantine-auto-recovery-regression: regression test proving a
quarantined backend auto-recovers after consecutive successes.

health.py's module docstring documents that quarantine is computed live
from the stats: a success resets the consecutive failure count and the
score climbs back above the quarantine threshold, so the backend
auto-recovers without any explicit unquarantine call.
"""

from hugrgate.health import HealthMonitor


def _sick_monitor() -> HealthMonitor:
    return HealthMonitor(quarantine_threshold=0.3,
                         max_consecutive_failures=5,
                         min_samples=3)


def test_quarantine_triggers_on_consecutive_failures():
    monitor = _sick_monitor()
    # Not quarantined before enough samples to judge the score.
    for _ in range(2):
        monitor.record("sick", 5000.0, ok=False)
        assert monitor.is_quarantined("sick") is False

    # A failing backend's error rate drives its score below the threshold,
    # so quarantine also triggers via score (not only the consecutive-
    # failure rule, which fires at max_consecutive_failures).
    for _ in range(3):
        monitor.record("sick", 5000.0, ok=False)
    assert monitor.is_quarantined("sick") is True
    assert "sick" in monitor.quarantined()
    assert monitor.stats("sick")["consecutive_failures"] == 5


def test_quarantined_backend_recovers_after_consecutive_successes():
    monitor = _sick_monitor()
    for _ in range(6):
        monitor.record("sick", 5000.0, ok=False)
    assert monitor.is_quarantined("sick") is True

    # Successes dilute the error rate and push the score back above the
    # quarantine threshold; the first success resets consecutive failures.
    monitor.record("sick", 20.0, ok=True)
    assert monitor.stats("sick")["consecutive_failures"] == 0

    for _ in range(10):
        monitor.record("sick", 20.0, ok=True)

    assert monitor.is_quarantined("sick") is False
    assert "sick" not in monitor.quarantined()
    assert monitor.score("sick") >= 0.3


def test_unknown_backend_is_never_quarantined():
    monitor = _sick_monitor()
    assert monitor.is_quarantined("ghost") is False
    assert monitor.quarantined() == []
