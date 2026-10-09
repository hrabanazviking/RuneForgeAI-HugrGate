"""HugrGate core runtime — decide(). Slice 8."""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional

from hugrgate.backend import Backend, BackendRegistry
from hugrgate.errors import BackendUnavailable, BackendError, Abstention
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_result, validate_state

logger = get_logger(__name__)

__all__ = [
    "HugrGate",
]


class HugrGate:
    """The decision runtime.

    Usage:
        gate = HugrGate()
        gate.register(MyBackend())
        result = gate.decide(state, spec, policy)
    """

    def __init__(self, registry: Optional[BackendRegistry] = None):
        self.registry = registry or BackendRegistry()
        self.provenance = ProvenanceStore()

    def register(self, backend: Backend) -> None:
        self.registry.register(backend)

    def _select_backend(self, spec: DecisionSpec,
                        policy: DecisionPolicy) -> Backend:
        candidates = self.registry.supporting(spec)
        # Privacy gate first
        candidates = [b for b in candidates
                      if policy.backend_allowed(b.name, b.is_remote)]
        if not candidates:
            raise BackendUnavailable(
                "no backend supports this spec under the given policy")
        # Preferred backends first
        if policy.preferred_backends:
            preferred = [b for b in candidates
                         if b.name in policy.preferred_backends]
            if preferred:
                return preferred[0]
        return candidates[0]

    def decide(self, state: Mapping[str, Any], spec: DecisionSpec,
               policy: Optional[DecisionPolicy] = None,
               context: Optional[Mapping[str, Any]] = None,
               backend_name: Optional[str] = None) -> DecisionResult:
        """Make a bounded machine judgment.

        Never returns a value outside the spec's decision space.
        """
        policy = policy or DecisionPolicy()
        validate_state(state)
        start = time.perf_counter()

        if backend_name:
            backend = self.registry.get(backend_name)
            if backend is None:
                raise BackendUnavailable(f"unknown backend: {backend_name}")
            if not policy.backend_allowed(backend.name, backend.is_remote):
                raise BackendUnavailable(
                    f"backend {backend_name} blocked by policy")
        else:
            backend = self._select_backend(spec, policy)

        try:
            result = backend.evaluate(state, spec, context)
        except Abstention:
            logger.debug("backend %r abstained (spec=%s)", backend.name,
                         spec.type)
            raise
        except BackendError:
            logger.warning("backend %r failed; no failover in core path",
                           backend.name)
            raise
        except Exception as e:
            logger.warning("backend %r raised unexpected %s",
                           backend.name, type(e).__name__)
            raise BackendError(f"backend {backend.name} failed: {e}")

        result.latency_ms = (time.perf_counter() - start) * 1000
        result.backend = backend.name

        # The application never receives a value outside the spec space.
        validate_result(result, spec)

        # Policy gate
        verdict = policy.evaluate(result)
        if verdict == "abstain":
            raise Abstention(
                f"probability {result.probability:.3f} below threshold "
                f"{policy.minimum_probability:.3f}")
        result.accepted = True
        result.metadata["policy_verdict"] = verdict

        # Provenance
        redact = policy.privacy_class == "strict"
        self.provenance.append(DecisionRecord.from_decision(
            state, spec, result,
            policy_threshold=policy.minimum_probability,
            redact_input=redact))

        return result

    def decide_batch(self, states: list, spec: DecisionSpec,
                     policy: Optional[DecisionPolicy] = None) -> list:
        return [self.decide(s, spec, policy) for s in states]
