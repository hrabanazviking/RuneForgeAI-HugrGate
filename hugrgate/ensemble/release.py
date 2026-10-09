"""Ensemble release gate — the council earns its deployment. Slice 125.

A checklist with teeth. :class:`ReleaseGate` composes named checks —
each a zero-argument callable returning ``(passed, detail)`` — and
:meth:`run` produces a :class:`ReleaseVerdict`. A check that raises
fails with the exception recorded; the gate always runs every check.

Built-in check factories (all real measurements, no stubs):

- :func:`benchmark_thresholds` — accuracy / ECE / Brier floors via
  slice 124's harness on labeled states;
- :func:`diversity_floor` — mean disagreement rate (slice 110) must
  clear the floor: a council that never disagrees is redundant;
- :func:`no_correlated_cliques` — slice 115 must find no error
  cliques on the labeled states;
- :func:`adversarial_clean` — slice 123's suite: no ``UNEXPECTED``
  errors, and every case decides fully unless named in
  ``may_refuse`` (honest refusal is allowed where expected);
- :func:`evidence_check` — for what the gate cannot measure
  itself (CI test results, completion notes): the caller supplies
  the verdict and the detail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from hugrgate.backend import Backend
from hugrgate.ensemble.adversarial import (
    AdversarialCase,
    run_adversarial_suite,
)
from hugrgate.ensemble.batch import batch_collect_votes
from hugrgate.ensemble.benchmarks import benchmark_strategies
from hugrgate.ensemble.correlation import detect_correlated_errors
from hugrgate.ensemble.diversity import diversity_summary
from hugrgate.errors import PolicyError
from hugrgate.spec import DecisionSpec

__all__ = [
    "CheckResult",
    "ReleaseVerdict",
    "ReleaseGate",
    "benchmark_thresholds",
    "diversity_floor",
    "no_correlated_cliques",
    "adversarial_clean",
    "evidence_check",
]

#: A check: zero-arg callable returning (passed, detail).
Check = Callable[[], Tuple[bool, str]]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "passed": self.passed,
                "detail": self.detail}


@dataclass
class ReleaseVerdict:
    gate: str
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    @property
    def failures(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> Dict[str, Any]:
        return {"gate": self.gate, "passed": self.passed,
                "checks": [c.to_dict() for c in self.checks]}

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"Release gate {self.gate!r}: {status} "
                 f"({sum(c.passed for c in self.checks)}/"
                 f"{len(self.checks)} checks)"]
        for c in self.checks:
            mark = "PASS" if c.passed else "FAIL"
            lines.append(f"  [{mark}] {c.name}: {c.detail}")
        return "\n".join(lines)


class ReleaseGate:
    """Compose named checks; run them all; get a verdict."""

    def __init__(self, name: str = "ensemble-release"):
        if not name:
            raise PolicyError("ReleaseGate needs a name")
        self.name = name
        self._checks: List[Tuple[str, Check]] = []

    def add(self, name: str, check: Check) -> "ReleaseGate":
        if not callable(check):
            raise PolicyError(
                f"check {name!r} must be callable")
        if any(n == name for n, _ in self._checks):
            raise PolicyError(
                f"duplicate check name {name!r}")
        self._checks.append((name, check))
        return self

    def run(self) -> ReleaseVerdict:
        results = []
        for name, check in self._checks:
            try:
                passed, detail = check()
                results.append(CheckResult(
                    name, bool(passed), str(detail)))
            except Exception as e:  # noqa: BLE001 - the gate reports
                results.append(CheckResult(
                    name, False,
                    f"check raised {type(e).__name__}: {e}"))
        return ReleaseVerdict(gate=self.name, checks=results)


# --- built-in check factories -------------------------------------------------


def benchmark_thresholds(
        member_factory: Callable[[], List[Backend]],
        states: List[Mapping[str, Any]],
        spec: DecisionSpec,
        labels: List[Any],
        strategy: str = "soft",
        min_accuracy: float = 0.5,
        max_ece: float = 0.25,
        max_brier: Optional[float] = None) -> Check:
    """Accuracy/ECE/Brier floors on labeled states."""
    for label, bound in (("min_accuracy", min_accuracy),
                         ("max_ece", max_ece)):
        if not 0.0 <= bound <= 1.0:
            raise PolicyError(
                f"{label} must be in [0, 1], got {bound}")
    if max_brier is not None and not 0.0 <= max_brier <= 2.0:
        raise PolicyError(
            f"max_brier must be in [0, 2], got {max_brier}")

    def check() -> Tuple[bool, str]:
        report = benchmark_strategies(
            member_factory, states, spec, labels,
            strategies=[strategy])
        m = report[strategy]
        problems = []
        if (m["accuracy"] or 0.0) < min_accuracy:
            problems.append(
                f"accuracy {m['accuracy']:.3f} < {min_accuracy}")
        if (m["ece"] or 0.0) > max_ece:
            problems.append(f"ece {m['ece']:.3f} > {max_ece}")
        if max_brier is not None and \
                (m["brier_score"] or 0.0) > max_brier:
            problems.append(
                f"brier {m['brier_score']:.3f} > {max_brier}")
        detail = (f"{strategy}: accuracy={m['accuracy']:.3f}, "
                  f"ece={m['ece']:.3f}, brier={m['brier_score']:.3f}, "
                  f"wall={m['wall_ms']:.1f}ms")
        if problems:
            return False, detail + " :: " + "; ".join(problems)
        return True, detail

    return check


def diversity_floor(
        member_factory: Callable[[], List[Backend]],
        states: List[Mapping[str, Any]],
        spec: DecisionSpec,
        min_disagreement_rate: float = 0.1) -> Check:
    """The council must actually disagree sometimes."""
    if not 0.0 <= min_disagreement_rate <= 1.0:
        raise PolicyError(
            f"min_disagreement_rate must be in [0, 1], got "
            f"{min_disagreement_rate}")

    def check() -> Tuple[bool, str]:
        votes_by_state = batch_collect_votes(
            member_factory(), states, spec)
        rates = [diversity_summary(v)["disagreement_rate"]
                 for v in votes_by_state]
        mean_rate = sum(rates) / len(rates) if rates else 0.0
        detail = (f"mean disagreement rate {mean_rate:.3f} over "
                  f"{len(rates)} states")
        if mean_rate < min_disagreement_rate:
            return False, (detail +
                           f" < floor {min_disagreement_rate}")
        return True, detail

    return check


def no_correlated_cliques(
        member_factory: Callable[[], List[Backend]],
        states: List[Mapping[str, Any]],
        spec: DecisionSpec,
        labels: List[Any],
        threshold: float = 0.7) -> Check:
    """No error cliques on the labeled states."""

    def check() -> Tuple[bool, str]:
        members = member_factory()
        votes_by_state = batch_collect_votes(members, states, spec)
        correct: Dict[str, List[bool]] = {
            m.name: [] for m in members}
        for votes, label in zip(votes_by_state, labels):
            for v in votes:
                if not v.skipped:
                    correct[v.backend].append(v.value == label)
        report = detect_correlated_errors(correct,
                                          threshold=threshold)
        if report.cliques:
            return False, ("correlated-error cliques: " +
                           "; ".join(report.recommendations()))
        return True, (f"no cliques among {len(members)} members "
                      f"(Q threshold {threshold})")

    return check


def adversarial_clean(cases: List[AdversarialCase],
                      may_refuse: Tuple[str, ...] = ()) -> Check:
    """The suite: nothing unexpected, full decisions where required."""

    def check() -> Tuple[bool, str]:
        report = run_adversarial_suite(cases)
        problems = []
        for name, summary in report.items():
            unexpected = [e for e in summary["errors"]
                          if e.startswith("UNEXPECTED")]
            if unexpected:
                problems.append(f"{name}: {unexpected[0]}")
            elif summary["decided"] < summary["states"] \
                    and name not in may_refuse:
                problems.append(
                    f"{name}: decided {summary['decided']}/"
                    f"{summary['states']}")
        detail = (f"{len(report)} adversarial cases, " +
                  (f"problems: {'; '.join(problems)}"
                   if problems else "all clean"))
        return (not problems), detail

    return check


def evidence_check(name: str, passed: bool, detail: str = ""
                   ) -> Tuple[str, Check]:
    """Wrap caller-supplied evidence (CI results, docs) as a check."""
    def check() -> Tuple[bool, str]:
        return passed, detail or ("evidence accepted"
                                  if passed else "evidence missing")

    return name, check
