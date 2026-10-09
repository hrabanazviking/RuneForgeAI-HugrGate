"""Intelligence ladder — ordered backend cascade. Slices 31-32.

The ladder is the heart of "least expensive sufficient intelligence":
backends are ordered from cheapest to most capable, and each rung declares
a ``min_confidence`` gate. A rung whose result clears its gate wins; a rung
whose result falls short hands the decision upward. When every rung is
exhausted the gate abstains rather than guess.

Slice 32 adds two pruning rules applied *before* a rung runs:
- **Latency budgets**: a rung whose ``estimated_latency`` exceeds its own
  budget — or the time remaining under ``policy.maximum_latency_ms`` — is
  skipped, never started.
- **Privacy gate**: remote rungs require ``policy.remote_inference=True``
  (and pass the operator-level :class:`PrivacyGuard`).

Every rung outcome — attempted, skipped, failed, accepted — is recorded in
an auditable trail, both in the result's metadata and, optionally, in a
:class:`ProvenanceStore`.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.backend import Backend, BackendRegistry
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    SpecError,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard, provenance_mode_for
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_result, validate_state

__all__ = [
    "RUNG_ABSTAINED",
    "RUNG_ACCEPTED",
    "RUNG_BELOW_CONFIDENCE",
    "RUNG_CANCELLED",
    "RUNG_ERROR",
    "RUNG_SKIPPED_LATENCY",
    "RUNG_SKIPPED_PRIVACY",
    "RUNG_SKIPPED_UNKNOWN",
    "RUNG_SKIPPED_UNSUPPORTED",
    "RUNG_UNAVAILABLE",
    "LadderAuditEntry",
    "LadderRouter",
    "LadderRung",
]

#: Audit outcomes for a single rung.
RUNG_ACCEPTED = "accepted"
RUNG_BELOW_CONFIDENCE = "below_confidence"
RUNG_SKIPPED_UNKNOWN = "skipped_unknown_backend"
RUNG_SKIPPED_UNSUPPORTED = "skipped_unsupported"
RUNG_SKIPPED_PRIVACY = "skipped_privacy_blocked"
RUNG_SKIPPED_LATENCY = "skipped_latency_budget"
RUNG_UNAVAILABLE = "backend_unavailable"
RUNG_ERROR = "backend_error"
RUNG_ABSTAINED = "backend_abstained"
RUNG_CANCELLED = "cancelled"  # slice 065: hedge straggler dropped after win


@dataclass
class LadderRung:
    """One step of the intelligence ladder.

    Parameters
    ----------
    backend_name: name of a backend in the registry.
    min_confidence: the rung wins only if ``result.probability`` reaches
        this gate (the policy's ``minimum_probability`` is also honored —
        the stricter of the two applies).
    latency_budget_ms: optional per-rung ceiling; rungs whose estimated
        latency exceeds it are skipped without running.
    """
    backend_name: str
    min_confidence: float = 0.0
    latency_budget_ms: float | None = None

    def __post_init__(self):
        if not 0.0 <= self.min_confidence <= 1.0:
            raise SpecError(
                f"min_confidence must be in [0,1], got {self.min_confidence}")
        if self.latency_budget_ms is not None and self.latency_budget_ms < 0:
            raise SpecError("latency_budget_ms must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_name": self.backend_name,
            "min_confidence": self.min_confidence,
            "latency_budget_ms": self.latency_budget_ms,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> LadderRung:
        """Rebuild a rung from :meth:`to_dict` output.

        Unknown keys raise ``SpecError`` (ladder configuration is
        strict, like ``policy_from_dict``).
        """
        unknown = set(d) - {"backend_name", "min_confidence",
                            "latency_budget_ms"}
        if unknown:
            raise SpecError(
                f"unknown LadderRung key(s): {sorted(unknown)}")
        return cls(backend_name=d["backend_name"],
                   min_confidence=d.get("min_confidence", 0.0),
                   latency_budget_ms=d.get("latency_budget_ms"))


@dataclass
class LadderAuditEntry:
    """Auditable record of what happened at one rung."""
    rung_index: int
    backend_name: str
    outcome: str
    detail: str = ""
    probability: float | None = None
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rung_index": self.rung_index,
            "backend_name": self.backend_name,
            "outcome": self.outcome,
            "detail": self.detail,
            "probability": self.probability,
            "latency_ms": round(self.latency_ms, 3),
        }


class LadderRouter:
    """Route decisions through an ordered cascade of backends.

    Parameters
    ----------
    registry: backends available to the rungs.
    rungs: default ladder used for every spec type.
    ladders: optional per-spec-type ladders, ``{spec_type: [LadderRung]}``.
        Takes precedence over ``rungs`` when the spec type matches.
    provenance: optional :class:`ProvenanceStore`; every *attempted* rung
        appends a record so the climb is auditable after the fact.
    privacy_guard: operator-level guard; defaults to a permissive guard
        that defers to the decision policy.
    """

    def __init__(self, registry: BackendRegistry,
                 rungs: list[LadderRung] | None = None, *,
                 ladders: dict[str, list[LadderRung]] | None = None,
                 provenance: ProvenanceStore | None = None,
                 privacy_guard: PrivacyGuard | None = None):
        if not rungs and not ladders:
            raise SpecError("LadderRouter needs rungs or per-type ladders")
        self.registry = registry
        self.rungs = list(rungs or [])
        self.ladders = {k: list(v) for k, v in (ladders or {}).items()}
        self.provenance = provenance
        self.privacy_guard = privacy_guard or PrivacyGuard()
        self.last_audit: list[LadderAuditEntry] = []

    # -- ladder selection ------------------------------------------------

    def ladder_for(self, spec: DecisionSpec) -> list[LadderRung]:
        """The rung list governing this spec type."""
        return self.ladders.get(spec.type, self.rungs)

    # -- pre-run pruning (slice 051: extracted so v2 planners can reuse) --

    def skip_reason(self, backend: Backend, rung: LadderRung,
                    spec: DecisionSpec, policy: DecisionPolicy,
                    started: float) -> tuple | None:
        """Full pre-run check: (outcome, detail) or None if the rung may run."""
        if not backend.supports(spec):
            return (RUNG_SKIPPED_UNSUPPORTED,
                    f"backend does not support {spec.type} specs")
        if not self.privacy_guard.remote_allowed(backend, policy):
            return (RUNG_SKIPPED_PRIVACY,
                    "remote backend blocked (policy/guard)")
        skip = self._latency_skip(backend, rung, policy, started)
        if skip is not None:
            return (RUNG_SKIPPED_LATENCY, skip)
        return None

    # -- routing ---------------------------------------------------------

    def decide(self, state: Mapping[str, Any], spec: DecisionSpec,
               policy: DecisionPolicy | None = None,
               context: Mapping[str, Any] | None = None
               ) -> DecisionResult:
        """Climb the ladder until a rung clears its confidence gate.

        Raises
        ------
        Abstention
            With ``reason="ladder_exhausted"`` when no rung produced an
            acceptable result. The full audit trail rides in ``details``.
        """
        policy = policy or DecisionPolicy()
        validate_state(state)
        rungs = self.ladder_for(spec)
        if not rungs:
            raise SpecError(f"no ladder configured for spec type {spec.type!r}")

        audit: list[LadderAuditEntry] = []
        started = time.perf_counter()

        for i, rung in enumerate(rungs):
            backend = self.registry.get(rung.backend_name)
            if backend is None:
                audit.append(LadderAuditEntry(
                    i, rung.backend_name, RUNG_SKIPPED_UNKNOWN,
                    detail="backend not in registry"))
                continue
            skip = self.skip_reason(backend, rung, spec, policy, started)
            if skip is not None:
                audit.append(LadderAuditEntry(
                    i, backend.name, skip[0], detail=skip[1]))
                continue

            result = self._attempt(backend, state, spec, context, audit, i)
            if result is None:
                continue  # failure already audited; climb on

            gate = max(rung.min_confidence, policy.minimum_probability)
            if result.probability >= gate:
                entry = audit[-1]
                entry.outcome = RUNG_ACCEPTED
                entry.detail = (f"probability {result.probability:.3f} "
                                f"cleared gate {gate:.3f}")
                self._log_attempt(state, spec, result, policy, gate)
                result.metadata["ladder_trace"] = [e.to_dict() for e in audit]
                result.metadata["ladder_rung"] = i
                result.metadata["ladder_backend"] = backend.name
                self.last_audit = audit
                return result

            audit[-1].outcome = RUNG_BELOW_CONFIDENCE
            audit[-1].detail = (f"probability {result.probability:.3f} "
                                f"below gate {gate:.3f}; climbing")
            self._log_attempt(state, spec, result, policy, gate)

        self.last_audit = audit
        raise Abstention(
            "ladder exhausted: no rung cleared its confidence gate",
            reason="ladder_exhausted",
            ladder_trace=[e.to_dict() for e in audit])

    # -- internals -------------------------------------------------------

    def _latency_skip(self, backend: Backend, rung: LadderRung,
                      policy: DecisionPolicy, started: float
                      ) -> str | None:
        """Return a skip reason, or None if the rung may run."""
        estimate = backend.estimated_latency()
        if (rung.latency_budget_ms is not None
                and estimate > rung.latency_budget_ms):
            return (f"estimated {estimate:.1f}ms exceeds rung budget "
                    f"{rung.latency_budget_ms:.1f}ms")
        if policy.maximum_latency_ms is not None:
            elapsed = (time.perf_counter() - started) * 1000
            remaining = policy.maximum_latency_ms - elapsed
            if estimate > remaining:
                return (f"estimated {estimate:.1f}ms exceeds remaining "
                        f"budget {remaining:.1f}ms")
        return None

    def _attempt(self, backend: Backend, state: Mapping[str, Any],
                 spec: DecisionSpec, context: Mapping[str, Any] | None,
                 audit: list[LadderAuditEntry], rung_index: int
                 ) -> DecisionResult | None:
        """Run one rung. Returns the result, or None (audited) on failure."""
        t0 = time.perf_counter()
        try:
            result = backend.evaluate(state, spec, context)
        except Abstention as e:
            audit.append(LadderAuditEntry(
                rung_index, backend.name, RUNG_ABSTAINED,
                detail=f"backend abstained ({e.reason}); climbing",
                latency_ms=(time.perf_counter() - t0) * 1000))
            return None
        except BackendUnavailable as e:
            audit.append(LadderAuditEntry(
                rung_index, backend.name, RUNG_UNAVAILABLE,
                detail=str(e), latency_ms=(time.perf_counter() - t0) * 1000))
            return None
        except BackendError as e:
            audit.append(LadderAuditEntry(
                rung_index, backend.name, RUNG_ERROR,
                detail=str(e), latency_ms=(time.perf_counter() - t0) * 1000))
            return None
        except SpecError as e:
            # Slice 073: a backend that raises SpecError *during evaluate*
            # (e.g. constructing an incoherent DecisionResult) is a faulty
            # rung — audit it as RUNG_ERROR and keep climbing. SpecError
            # from validate_result() *after* evaluate still propagates
            # below (slice 012: never let invalid values climb).
            audit.append(LadderAuditEntry(
                rung_index, backend.name, RUNG_ERROR,
                detail=f"backend raised {type(e).__name__}: {e}",
                latency_ms=(time.perf_counter() - t0) * 1000))
            return None
        except Exception as e:  # noqa: BLE001 - never let one rung kill the climb
            audit.append(LadderAuditEntry(
                rung_index, backend.name, RUNG_ERROR,
                detail=f"unexpected {type(e).__name__}: {e}",
                latency_ms=(time.perf_counter() - t0) * 1000))
            return None

        if result is None:  # slice 073: hostile backend returned None
            audit.append(LadderAuditEntry(
                rung_index, backend.name, RUNG_ERROR,
                detail="backend returned None instead of a DecisionResult",
                latency_ms=(time.perf_counter() - t0) * 1000))
            return None

        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.backend = backend.name
        validate_result(result, spec)  # never let invalid values climb
        audit.append(LadderAuditEntry(
            rung_index, backend.name, RUNG_BELOW_CONFIDENCE,  # provisional
            probability=result.probability, latency_ms=result.latency_ms))
        return result

    def _log_attempt(self, state: Mapping[str, Any], spec: DecisionSpec,
                     result: DecisionResult, policy: DecisionPolicy,
                     gate: float) -> None:
        """Append an attempted rung to the provenance store, if any."""
        if self.provenance is None:
            return
        # Slice 226: redaction follows the class ladder's provenance
        # mode, not a hard-coded "strict" comparison.
        redact = provenance_mode_for(policy.privacy_class) in ("redacted", "none")
        record = DecisionRecord.from_decision(
            state, spec, result, policy_threshold=gate, redact_input=redact)
        if redact or self.privacy_guard.redact_provenance:
            record = self.privacy_guard.redact_record(record)
        self.provenance.append(record)
