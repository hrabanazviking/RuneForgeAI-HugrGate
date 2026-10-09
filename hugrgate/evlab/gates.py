"""CI quality gates — declarative pass/fail over results. Slice 373.

Gates turn "the numbers look fine" into a checkable contract: a
:class:`Gate` names a metric, a comparison, and a threshold, applied
to one backend, several, or all.  :func:`check_gates` evaluates a
:class:`GateSuite` against a results mapping (or a
:class:`RunRecord`); :func:`assert_gates` raises
:class:`EvalGateError` naming every failure — the CI-red path.

Fail-closed by design: a gate on an unscored metric, or on a
backend absent from the results, *fails* with ``actual=None``
rather than passing silently.  A gate that cannot see its evidence
is not a gate.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import EvalError, EvalGateError
from hugrgate.evlab.api import RunRecord

__all__ = [
    "Gate",
    "GateResult",
    "GateSuite",
    "assert_gates",
    "check_gates",
]

_OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
}


@dataclass
class Gate:
    """One quality gate: ``metric`` ``op`` ``threshold`` (slice 373)."""

    name: str
    metric: str
    op: str
    threshold: float
    backends: tuple[str, ...] = ("*",)

    def __post_init__(self) -> None:
        if not self.name:
            raise EvalError("gate name must be a non-empty string")
        if not self.metric:
            raise EvalError(f"gate {self.name!r}: metric must be set")
        if self.op not in _OPS:
            raise EvalError(
                f"gate {self.name!r}: op must be one of "
                f"{sorted(_OPS)}, got {self.op!r}")
        if not self.backends:
            raise EvalError(
                f"gate {self.name!r}: needs at least one backend "
                f"('*' for all)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "metric": self.metric,
            "op": self.op,
            "threshold": self.threshold,
            "backends": list(self.backends),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Gate:
        return cls(
            name=data["name"],
            metric=data["metric"],
            op=data["op"],
            threshold=data["threshold"],
            backends=tuple(data.get("backends", ("*",))),
        )


@dataclass
class GateResult:
    """Outcome of one gate on one backend (slice 373)."""

    gate: str
    backend: str
    metric: str
    op: str
    threshold: float
    actual: float | None
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "backend": self.backend,
            "metric": self.metric,
            "op": self.op,
            "threshold": self.threshold,
            "actual": self.actual,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class GateSuite:
    """A named set of gates evaluated together (slice 373)."""

    name: str
    gates: list[Gate]

    def __post_init__(self) -> None:
        if not self.name:
            raise EvalError("gate suite name must be non-empty")
        seen: set[str] = set()
        for gate in self.gates:
            if gate.name in seen:
                raise EvalError(
                    f"duplicate gate name {gate.name!r} in suite "
                    f"{self.name!r}")
            seen.add(gate.name)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name,
                "gates": [g.to_dict() for g in self.gates]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GateSuite:
        return cls(name=data["name"],
                   gates=[Gate.from_dict(g) for g in data["gates"]])


def _resolve_backends(gate: Gate,
                      results: Mapping[str, Any]) -> list[str]:
    if gate.backends == ("*",):
        return sorted(results)
    return list(gate.backends)


def check_gates(
    suite: GateSuite,
    results: Mapping[str, Mapping[str, Any]] | RunRecord,
) -> list[GateResult]:
    """Evaluate every gate; return per-backend results (never raises)."""
    if isinstance(results, RunRecord):
        table: Mapping[str, Mapping[str, Any]] = results.backends
    else:
        table = results
    outcomes: list[GateResult] = []
    for gate in suite.gates:
        cmp = _OPS[gate.op]
        for backend in _resolve_backends(gate, table):
            metrics = table.get(backend, {})
            actual = metrics.get(gate.metric)
            if isinstance(actual, bool) or not isinstance(
                    actual, (int, float)):
                outcomes.append(GateResult(
                    gate=gate.name, backend=backend, metric=gate.metric,
                    op=gate.op, threshold=gate.threshold, actual=None,
                    passed=False,
                    detail=(f"metric {gate.metric!r} not scored for "
                            f"backend {backend!r}"),
                ))
                continue
            value = float(actual)
            passed = bool(cmp(value, gate.threshold))
            outcomes.append(GateResult(
                gate=gate.name, backend=backend, metric=gate.metric,
                op=gate.op, threshold=gate.threshold, actual=value,
                passed=passed,
                detail=(f"{value:.4f} {gate.op} {gate.threshold} "
                        f"{'holds' if passed else 'fails'}"),
            ))
    return outcomes


def assert_gates(
    suite: GateSuite,
    results: Mapping[str, Mapping[str, Any]] | RunRecord,
) -> list[GateResult]:
    """Check gates; raise :class:`EvalGateError` listing failures."""
    outcomes = check_gates(suite, results)
    failures = [o for o in outcomes if not o.passed]
    if failures:
        summary = "; ".join(
            f"{o.gate}@{o.backend}: {o.detail}" for o in failures)
        raise EvalGateError(
            f"{len(failures)} gate(s) failed in suite "
            f"{suite.name!r}: {summary}",
            suite=suite.name,
            failures=[o.to_dict() for o in failures],
        )
    return outcomes


def gates_from_config(
    configs: Sequence[Mapping[str, Any]], name: str = "suite"
) -> GateSuite:
    """Build a :class:`GateSuite` from a list of gate dicts."""
    return GateSuite(
        name=name,
        gates=[Gate.from_dict(c) for c in configs],
    )
