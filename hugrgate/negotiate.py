"""Backend capability negotiation. Slice 36.

:func:`select_backend` turns a registry into an ordered candidate list for
one decision: filter by capability, privacy, latency, cost and health, then
rank the survivors by historical quality (accuracy + calibration) with
latency and name as deterministic tie-breakers.

It returns candidates — it never raises — so routers (ladder, fallback)
can decide what "no candidate" means for their policy.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Mapping, Optional

from hugrgate.backend import Backend, BackendRegistry
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.spec import DecisionSpec

__all__ = [
    "ACCURACY_WEIGHT",
    "CALIBRATION_WEIGHT",
    "select_backend",
]

#: Weighting of historical quality: accuracy vs. calibration.
ACCURACY_WEIGHT = 0.7
CALIBRATION_WEIGHT = 0.3


def _quality(stats: Optional[Mapping[str, float]]) -> float:
    """Historical quality in [0,1]; neutral 0.5 when nothing is known."""
    if not stats:
        return 0.5
    accuracy = float(stats.get("accuracy", 0.5))
    cal_error = float(stats.get("calibration_error", 0.5))
    accuracy = max(0.0, min(1.0, accuracy))
    cal_error = max(0.0, min(1.0, cal_error))
    return ACCURACY_WEIGHT * accuracy + CALIBRATION_WEIGHT * (1.0 - cal_error)


def select_backend(
    spec: DecisionSpec,
    policy: DecisionPolicy,
    registry: BackendRegistry,
    *,
    privacy_guard: Optional[PrivacyGuard] = None,
    health: Optional[Callable[[str], float]] = None,
    min_health: float = 0.0,
    stats: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> List[Backend]:
    """Return backends ordered best-first for ``(spec, policy)``.

    Filters (in order):
    1. ``supports(spec)`` — the backend must handle the spec type.
    2. Privacy — the guard (default: defer to policy) must allow the
       backend; remote backends need ``policy.remote_inference``.
    3. Policy allow-list — ``policy.backend_allowed(name, is_remote)``.
    4. Latency — ``estimated_latency()`` must fit
       ``policy.maximum_latency_ms`` when set.
    5. Cost — ``estimated_cost()`` must fit ``policy.max_cost`` when set.
    6. Health — when a ``health(name) -> 0..1`` scorer is given, backends
       below ``min_health`` are excluded.

    Ranking: historical quality (accuracy + calibration) first, then
    lower estimated latency, then name — fully deterministic.
    """
    guard = privacy_guard or PrivacyGuard()
    candidates: List[Backend] = []
    for backend in registry.supporting(spec):
        if not guard.remote_allowed(backend, policy):
            continue
        if not policy.backend_allowed(backend.name, backend.is_remote):
            continue
        if (policy.maximum_latency_ms is not None
                and backend.estimated_latency() > policy.maximum_latency_ms):
            continue
        if (policy.max_cost is not None
                and backend.estimated_cost() > policy.max_cost):
            continue
        if health is not None:
            try:
                score = float(health(backend.name))
            except Exception:
                score = 0.0
            if score < min_health:
                continue
        candidates.append(backend)

    def rank_key(b: Backend):
        return (-_quality(stats.get(b.name) if stats else None),
                b.estimated_latency(),
                b.name)

    return sorted(candidates, key=rank_key)
