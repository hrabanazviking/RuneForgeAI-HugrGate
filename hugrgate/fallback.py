"""Fallback engine — ordered failover across backends. Slice 14.

``FallbackChain`` is itself a :class:`~hugrgate.backend.Backend`, so it
drops straight into :class:`~hugrgate.core.HugrGate` and the provenance
trail. Backends are tried in order; on :class:`BackendError` (which
includes :class:`TimeoutError` and :class:`BackendUnavailable`) the next
backend is tried. When every backend has failed, the policy's
``fallback_behavior`` decides:

- ``"abstain"``   -> raise :class:`Abstention` (reason
  ``all_backends_failed``)
- ``"safe_default"`` -> return a ``DecisionResult`` for the configured
  safe value (must lie inside the spec's value space)
- ``"escalate"``  -> raise :class:`Abstention` with reason
  ``escalation_required`` (a human must take the decision)

``Abstention`` raised by an inner backend is *not* swallowed: abstaining
is a decision, not a failure, and it propagates to the caller.

Every attempt is recorded in ``result.metadata["fallback_trace"]`` and
``result.fallback_used`` is set when any failover happened, so the
provenance record carries the full chain trace.

A :class:`~hugrgate.circuit.CircuitRegistry` may be supplied; backends
whose circuit is open are skipped (recorded in the trace) and outcomes
are reported back to their breakers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hugrgate.backend import Backend
from hugrgate.circuit import CircuitRegistry
from hugrgate.errors import Abstention, BackendError, PolicyError
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

logger = get_logger(__name__)

__all__ = [
    "FallbackChain",
]


class FallbackChain(Backend):
    """Try backends in order; fail over on backend errors."""

    name = "fallback-chain"

    def __init__(self, backends: list[Backend],
                 policy: DecisionPolicy | None = None,
                 safe_default: Any = None,
                 circuits: CircuitRegistry | None = None,
                 name: str = "fallback-chain"):
        if not backends:
            raise PolicyError("FallbackChain needs at least one backend")
        self.name = name
        self.backends = list(backends)
        self.policy = policy or DecisionPolicy()
        self.safe_default = safe_default
        self.circuits = circuits
        self._last_outcome: dict[str, str] = {}
        if (self.policy.fallback_behavior == "safe_default"
                and safe_default is None):
            raise PolicyError(
                "fallback_behavior='safe_default' requires a safe_default value")

    def capabilities(self) -> dict[str, Any]:
        return {
            "spec_types": sorted({t for b in self.backends
                                  for t in b.capabilities().get("spec_types", [])}),
            "deterministic": all(b.capabilities().get("deterministic", False)
                                 for b in self.backends),
            "chain": [b.name for b in self.backends],
            "fallback_behavior": self.policy.fallback_behavior,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return any(b.supports(spec) for b in self.backends)

    def _breaker(self, backend: Backend):
        if self.circuits is None:
            return None
        return self.circuits.get(backend.name)

    def _record_outcomes(self, trace: list[dict[str, Any]]) -> None:
        for entry in trace:
            self._last_outcome[entry["backend"]] = entry["outcome"]

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        trace: list[dict[str, Any]] = []
        for index, backend in enumerate(self.backends):
            breaker = self._breaker(backend)
            if breaker is not None and not breaker.allow():
                trace.append({"backend": backend.name, "outcome": "skipped",
                              "reason": "circuit_open",
                              "circuit_state": breaker.state})
                continue
            try:
                result = backend.evaluate(state, spec, context)
            except Abstention:
                # A decision to abstain is not a failure; let it through.
                raise
            except BackendError as e:
                trace.append({"backend": backend.name, "outcome": "failed",
                              "error": str(e), "code": e.code})
                logger.warning("fallback: backend %r failed (%s); trying next",
                               backend.name, e.code)
                if breaker is not None:
                    breaker.record_failure()
                continue
            if breaker is not None:
                breaker.record_success()
            trace.append({"backend": backend.name, "outcome": "ok"})
            self._record_outcomes(trace)
            result.fallback_used = index > 0 or any(
                t["outcome"] != "ok" for t in trace)
            result.metadata.setdefault("fallback_trace", trace)
            result.metadata["decided_by"] = backend.name
            return result
        return self._exhausted(state, spec, trace)

    def explain(self) -> str:
        """Human-readable summary of the chain.

        Reports the backend order, the circuit state of each backend
        (``n/a`` when no :class:`~hugrgate.circuit.CircuitRegistry` was
        supplied), and the last recorded outcome of each backend from
        the most recent :meth:`evaluate` call (``never-attempted`` when
        no evaluation has run yet). Pure read-only report.
        """
        lines = [f"{self.name} (order: {' -> '.join(b.name for b in self.backends)})"]
        for backend in self.backends:
            if self.circuits is None:
                circuit = "n/a"
            else:
                # _breaker may materialize a default closed breaker, the
                # same behaviour evaluate() has when consulting the registry.
                circuit = self._breaker(backend).state
            last = self._last_outcome.get(backend.name, "never-attempted")
            lines.append(f"  {backend.name}: circuit={circuit} last={last}")
        return "\n".join(lines)

    def _exhausted(self, state: Mapping[str, Any], spec: DecisionSpec,
                   trace: list[dict[str, Any]]) -> DecisionResult:
        self._record_outcomes(trace)
        behavior = self.policy.fallback_behavior
        if behavior == "abstain":
            raise Abstention(
                "all backends in the fallback chain failed",
                reason="all_backends_failed",
                trace=[t["backend"] for t in trace],
                backend=self.name)
        if behavior == "escalate":
            raise Abstention(
                "all backends failed; human escalation required",
                reason="escalation_required",
                trace=[t["backend"] for t in trace],
                backend=self.name)
        # behavior == "safe_default" (validated at construction)
        value = self.safe_default
        space = spec.value_space()
        if spec.type == "numeric":
            # _validate_numeric guarantees both bounds are set.
            assert spec.minimum is not None and spec.maximum is not None
            ok = isinstance(value, (int, float)) and spec.minimum <= value <= spec.maximum
        elif spec.type == "multilabel":
            ok = isinstance(value, list) and all(v in space for v in value)
        else:
            ok = value in space
        if not ok:
            raise BackendError(
                f"safe_default {value!r} is outside the spec value space")
        distribution = {value: 1.0} if spec.type != "multilabel" else {}
        result = DecisionResult(
            value=value,
            probability=1.0,
            distribution=distribution,
            uncertainty=0.0,
            backend=self.name,
            model="fallback-safe-default",
            fallback_used=True,
            metadata={
                "fallback_trace": trace,
                "safe_default_used": True,
                "decided_by": self.name,
            },
        )
        return result

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "backend": self.name,
                "chain": [b.health() for b in self.backends]}
