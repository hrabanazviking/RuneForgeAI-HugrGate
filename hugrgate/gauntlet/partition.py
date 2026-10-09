"""Network partition gauntlet (slice 491).

``hugrgate/chaos/network.py`` simulates partitions; this module is
the *gauntlet* that proves the decision path stays fail-closed
under them. The invariant under test, end to end through the live
``HugrGate.decide`` path:

- while a remote backend's host is partitioned, decisions fail
  *fast* with :class:`BackendUnavailable` — never by silently
  weakening the policy (no lowered ``minimum_probability``, no
  flipped ``remote_inference``, no mutated policy object);
- partial failure (one of two remotes down) does not take down the
  reachable one;
- after healing, decisions succeed again with the policy
  byte-identical to before the partition.

:func:`run_partition_scenario` drives the three phases (up →
partitioned → healed) and returns a :class:`PartitionReport`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import BackendUnavailable

__all__ = [
    "PartitionReport",
    "assert_policy_intact",
    "run_partition_scenario",
    "snapshot_policy",
]


def snapshot_policy(policy: Any) -> dict[str, Any]:
    """Capture every public policy field for later comparison."""
    snap: dict[str, Any] = {}
    for name in dir(policy):
        if name.startswith("_"):
            continue
        try:
            value = getattr(policy, name)
        except Exception:  # noqa: BLE001 - unreadable: skip
            continue
        if callable(value):
            continue
        try:
            snap[name] = repr(value)
        except Exception:  # noqa: BLE001 - unrepresentable: skip
            continue
    return snap


def assert_policy_intact(policy: Any, snapshot: dict[str, Any]) -> None:
    """Raise if the policy drifted since ``snapshot`` was taken.

    Network events must never silently weaken policy — this is the
    assertion that proves it.
    """
    current = snapshot_policy(policy)
    drifted = {
        name: (snapshot.get(name), current.get(name))
        for name in set(snapshot) | set(current)
        if snapshot.get(name) != current.get(name)
    }
    if drifted:
        raise AssertionError(
            f"policy weakened/mutated during partition: {drifted}")


@dataclass
class PartitionReport:
    """Outcome of :func:`run_partition_scenario`."""

    phases: list[dict[str, Any]] = field(default_factory=list)
    policy_drift: dict[str, Any] = field(default_factory=dict)

    @property
    def fail_closed_ok(self) -> bool:
        """Every partitioned phase failed fast with no policy drift."""
        if not self.phases:
            return False
        partitioned = [p for p in self.phases if p["phase"] == "partitioned"]
        return (
            bool(partitioned)
            and all(p["outcome"] == "unavailable" for p in partitioned)
            and not self.policy_drift
        )


def run_partition_scenario(
    gate: Any,
    decide: Any,
    simulator: Any,
    host: str,
    *,
    policy: Any = None,
) -> PartitionReport:
    """Drive up → partitioned → healed through ``decide(state, spec)``.

    ``decide`` is a zero-arg callable performing one decision
    (closing over state/spec/policy). ``simulator`` is a
    ``NetworkSimulator``; ``host`` is partitioned in phase 2 and
    healed in phase 3. Returns the report; raises on policy drift.
    """
    report = PartitionReport()
    before = snapshot_policy(policy) if policy is not None else {}

    def _phase(name: str) -> None:
        try:
            decide()
            outcome: str = "ok"
            detail = ""
        except BackendUnavailable as exc:
            outcome = "unavailable"
            detail = str(exc)[:120]
        except Exception as exc:  # noqa: BLE001 - recorded, not hidden
            outcome = f"error:{type(exc).__name__}"
            detail = str(exc)[:120]
        report.phases.append({"phase": name, "outcome": outcome,
                              "detail": detail})
        if policy is not None:
            try:
                assert_policy_intact(policy, before)
            except AssertionError as exc:
                report.policy_drift = {"phase": name,
                                       "drift": str(exc)[:200]}
                raise

    _phase("up")
    simulator.set_down(host)
    try:
        _phase("partitioned")
    finally:
        simulator.set_up(host)
    _phase("healed")
    return report
