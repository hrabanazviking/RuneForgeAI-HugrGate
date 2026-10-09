"""Optimization modes: offline, shadow, canary. Campaign XIX.

- Slice 466: :class:`OfflineDriver` — proposals are journaled and may
  be *replayed* against recorded telemetry; nothing ever touches the
  live config.
- Slice 467: :class:`ShadowDriver` — proposals are evaluated
  side-by-side with live traffic; compared, never applied.
- Slice 468: :class:`CanaryDriver` — proposals apply to a traffic
  fraction with automatic guardrails.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from hugrgate.autotune.controller import (
    Disposition,
    DriverResult,
    Mode,
    ModeDriver,
    Proposal,
    TuningContext,
)
from hugrgate.errors import AutotuneError

__all__ = [
    "CanaryDriver",
    "CanaryLease",
    "OfflineDriver",
    "ShadowDriver",
]


@dataclass
class OfflineDriver(ModeDriver):
    """Journal proposals and replay them against recorded telemetry.

    Slice 466. The offline driver never applies anything: ``handle``
    records the proposal (disposition RECORDED) and returns
    immediately. Operators (or slice 474's benchmark) can later call
    :meth:`replay` to score a journaled proposal's changes with an
    evaluator over recorded data, attaching the measured result to
    the journal entry. The journal is exportable for audit.
    """

    mode: Mode = Mode.OFFLINE
    journal: list[dict[str, Any]] = field(default_factory=list)

    def handle(self, proposal: Proposal, ctx: TuningContext) -> DriverResult:
        entry = {"proposal": proposal.to_dict(),
                 "disposition": Disposition.RECORDED.value,
                 "replay": None,
                 "mode": self.mode.value,
                 "run_id": ctx.run_id}
        self.journal.append(entry)
        return DriverResult(proposal_id=proposal.proposal_id,
                            disposition=Disposition.RECORDED,
                            detail={"journal_index": len(self.journal) - 1})

    def replay(self, proposal_id: str,
               evaluator: Callable[[Mapping[str, Any]], float]) -> float:
        """Score a journaled proposal's changes; record and return it."""
        for entry in self.journal:
            if entry["proposal"]["proposal_id"] == proposal_id:
                try:
                    score = float(evaluator(
                        entry["proposal"]["changes"]))
                except Exception as exc:  # evaluator isolation
                    raise AutotuneError("offline replay evaluator raised",
                                        proposal=proposal_id,
                                        error=repr(exc)) from exc
                entry["replay"] = {"score": score}
                return score
        raise AutotuneError("proposal not in offline journal",
                            proposal=proposal_id)

    def export(self) -> list[dict[str, Any]]:
        """A JSON-serializable copy of the journal."""
        import copy
        return copy.deepcopy(self.journal)

    def clear(self) -> None:
        self.journal.clear()


@dataclass
class ShadowDriver(ModeDriver):
    """Compare proposals against live config on mirrored traffic.

    Slice 467. The shadow driver scores every proposal's candidate
    config *alongside* the live config on the same recorded samples —
    like a shadow deployment, but fully offline and deterministic.
    Nothing is applied; the verdict is recorded:

    - ``would_win``: shadow mean beats live mean by ``min_delta``;
    - ``would_lose``: live beats shadow by ``min_delta``;
    - ``tie``: within ``min_delta``.

    ``live_scorer`` / ``shadow_scorer`` map ``(values, sample)`` to a
    higher-is-better score. Scorers are operator-supplied (e.g. a
    simulator over recorded decisions); a crashing scorer becomes
    :class:`AutotuneError`, never a silent tie.
    """

    mode: Mode = Mode.SHADOW
    samples: Sequence[Mapping[str, Any]] = field(default_factory=list)
    live_scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], float] | None = None
    shadow_scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], float] | None = None
    min_delta: float = 0.005
    journal: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.samples:
            raise AutotuneError("shadow driver needs samples")
        if self.live_scorer is None or self.shadow_scorer is None:
            raise AutotuneError("shadow driver needs live/shadow scorers")

    def _mean(self, scorer: Callable[[Mapping[str, Any], Mapping[str, Any]], float],
               values: Mapping[str, Any], proposal_id: str) -> float:
        try:
            scores = [float(scorer(values, s)) for s in self.samples]
        except Exception as exc:  # scorer isolation
            raise AutotuneError("shadow scorer raised",
                                proposal=proposal_id,
                                error=repr(exc)) from exc
        return statistics.fmean(scores)

    def handle(self, proposal: Proposal, ctx: TuningContext) -> DriverResult:
        live_values = ctx.store.snapshot()
        candidate = dict(live_values)
        candidate.update(proposal.changes)
        live = self._mean(self.live_scorer, live_values,  # type: ignore[arg-type]
                          proposal.proposal_id)
        shadow = self._mean(self.shadow_scorer, candidate,  # type: ignore[arg-type]
                            proposal.proposal_id)
        delta = shadow - live
        verdict = ("would_win" if delta >= self.min_delta
                   else "would_lose" if delta <= -self.min_delta
                   else "tie")
        self.journal.append({
            "proposal": proposal.to_dict(),
            "disposition": Disposition.SHADOWED.value,
            "verdict": verdict,
            "live_mean": live,
            "shadow_mean": shadow,
            "delta": delta,
            "n_samples": len(self.samples),
            "run_id": ctx.run_id,
        })
        return DriverResult(
            proposal_id=proposal.proposal_id,
            disposition=Disposition.SHADOWED,
            detail={"verdict": verdict, "delta": delta,
                    "live_mean": live, "shadow_mean": shadow,
                    "journal_index": len(self.journal) - 1})


@dataclass
class CanaryLease:
    """One in-flight canary: applied changes plus the way back."""

    lease_id: str
    proposal_id: str
    changes: dict[str, Any]
    previous: dict[str, Any]
    fraction: float
    started_at: float
    ends_at: float
    status: str = "active"  # active | promoted | rolled_back | expired
    events: list[str] = field(default_factory=list)


@dataclass
class CanaryDriver(ModeDriver):
    """Apply proposals to a traffic fraction with guardrails.

    Slice 468. The canary driver *does* apply the proposal — through
    the store, so type/bounds validation still holds — but records a
    :class:`CanaryLease` with the pre-canary snapshot, the traffic
    fraction, and an expiry. :meth:`poll` is the heartbeat:

    - guardrail breach -> restore the snapshot (``rolled_back``);
    - lease expiry without promotion -> restore (``expired``);
    - :meth:`promote` marks the canary good (``promoted``, stays
      applied).

    Only one canary may be active at a time; a second proposal while
    one is active is REJECTED, not queued. Guardrails are
    zero-argument callables returning ``(ok, reason)``; a raising
    guardrail counts as a breach (fail closed). Slice 469 builds the
    declarative rollback triggers on top of this mechanism.
    """

    mode: Mode = Mode.CANARY
    fraction: float = 0.05
    lease_seconds: float = 600.0
    guardrails: list[Callable[[], tuple[bool, str]]] = field(
        default_factory=list)
    clock: Callable[[], float] = time.time
    leases: list[CanaryLease] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 < self.fraction < 1.0:
            raise AutotuneError("canary fraction must be in (0, 1)",
                                fraction=self.fraction)
        if self.lease_seconds <= 0:
            raise AutotuneError("lease_seconds must be positive")

    def _active(self) -> CanaryLease | None:
        return next((lease for lease in self.leases
                     if lease.status == "active"), None)

    def handle(self, proposal: Proposal, ctx: TuningContext) -> DriverResult:
        if self._active() is not None:
            return DriverResult(
                proposal_id=proposal.proposal_id,
                disposition=Disposition.REJECTED,
                detail={"reason": "canary already active"})
        previous = ctx.store.snapshot()
        applied = ctx.store.apply(proposal.changes)
        now = self.clock()
        lease = CanaryLease(
            lease_id=f"canary-{uuid4().hex[:10]}",
            proposal_id=proposal.proposal_id,
            changes=dict(applied),
            previous=previous,
            fraction=self.fraction,
            started_at=now,
            ends_at=now + self.lease_seconds,
            events=[f"applied at {now:.1f}"])
        self.leases.append(lease)
        return DriverResult(
            proposal_id=proposal.proposal_id,
            disposition=Disposition.CANARIED,
            detail={"lease_id": lease.lease_id,
                    "fraction": self.fraction,
                    "applied": applied})

    def poll(self, ctx: TuningContext) -> list[dict[str, Any]]:
        """Heartbeat: enforce guardrails and expiry. Returns actions."""
        actions: list[dict[str, Any]] = []
        lease = self._active()
        if lease is None:
            return actions
        now = self.clock()
        if now >= lease.ends_at:
            ctx.store.restore(lease.previous)
            lease.status = "expired"
            lease.events.append(f"expired at {now:.1f}; config restored")
            actions.append({"lease_id": lease.lease_id,
                            "action": "expired_rollback"})
            return actions
        for guard in self.guardrails:
            try:
                ok, reason = guard()
            except Exception as exc:  # noqa: BLE001 - fail closed on guardrail crash
                ok, reason = False, f"guardrail raised: {exc!r}"
            if not ok:
                ctx.store.restore(lease.previous)
                lease.status = "rolled_back"
                lease.events.append(f"guardrail breach at {now:.1f}: "
                                    f"{reason}; config restored")
                actions.append({"lease_id": lease.lease_id,
                                "action": "guardrail_rollback",
                                "reason": reason})
                return actions
        actions.append({"lease_id": lease.lease_id, "action": "hold"})
        return actions

    def promote(self, lease_id: str) -> None:
        for lease in self.leases:
            if lease.lease_id == lease_id:
                if lease.status != "active":
                    raise AutotuneError("only active leases promote",
                                        lease=lease_id,
                                        status=lease.status)
                lease.status = "promoted"
                lease.events.append("promoted by operator")
                return
        raise AutotuneError("unknown lease", lease=lease_id)
