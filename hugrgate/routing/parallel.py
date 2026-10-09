"""Parallel speculative rungs. Slice 064.

Instead of climbing serially, :class:`ParallelPlanExecutor` fans the
plan's rungs out across a thread pool and takes the *first result that
clears its gate*. Every rung still passes the same pre-run
``skip_reason`` checks, the same ``_attempt`` path (validation, audit,
provenance), and the same feedback hooks as the serial executor — only
the *scheduling* changes.

Fan-out width is ``min(options.parallel_width,
qos_profile(options.qos).parallel_width)``: the QoS posture caps how
speculative a request may be (best_effort never fans out). Rungs beyond
the width run in a second wave only if the first wave produced no
winner.

Thread-safety contract: ``backend.evaluate`` must be safe to call from
pool threads (true for stateless backends; stateful ones should guard
themselves). Audit/provenance/feedback writes are serialized under one
lock inside the executor.

Cancellation is best-effort: once a winner is found, pending futures
are cancelled; already-running backends run to completion but their
results are recorded, not returned.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from hugrgate.errors import Abstention
from hugrgate.ladder import (
    RUNG_ACCEPTED,
    RUNG_BELOW_CONFIDENCE,
    RUNG_ERROR,
    RUNG_SKIPPED_UNKNOWN,
    RUNG_UNAVAILABLE,
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
    "ParallelPlanExecutor",
]

class ParallelPlanExecutor(RungExecutor):
    """Execute a plan's rungs concurrently; first gate-clear wins."""

    def execute(self, router: LadderRouterV2, plan: RoutingPlan,
                state, ctx: RouterContext) -> RoutingDecision:
        width = min(ctx.options.parallel_width,
                    qos_profile(ctx.options.qos).parallel_width)
        policy = ctx.policy
        started = time.perf_counter()

        # Phase 1 (main thread): pre-run checks, exactly like serial.
        runnable = []  # (index, node, backend)
        audit: list[LadderAuditEntry] = []
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
            runnable.append((i, node, backend))

        lock = threading.Lock()
        winner = {}

        def run_one(item):
            i, node, backend = item
            local_audit: list[LadderAuditEntry] = []
            result = router._attempt(backend, state, ctx.spec, None,
                                     local_audit, i)
            with lock:
                if result is None:
                    outcome = (local_audit[-1].outcome
                               if local_audit else RUNG_ERROR)
                    audit.append(LadderAuditEntry(
                        i, backend.name, outcome,
                        detail=(local_audit[-1].detail
                                if local_audit else "no attempt record"),
                        latency_ms=(local_audit[-1].latency_ms
                                    if local_audit else 0.0)))
                    if outcome in (RUNG_UNAVAILABLE, RUNG_ERROR):
                        router.note_availability(backend.name, False)
                    return None
                router.note_availability(backend.name, True)
                router.note_cost(backend, result)
                router.note_energy(backend, result)
                gate = max(node.min_confidence, policy.minimum_probability)
                if result.probability >= gate:
                    entry = local_audit[-1]
                    entry.outcome = RUNG_ACCEPTED
                    entry.detail = (f"probability {result.probability:.3f} "
                                    f"cleared gate {gate:.3f}")
                    audit.append(entry)
                    router._log_attempt(state, ctx.spec, result, policy, gate)
                    if "winner" not in winner:
                        winner["winner"] = (i, node, backend, result, gate)
                    return result
                entry = local_audit[-1]
                entry.outcome = RUNG_BELOW_CONFIDENCE
                entry.detail = (f"probability {result.probability:.3f} "
                                f"below gate {gate:.3f}")
                audit.append(entry)
                router._log_attempt(state, ctx.spec, result, policy, gate)
                return None

        # Phase 2: waves of up to `width` concurrent rungs.
        pending = list(runnable)
        while pending and "winner" not in winner:
            wave, pending = pending[:width], pending[width:]
            with ThreadPoolExecutor(max_workers=len(wave)) as pool:
                futures = {pool.submit(run_one, item): item
                           for item in wave}
                for future in as_completed(futures):
                    future.result()  # re-raise unexpected errors
                    if "winner" in winner:
                        for f in futures:
                            f.cancel()
                        break

        audit.sort(key=lambda e: (e.rung_index, e.latency_ms))
        router.last_audit = audit
        router.note_latencies(audit)
        if "winner" in winner:
            i, node, backend, result, _gate = winner["winner"]
            result.metadata["routing_plan"] = plan.to_dict()
            result.metadata["ladder_trace"] = [e.to_dict() for e in audit]
            result.metadata["ladder_rung"] = i
            result.metadata["ladder_backend"] = backend.name
            result.metadata["execution"] = "parallel_speculative"
            return RoutingDecision(result=result, plan=plan,
                                   audit=[e.to_dict() for e in audit],
                                   accepted_rung=i)
        raise Abstention(
            "parallel plan exhausted: no rung cleared its gate",
            reason="ladder_exhausted",
            ladder_trace=[e.to_dict() for e in audit],
            plan_fingerprint=plan.fingerprint)
