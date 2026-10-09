"""Distributed ladder routing. Slice 212.

The local ladder (``hugrgate.ladder``) walks backends cheapest-first;
the distributed router walks *nodes* best-first. A routing candidate is
either "decide locally" or "ask peer P". Candidates are filtered, then
scored, then walked in order — the same shape as ladder rungs, so the
two compose: local ladder first, cluster walk after.

Filtering (a candidate that fails any filter is never tried):

- capability: the peer must advertise the spec type (or have no
  advertisement, in which case the operator configured it explicitly);
- privacy: remote candidates require ``policy.remote_inference`` and a
  non-strict ``privacy_class`` (slice 211);
- serve: the peer must serve remote decisions (``PeerRecord`` has no
  serve flag — the RPC reports ``backend_unavailable``, which the walk
  treats as an ordinary candidate failure).

Scoring: each peer carries :class:`PeerScores` (health/latency/cost in
[0,1], maintained by slices 213-215; default 1.0 = perfect). The total
is the weighted mean; the local candidate scores a flat 1.0 and wins
ties (no network hop).

Walking (:func:`DistributedRouter.decide`): try candidates in order;
``BackendError`` (incl. ``BackendUnavailable``, ``TimeoutError``)
moves to the next candidate; ``Abstention`` and ``PrivacyViolation``
propagate — they are decisions, not transport failures.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.privacy_boundary import PrivacyBoundary
from hugrgate.errors import (
    BackendError,
    BackendUnavailable,
    PrivacyViolation,
    SpecError,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

if TYPE_CHECKING:
    from hugrgate.cluster.node import ClusterNode

__all__ = [
    "DistributedRouter",
    "PeerScores",
    "RouteCandidate",
]


@dataclass
class PeerScores:
    """Per-peer scores in [0, 1]; 1.0 is perfect.

    Maintained by the health (213), latency (214), and cost (215)
    monitors; the router only reads them.
    """

    health: float = 1.0
    latency: float = 1.0   # 1.0 = fast
    cost: float = 1.0      # 1.0 = cheap

    def __post_init__(self) -> None:
        for name in ("health", "latency", "cost"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
                raise SpecError(
                    f"peer score {name} must be in [0, 1], got {value!r}")


@dataclass
class RouteCandidate:
    """One routable option: local gate or a peer."""

    kind: str  # "local" | "remote"
    peer: PeerRecord | None
    scores: PeerScores = field(default_factory=PeerScores)
    total: float = 1.0
    reasons: list[str] = field(default_factory=list)

    @property
    def node_id(self) -> str:
        return self.peer.node_id if self.peer else "local"


class DistributedRouter:
    """Filter → score → walk cluster routing candidates."""

    def __init__(self, node: ClusterNode,
                 weights: dict[str, float] | None = None) -> None:
        self._node = node
        self._weights = dict(weights or {"health": 0.5, "latency": 0.3,
                                        "cost": 0.2})
        if set(self._weights) != {"health", "latency", "cost"}:
            raise SpecError(
                "weights must name exactly health/latency/cost")
        if any(w < 0 for w in self._weights.values()):
            raise SpecError("weights must be non-negative")
        if sum(self._weights.values()) <= 0:
            raise SpecError("at least one weight must be positive")
        self._scores: dict[str, PeerScores] = {}
        self._boundary = PrivacyBoundary()

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def set_scores(self, node_id: str, scores: PeerScores) -> None:
        """Record scores for a peer (slices 213-215 call this)."""
        if not isinstance(scores, PeerScores):
            raise SpecError("scores must be a PeerScores")
        self._scores[node_id] = scores

    def scores_for(self, node_id: str) -> PeerScores:
        return self._scores.get(node_id, PeerScores())

    def _total(self, scores: PeerScores) -> float:
        total_w = sum(self._weights.values())
        return sum(self._weights[k] * getattr(scores, k)
                   for k in self._weights) / total_w

    def _peer_allowed(self, peer: PeerRecord, spec: DecisionSpec,
                      policy: DecisionPolicy) -> tuple[bool, str]:
        caps = peer.capabilities
        if caps is not None and not caps.matches(spec):
            return False, f"no backend for spec type {spec.type}"
        try:
            self._boundary.check_outbound_allowed(policy)
        except PrivacyViolation as e:
            return False, e.message
        cost = self._node.costs.cost_of(peer.node_id)
        if policy.max_cost is not None and cost > policy.max_cost:
            return False, (f"cost {cost} exceeds max_cost "
                           f"{policy.max_cost}")
        return True, "ok"

    def route(self, spec: DecisionSpec,
              policy: DecisionPolicy | None = None) -> list[RouteCandidate]:
        """Ordered candidates, best first. Local wins ties."""
        policy = policy or DecisionPolicy()
        candidates: list[RouteCandidate] = []
        # Local candidate: let the gate pick its own backend.
        if self._node.gate.registry.supporting(spec):
            candidates.append(RouteCandidate(
                kind="local", peer=None,
                scores=PeerScores(1.0, 1.0, 1.0), total=1.0,
                reasons=["local gate supports the spec"]))
        for peer in self._node.peers():
            allowed, _reason = self._peer_allowed(peer, spec, policy)
            if not allowed:
                continue
            scores = self.scores_for(peer.node_id)
            total = self._total(scores)
            candidates.append(RouteCandidate(
                kind="remote", peer=peer, scores=scores, total=total,
                reasons=[f"score={total:.3f}"]))
        candidates.sort(key=lambda c: (-c.total,
                                       0 if c.kind == "local" else 1))
        return candidates

    def best(self, spec: DecisionSpec,
             policy: DecisionPolicy | None = None
             ) -> RouteCandidate | None:
        candidates = self.route(spec, policy)
        return candidates[0] if candidates else None

    def decide(self, spec: DecisionSpec, state: Mapping[str, Any],
               policy: DecisionPolicy | None = None,
               context: Mapping[str, Any] | None = None,
               backend_name: str | None = None) -> DecisionResult:
        """Walk candidates until one decides.

        ``BackendError`` moves to the next candidate; ``Abstention``
        and ``PrivacyViolation`` propagate. The winning candidate is
        recorded in ``result.metadata["route"]``.
        """
        policy = policy or DecisionPolicy()
        candidates = self.route(spec, policy)
        if not candidates:
            raise BackendUnavailable(
                "no route: no local backend and no peer serves this "
                "spec under the given policy")
        failures: list[str] = []
        for candidate in candidates:
            try:
                if candidate.kind == "local":
                    result = self._node.gate.decide(
                        state, spec, policy, context=context,
                        backend_name=backend_name)
                else:
                    assert candidate.peer is not None
                    result = self._node.decide_remote(
                        candidate.peer, spec, state, policy=policy,
                        context=context, backend_name=backend_name)
            except BackendError as e:
                failures.append(f"{candidate.node_id[:12]}…: {e.code}")
                continue
            result.metadata["route"] = {
                "kind": candidate.kind,
                "node_id": candidate.node_id,
                "score": round(candidate.total, 4),
            }
            return result
        raise BackendUnavailable(
            f"all {len(candidates)} route candidates failed: "
            f"{'; '.join(failures)}")

    def audit(self, spec: DecisionSpec,
              policy: DecisionPolicy | None = None) -> list[dict[str, Any]]:
        """Explain a routing decision (for logs and debugging)."""
        return [{
            "kind": c.kind,
            "node_id": c.node_id,
            "total": round(c.total, 4),
            "scores": {"health": c.scores.health,
                       "latency": c.scores.latency,
                       "cost": c.scores.cost},
            "reasons": list(c.reasons),
        } for c in self.route(spec, policy)]
