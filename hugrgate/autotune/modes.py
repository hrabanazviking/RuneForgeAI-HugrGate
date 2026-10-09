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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

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
