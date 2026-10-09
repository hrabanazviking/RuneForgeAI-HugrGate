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

from collections.abc import Callable, Mapping
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
