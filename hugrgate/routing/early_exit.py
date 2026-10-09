"""Early-exit routing. Slice 066.

A ladder that always climbs to the top wastes work two ways: it keeps
going after an overwhelmingly confident answer, and it keeps going when
each new rung barely moves the needle. :class:`EarlyExitExecutor`
(wrapping the serial walk's building blocks, not its loop) adds two
exit rules:

1. **Fast path** — a result with ``probability >= fast_path_bar`` is
   accepted immediately, even if the rung's own ``min_confidence`` gate
   is stricter. Overwhelming confidence short-circuits stricter gates.
   The bar is ``min(options.fast_path_probability,
   qos_profile(options.qos).fast_path_probability)``.
2. **Diminishing returns** — after at least 3 attempts, if the best
   probability has not improved by ``early_exit_delta`` over the last 2
   attempts, the climb stops: the best result so far is returned when it
   clears ``policy.minimum_probability``, otherwise the router abstains
   early with ``reason="early_exit_no_improvement"`` instead of burning
   more rungs. The delta defaults to the QoS profile's value; setting
   ``options.early_exit_delta = 0`` disables the rule (no positive
   improvement threshold can be met... i.e. the rule only fires on
   *strictly less than delta* improvement, and ``0`` means "never").

Both exits are recorded in the audit detail and in
``result.metadata["early_exit"]``.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from hugrgate.errors import Abstention
from hugrgate.ladder import (
    RUNG_ACCEPTED,
    RUNG_BELOW_CONFIDENCE,
    RUNG_SKIPPED_UNKNOWN,
    LadderAuditEntry,
)
from hugrgate.routing.architecture import (
    LadderRouterV2,
    RouterContext,
    RoutingDecision,
    RoutingPlan,
    RungExecutor,
)
from hugrgate.routing.qos import qos_profile

__all__ = [
    "EarlyExitExecutor",
]

_MIN_ATTEMPTS = 3
_WINDOW = 2


class EarlyExitExecutor(RungExecutor):
    """Serial climb with fast-path and diminishing-returns exits."""

    def execute(self, router: LadderRouterV2, plan: RoutingPlan,
                state: Mapping[str, Any], ctx: RouterContext
                ) -> RoutingDecision:
        profile = qos_profile(ctx.options.qos)
        fast_bar = min(ctx.options.fast_path_probability,
                       profile.fast_path_probability)
        delta = (ctx.options.early_exit_delta
                 if ctx.options.early_exit_delta is not None
                 else profile.early_exit_delta)
        policy = ctx.policy
        started = time.perf_counter()

        audit: list[LadderAuditEntry] = []
        best: dict[str, Any] | None = None  # {prob, result, index, gate}
        improvements: list[float] = []

        for i, node in enumerate(plan.nodes):
            backend = router.registry.get(node.backend_name)
            if backend is None:
                audit.append(LadderAuditEntry(
                    i, node.backend_name, RUNG_SKIPPED_UNKNOWN,
                    detail="backend not in registry"))
                continue
            skip = router.skip_reason(backend, node.to_ladder_rung(),
                                      ctx.spec, policy, started)
            if skip is not None:
                audit.append(LadderAuditEntry(
                    i, backend.name, skip[0], detail=skip[1]))
                continue

            result = router._attempt(backend, state, ctx.spec, None,
                                     audit, i)
            if result is None:
                continue
            router.note_availability(backend.name, True)
            router.note_cost(backend, result)
            router.note_energy(backend, result)
            gate = max(node.min_confidence, policy.minimum_probability)

            prev_best = best["prob"] if best else 0.0
            if best is None or result.probability > best["prob"]:
                improvements.append(result.probability - prev_best)
                best = {"prob": result.probability, "result": result,
                        "index": i, "gate": gate, "backend": backend.name}
            else:
                improvements.append(0.0)

            # Rule 1: fast path.
            if result.probability >= fast_bar:
                return self._finish(router, plan, audit, state, ctx.spec,
                                    policy, result, i, backend.name, gate,
                                    early_exit="fast_path",
                                    detail=(f"probability "
                                            f"{result.probability:.3f} >= "
                                            f"fast-path bar {fast_bar:.3f}"))

            # Rule 1b: normal gate clear.
            if result.probability >= gate:
                return self._finish(router, plan, audit, state, ctx.spec,
                                    policy, result, i, backend.name, gate,
                                    early_exit=None,
                                    detail=(f"probability "
                                            f"{result.probability:.3f} "
                                            f"cleared gate {gate:.3f}"))

            audit[-1].outcome = RUNG_BELOW_CONFIDENCE
            audit[-1].detail = (f"probability {result.probability:.3f} "
                                f"below gate {gate:.3f}; climbing")
            router._log_attempt(state, ctx.spec, result, policy, gate)

            # Rule 2: diminishing returns.
            if (delta > 0 and len(improvements) >= _MIN_ATTEMPTS
                    and all(imp < delta for imp in improvements[-_WINDOW:])):
                if (best is not None
                        and best["prob"] >= policy.minimum_probability):
                    b = best
                    return self._finish(
                        router, plan, audit, state, ctx.spec, policy,
                        b["result"], b["index"], b["backend"], b["gate"],
                        early_exit="diminishing_returns",
                        already_logged=True,
                        detail=(f"best probability {b['prob']:.3f} "
                                f"stagnant (< {delta} gain over "
                                f"{_WINDOW} rungs); accepting best"))
                router.last_audit = audit
                router.note_latencies(audit)
                raise Abstention(
                    "early exit: no rung improving; best below policy "
                    "minimum",
                    reason="early_exit_no_improvement",
                    ladder_trace=[e.to_dict() for e in audit],
                    plan_fingerprint=plan.fingerprint)

        router.last_audit = audit
        router.note_latencies(audit)
        raise Abstention(
            "routing plan exhausted: no rung cleared its gate",
            reason="ladder_exhausted",
            ladder_trace=[e.to_dict() for e in audit],
            plan_fingerprint=plan.fingerprint)

    @staticmethod
    def _finish(router, plan, audit, state, spec, policy, result, i,
                backend_name, gate, early_exit, detail,
                already_logged: bool = False):
        for entry in audit:
            if entry.rung_index == i:
                entry.outcome = RUNG_ACCEPTED
                entry.detail = detail
                break
        if not already_logged:
            router._log_attempt(state, spec, result, policy, gate)
        result.metadata["routing_plan"] = plan.to_dict()
        result.metadata["ladder_trace"] = [e.to_dict() for e in audit]
        result.metadata["ladder_rung"] = i
        result.metadata["ladder_backend"] = backend_name
        result.metadata["execution"] = "early_exit"
        if early_exit:
            result.metadata["early_exit"] = early_exit
        router.last_audit = audit
        router.note_latencies(audit)
        return RoutingDecision(result=result, plan=plan,
                               audit=[e.to_dict() for e in audit],
                               accepted_rung=i)
