"""Release gate — the lab's final verdict. Slice 375.

Campaign XV's capstone: :func:`release_gate` ties the lab together
into one go/no-go decision over a finished run.  It runs, in order:

1. the CI :class:`GateSuite` (slice 373) — any failure holds;
2. regression checks against the :class:`HistoryStore` (slice 370)
   for the declared metrics — any regression holds;
3. the reproducibility manifest (slice 372) — mismatches hold, and
   a missing manifest holds when ``require_repro`` is set;
4. git-SHA provenance — a run with no recorded SHA holds when
   ``require_git_sha`` is set (an unattributable result cannot
   ship).

The outcome is a :class:`ReleaseVerdict` (``"release"`` or
``"hold"`` with every reason named); :func:`assert_release` turns a
hold into :class:`EvalGateError` for CI.  A release with zero gates
is a rubber stamp and is refused outright.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from hugrgate.errors import EvalError, EvalGateError
from hugrgate.evlab.api import RunRecord
from hugrgate.evlab.gates import (
    GateResult,
    GateSuite,
    check_gates,
)
from hugrgate.evlab.history import (
    HistoryStore,
    RegressionFinding,
    detect_regression,
)
from hugrgate.evlab.repro import (
    ReproCheck,
    ReproManifest,
    check_reproducibility,
)

__all__ = [
    "ReleaseVerdict",
    "assert_release",
    "release_gate",
]

RELEASE = "release"
HOLD = "hold"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReleaseVerdict:
    """Go/no-go outcome for one run (slice 375)."""

    decision: str
    reasons: list[str]
    run_id: str
    dataset: str
    decided_at: str
    gate_results: list[dict[str, Any]]
    regressions: list[dict[str, Any]]
    repro_check: dict[str, Any] | None

    @property
    def released(self) -> bool:
        return self.decision == RELEASE

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "run_id": self.run_id,
            "dataset": self.dataset,
            "decided_at": self.decided_at,
            "gate_results": [dict(g) for g in self.gate_results],
            "regressions": [dict(r) for r in self.regressions],
            "repro_check": (dict(self.repro_check)
                            if self.repro_check is not None else None),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReleaseVerdict:
        return cls(
            decision=data["decision"],
            reasons=list(data["reasons"]),
            run_id=data["run_id"],
            dataset=data["dataset"],
            decided_at=data["decided_at"],
            gate_results=[dict(g)
                          for g in data.get("gate_results", [])],
            regressions=[dict(r)
                         for r in data.get("regressions", [])],
            repro_check=(dict(data["repro_check"])
                         if data.get("repro_check") is not None
                         else None),
        )


def release_gate(
    record: RunRecord,
    gates: GateSuite,
    history: HistoryStore | None = None,
    regression_metrics: Sequence[
        tuple[str, float, bool]] = (),
    repro_manifest: ReproManifest | None = None,
    require_repro: bool = True,
    require_git_sha: bool = True,
) -> ReleaseVerdict:
    """Decide release/hold for a finished run.

    ``regression_metrics`` entries are
    ``(metric, min_drop, higher_better)`` triples checked against
    ``history`` (history is required when any are declared).
    """
    if not isinstance(record, RunRecord):
        raise EvalError(
            f"release_gate needs a RunRecord, got "
            f"{type(record).__name__}")
    if not isinstance(gates, GateSuite):
        raise EvalError(
            f"release_gate needs a GateSuite, got "
            f"{type(gates).__name__}")
    if not gates.gates:
        raise EvalError(
            "release_gate refuses a gateless suite: a release with "
            "zero quality gates is a rubber stamp")
    if regression_metrics and history is None:
        raise EvalError(
            "regression_metrics need a history store to compare against")
    for entry in regression_metrics:
        if (not isinstance(entry, tuple) or len(entry) != 3
                or not isinstance(entry[0], str)
                or not isinstance(entry[1], (int, float))
                or not isinstance(entry[2], bool)):
            raise EvalError(
                "regression_metrics entries must be "
                "(metric, min_drop, higher_better) triples")

    reasons: list[str] = []

    gate_outcomes: list[GateResult] = check_gates(gates, record)
    for outcome in gate_outcomes:
        if not outcome.passed:
            reasons.append(
                f"gate {outcome.gate!r} failed on "
                f"{outcome.backend!r}: {outcome.detail}")

    regressions: list[RegressionFinding] = []
    if history is not None:
        backends = sorted(record.backends)
        for metric, min_drop, higher_better in regression_metrics:
            for backend in backends:
                finding = detect_regression(
                    history, record.dataset_name, backend, metric,
                    min_drop=min_drop, higher_better=higher_better,
                    current=record)
                if finding is not None:
                    regressions.append(finding)
                    reasons.append(
                        f"regression: {backend!r} {metric} dropped "
                        f"{finding.drop:.4f} "
                        f"({finding.baseline_run_id} -> "
                        f"{finding.current_run_id})")

    repro_check: ReproCheck | None = None
    if repro_manifest is not None:
        repro_check = check_reproducibility(repro_manifest)
        if not repro_check.ok:
            reasons.append(
                "reproducibility mismatch: "
                + "; ".join(repro_check.mismatches))
    elif require_repro:
        reasons.append(
            "no reproducibility manifest attached "
            "(require_repro=True)")

    if require_git_sha and not record.git_sha:
        reasons.append(
            "run records no git SHA (require_git_sha=True): "
            "unattributable results cannot ship")

    decision = RELEASE if not reasons else HOLD
    return ReleaseVerdict(
        decision=decision,
        reasons=reasons,
        run_id=record.run_id,
        dataset=record.dataset_name,
        decided_at=_utcnow(),
        gate_results=[o.to_dict() for o in gate_outcomes],
        regressions=[r.to_dict() for r in regressions],
        repro_check=repro_check.to_dict() if repro_check else None,
    )


def assert_release(verdict: ReleaseVerdict) -> ReleaseVerdict:
    """Raise :class:`EvalGateError` when the verdict is hold."""
    if not isinstance(verdict, ReleaseVerdict):
        raise EvalError(
            f"assert_release needs a ReleaseVerdict, got "
            f"{type(verdict).__name__}")
    if verdict.decision != RELEASE:
        raise EvalGateError(
            f"release HOLD for run {verdict.run_id!r} "
            f"({verdict.dataset!r}): "
            + "; ".join(verdict.reasons),
            run_id=verdict.run_id,
            dataset=verdict.dataset,
            reasons=list(verdict.reasons),
        )
    return verdict
