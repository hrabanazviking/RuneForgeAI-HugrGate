"""HugrGate core runtime — decide(). Slice 8."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Union

from hugrgate.backend import Backend, BackendRegistry
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    SpecError,
)
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import provenance_mode_for
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_result, validate_state

logger = get_logger(__name__)

if TYPE_CHECKING:
    from hugrgate.contracts.schema import DecisionContract

__all__ = [
    "HugrGate",
]

#: What decide() accepts as a decision specification.
SpecLike = Union[DecisionSpec, "DecisionContract"]


def _ensure_spec(spec: SpecLike) -> tuple[DecisionSpec, str | None]:
    """Accept a v1 DecisionSpec or a v2 DecisionContract.

    Returns the v1 spec the runtime understands plus the originating
    v2 ``contract_id`` (None for a native v1 spec). v2 contracts with a
    v1 equivalent ride the migration engine down to a DecisionSpec
    (slice 047); anything else raises a clear error instead of failing
    deep inside a backend.
    """
    if isinstance(spec, DecisionSpec):
        return spec, None
    # Imported lazily: the contracts package is large and core must stay
    # importable without it.
    from hugrgate.contracts.migration import contract_to_spec
    from hugrgate.contracts.schema import DecisionContract
    if isinstance(spec, DecisionContract):
        return contract_to_spec(spec), spec.contract_id
    raise SpecError(
        f"decide() needs a DecisionSpec or DecisionContract, got "
        f"{type(spec).__name__}")


class HugrGate:
    """The decision runtime.

    Usage:
        gate = HugrGate()
        gate.register(MyBackend())
        result = gate.decide(state, spec, policy)
    """

    def __init__(self, registry: BackendRegistry | None = None):
        self.registry = registry or BackendRegistry()
        self.provenance = ProvenanceStore()

    def register(self, backend: Backend, *, replace: bool = False) -> None:
        self.registry.register(backend, replace=replace)

    def close(self) -> None:
        """Release backend resources, best-effort (slice 019).

        Calls :meth:`Backend.close` on every registered backend.
        A backend whose ``close()`` raises is logged and skipped —
        one leaking backend must not block the rest.
        """
        for name in self.registry.list():
            backend = self.registry.get(name)
            if backend is None:
                continue
            try:
                backend.close()
            except Exception as e:  # noqa: BLE001 - best effort
                logger.warning("backend %r close() failed: %s", name, e)

    def __enter__(self) -> HugrGate:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
        return None

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

    def decide(self, state: Mapping[str, Any], spec: SpecLike,
               policy: DecisionPolicy | None = None,
               context: Mapping[str, Any] | None = None,
               backend_name: str | None = None) -> DecisionResult:
        """Make a bounded machine judgment.

        Never returns a value outside the spec's decision space.

        ``spec`` may be a v1 :class:`DecisionSpec` or a v2
        :class:`~hugrgate.contracts.schema.DecisionContract`; v2
        contracts with a v1 equivalent are migrated at the boundary
        (their ``contract_id`` rides in ``result.metadata``).
        """
        policy = policy or DecisionPolicy()
        validate_state(state)
        start = time.perf_counter()

        spec, contract_id = _ensure_spec(spec)

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
            raise BackendError(f"backend {backend.name} failed: {e}") from e

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
        if contract_id is not None:
            result.metadata["contract_id"] = contract_id

        # Provenance — slice 226: redaction follows the class ladder's
        # provenance mode, not a hard-coded "strict" comparison.
        redact = provenance_mode_for(policy.privacy_class) in ("redacted", "none")
        self.provenance.append(DecisionRecord.from_decision(
            state, spec, result,
            policy_threshold=policy.minimum_probability,
            redact_input=redact))

        return result

    def decide_batch(self, states: list, spec: SpecLike,
                     policy: DecisionPolicy | None = None) -> list:
        return [self.decide(s, spec, policy) for s in states]

    async def adecide(self, state: Mapping[str, Any],
                      spec: DecisionSpec,
                      policy: DecisionPolicy | None = None,
                      context: Mapping[str, Any] | None = None,
                      backend_name: str | None = None) -> DecisionResult:
        """Async variant of :meth:`decide` (slice 018).

        Backend inference is synchronous and may block; this runs it in
        a worker thread via :func:`asyncio.to_thread` so the event loop
        stays responsive. Same contract, same errors as ``decide``.
        """
        return await asyncio.to_thread(
            self.decide, state, spec, policy, context, backend_name)
