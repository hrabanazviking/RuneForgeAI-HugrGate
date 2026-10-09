"""Hedged inference. Slice 065.

When the primary rung is slow, waiting it out wastes the latency budget;
when it is merely *thought* slow, abandoning it wastes work. Hedging
splits the difference: launch the primary, and if it has not finished
within the hedge delay, launch the next rung as a *hedge* alongside it.
The first result to clear its gate wins; the loser is cancelled
best-effort.

- Delay: ``options.hedge_delay_ms``, but only when the QoS profile
  allows hedging (``qos_profile(...).hedge_allowed``) — otherwise the
  executor degrades to strict serial, documented in the plan rationale.
- A rung that *completes* below its gate hands off immediately: the next
  rung launches at once instead of waiting out the delay.
- Every attempt flows through the same ``skip_reason`` / ``_attempt`` /
  provenance / feedback path as the other executors; hedged launches
  are marked in the audit detail.

This is the classic "hedged requests" pattern (Dean & Barroso) applied
to rung selection rather than replicas.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import Dict, List

from hugrgate.errors import Abstention
from hugrgate.ladder import (RUNG_ACCEPTED, RUNG_BELOW_CONFIDENCE,
                             RUNG_CANCELLED, RUNG_ERROR,
                             RUNG_SKIPPED_LATENCY, RUNG_SKIPPED_PRIVACY,
                             RUNG_SKIPPED_UNKNOWN, RUNG_SKIPPED_UNSUPPORTED,
                             RUNG_UNAVAILABLE, LadderAuditEntry)
from hugrgate.routing.architecture import (LadderRouterV2, RouterContext,
                                            RungExecutor, RoutingDecision,
                                            RoutingPlan)
from hugrgate.routing.qos import qos_profile

__all__ = [
    "HedgedPlanExecutor",
]


class HedgedPlanExecutor(RungExecutor):
    """Primary-first with delayed hedge launches."""

    def execute(self, router: LadderRouterV2, plan: RoutingPlan,
                state, ctx: RouterContext) -> RoutingDecision:
        profile = qos_profile(ctx.options.qos)
        hedging = profile.hedge_allowed
        delay_s = ctx.options.hedge_delay_ms / 1000.0
        policy = ctx.policy
        started = time.perf_counter()

        runnable = []
        audit: List[LadderAuditEntry] = []
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
        closed = threading.Event()
        results: Dict[int, object] = {}

        def run_one(item, hedged: bool):
            i, node, backend = item
            local: List[LadderAuditEntry] = []
            result = router._attempt(backend, state, ctx.spec, None,
                                     local, i)
            with lock:
                if closed.is_set():
                    return  # winner already returned; drop late stragglers
                if result is None:
                    outcome = local[-1].outcome if local else RUNG_ERROR
                    entry = LadderAuditEntry(
                        i, backend.name, outcome,
                        detail=((local[-1].detail + " [hedged]"
                                 if hedged else local[-1].detail)
                                if local else "no attempt record"),
                        latency_ms=local[-1].latency_ms if local else 0.0)
                    audit.append(entry)
                    if outcome in (RUNG_UNAVAILABLE, RUNG_ERROR):
                        router.note_availability(backend.name, False)
                    results[i] = None
                    return
                router.note_availability(backend.name, True)
                router.note_cost(backend, result)
                router.note_energy(backend, result)
                gate = max(node.min_confidence, policy.minimum_probability)
                entry = local[-1]
                if result.probability >= gate:
                    entry.outcome = RUNG_ACCEPTED
                    entry.detail = (f"probability {result.probability:.3f} "
                                    f"cleared gate {gate:.3f}"
                                    + (" [hedged]" if hedged else ""))
                    won = True
                else:
                    entry.outcome = RUNG_BELOW_CONFIDENCE
                    entry.detail = (f"probability {result.probability:.3f} "
                                    f"below gate {gate:.3f}"
                                    + (" [hedged]" if hedged else ""))
                    won = False
                audit.append(entry)
                router._log_attempt(state, ctx.spec, result, policy, gate)
                results[i] = (node, backend, result, gate, won)

        if not hedging:
            plan.rationale.append(
                f"hedging disabled for QoS {ctx.options.qos}; serial climb")

        pending = list(runnable)
        in_flight: Dict[object, tuple] = {}
        winner = None
        # Without hedging the wait is unbounded: strict serial semantics.
        timeout = delay_s if hedging else None

        pool = ThreadPoolExecutor(max_workers=max(len(runnable), 1))
        try:
            def launch(hedged: bool):
                item = pending.pop(0)
                fut = pool.submit(run_one, item, hedged)
                in_flight[fut] = item

            if pending:
                launch(hedged=False)
            while in_flight:
                done, _ = wait(list(in_flight), timeout=timeout,
                               return_when=FIRST_COMPLETED)
                for fut in done:
                    item = in_flight.pop(fut)
                    fut.result()  # re-raise unexpected errors
                    i = item[0]
                    outcome = results.get(i)
                    if isinstance(outcome, tuple) and outcome[4]:
                        winner = (i, *outcome[:4])
                if winner is not None:
                    break
                if not done:
                    # Timeout with nothing finished: hedge, if allowed and
                    # anything remains; otherwise keep waiting.
                    if hedging and pending:
                        launch(hedged=True)
                else:
                    # Something finished without winning: promote the next
                    # rung immediately rather than waiting out the delay.
                    if pending:
                        launch(hedged=False)
        finally:
            if winner is not None:
                # Prompt return: cancel stragglers, record them, and do not
                # wait for them. The closed flag drops their late writes.
                closed.set()
                for fut, item in list(in_flight.items()):
                    i, _node, backend = item
                    if not fut.done():
                        fut.cancel()
                        audit.append(LadderAuditEntry(
                            i, backend.name, RUNG_CANCELLED,
                            detail="hedge straggler cancelled after winner"))
                pool.shutdown(wait=False, cancel_futures=True)
            else:
                pool.shutdown(wait=True)

        audit.sort(key=lambda e: (e.rung_index, e.latency_ms))
        router.last_audit = audit
        router.note_latencies(audit)
        if winner is not None:
            i, node, backend, result, gate = winner
            result.metadata["routing_plan"] = plan.to_dict()
            result.metadata["ladder_trace"] = [e.to_dict() for e in audit]
            result.metadata["ladder_rung"] = i
            result.metadata["ladder_backend"] = backend.name
            result.metadata["execution"] = "hedged"
            return RoutingDecision(result=result, plan=plan,
                                   audit=[e.to_dict() for e in audit],
                                   accepted_rung=i)
        raise Abstention(
            "hedged plan exhausted: no rung cleared its gate",
            reason="ladder_exhausted",
            ladder_trace=[e.to_dict() for e in audit],
            plan_fingerprint=plan.fingerprint)
