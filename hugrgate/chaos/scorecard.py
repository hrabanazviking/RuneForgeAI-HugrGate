"""Reliability scorecard: one graded view over experiment reports (slice 274).

The campaign built six reporting shapes — experiment reports,
dependency-matrix dicts, degradation reports, recovery reports,
soak reports, crash reports. A scorecard aggregates them into a
single verdict for the release gate (slice 275): per-category
entries, a weighted score, a letter grade, and PASS/FAIL.

Grading is strict by default: the verdict threshold is 1.0 —
chaos findings are release-blockers until fixed or *explicitly
waived*. :meth:`Scorecard.waive` records the waiver with a reason
so nothing is silently dropped; waived entries count as passed
but stay visible in the report.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import SpecError

__all__ = ["Scorecard", "ScorecardEntry", "ScorecardReport"]

_GRADE_BANDS = ((0.95, "A"), (0.85, "B"), (0.70, "C"), (0.50, "D"))


@dataclass
class ScorecardEntry:
    """One graded line: what was checked and whether it held."""

    name: str
    category: str
    passed: bool
    note: str = ""
    weight: float = 1.0
    waived: bool = False
    waiver_reason: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpecError("scorecard entry name must be non-empty")
        if not self.category.strip():
            raise SpecError("scorecard entry category must be non-empty")
        if self.weight <= 0:
            raise SpecError(
                f"scorecard entry weight must be positive, got "
                f"{self.weight!r}")

    @property
    def counts_as_passed(self) -> bool:
        return self.passed or self.waived

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "category": self.category,
                "passed": self.passed, "note": self.note,
                "weight": self.weight, "waived": self.waived,
                "waiver_reason": self.waiver_reason}


@dataclass
class ScorecardReport:
    """The built scorecard."""

    title: str
    entries: list[ScorecardEntry]
    threshold: float
    built_at: float = field(default_factory=time.monotonic)

    @property
    def total_weight(self) -> float:
        return sum(e.weight for e in self.entries)

    @property
    def score(self) -> float:
        total = self.total_weight
        if total == 0:
            return 0.0
        earned = sum(e.weight for e in self.entries
                     if e.counts_as_passed)
        return earned / total

    @property
    def grade(self) -> str:
        for bound, letter in _GRADE_BANDS:
            if self.score >= bound:
                return letter
        return "F"

    @property
    def failed(self) -> list[str]:
        return [e.name for e in self.entries
                if not e.counts_as_passed]

    @property
    def waived(self) -> list[str]:
        return [e.name for e in self.entries if e.waived]

    @property
    def verdict(self) -> str:
        return "PASS" if self.score >= self.threshold else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        report = {"title": self.title,
                  "verdict": self.verdict,
                  "score": round(self.score, 4),
                  "grade": self.grade,
                  "threshold": self.threshold,
                  "entries": [e.to_dict() for e in self.entries],
                  "failed": self.failed,
                  "waived": self.waived,
                  "built_at": self.built_at}
        json.dumps(report)  # contract: always serializable
        return report

    def render(self) -> str:
        """Human-readable one-page scorecard."""
        lines = [f"# {self.title}",
                 f"verdict: {self.verdict} "
                 f"(score {self.score:.2%}, grade {self.grade}, "
                 f"threshold {self.threshold:.0%})",
                 ""]
        by_cat: dict[str, list[ScorecardEntry]] = {}
        for e in self.entries:
            by_cat.setdefault(e.category, []).append(e)
        for cat in sorted(by_cat):
            lines.append(f"## {cat}")
            for e in by_cat[cat]:
                mark = "PASS" if e.passed else (
                    "WAIVED" if e.waived else "FAIL")
                extra = f" — {e.note}" if e.note else ""
                if e.waived and e.waiver_reason:
                    extra += f" (waived: {e.waiver_reason})"
                lines.append(f"- [{mark}] {e.name}{extra}")
            lines.append("")
        if self.failed:
            lines.append(f"failed: {', '.join(self.failed)}")
        return "\n".join(lines).rstrip() + "\n"


class Scorecard:
    """Collect graded entries from every campaign report shape."""

    def __init__(self, title: str = "Reliability scorecard",
                 threshold: float = 1.0) -> None:
        if not title.strip():
            raise SpecError("scorecard title must be non-empty")
        if not 0 < threshold <= 1.0:
            raise SpecError(
                f"threshold must be in (0, 1], got {threshold!r}")
        self._title = title
        self._threshold = threshold
        self._lock = threading.RLock()
        self._entries: dict[str, ScorecardEntry] = {}

    def add(self, entry: ScorecardEntry) -> Scorecard:
        if not isinstance(entry, ScorecardEntry):
            raise SpecError(
                "can only add ScorecardEntry, got "
                f"{type(entry).__name__}")
        with self._lock:
            if entry.name in self._entries:
                raise SpecError(
                    f"duplicate scorecard entry {entry.name!r}")
            self._entries[entry.name] = entry
        return self

    def waive(self, name: str, reason: str) -> Scorecard:
        """Waive a failing entry, audibly: the waiver and its reason
        stay in the report."""
        if not reason.strip():
            raise SpecError("waiver reason must be non-empty")
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                raise SpecError(
                    f"cannot waive unknown entry {name!r}")
            if entry.passed:
                raise SpecError(
                    f"entry {name!r} already passed; nothing to waive")
            if entry.waived:
                raise SpecError(
                    f"entry {name!r} is already waived")
            self._entries[name] = ScorecardEntry(
                name=entry.name, category=entry.category,
                passed=False, note=entry.note, weight=entry.weight,
                waived=True, waiver_reason=reason)
        return self

    # --- adapters: one per campaign report shape ---------------------------

    def add_experiment(self, report: Any, weight: float = 1.0
                       ) -> Scorecard:
        return self.add(ScorecardEntry(
            name=f"experiment:{report.experiment}",
            category="chaos-experiments",
            passed=bool(report.all_passed),
            note=("steady state held, all faults behaved as hypothesized"
                  if report.all_passed else
                  "steady state broke or a fault misbehaved"),
            weight=weight))

    def add_dependency_matrix(self, report: dict[str, Any],
                              weight: float = 1.0,
                              name: str = "dependency-matrix") -> Scorecard:
        failed = report.get("failed", [])
        return self.add(ScorecardEntry(
            name=name,
            category="dependencies",
            passed=bool(report.get("all_survived", False)),
            note=(f"{report.get('survived', 0)}/"
                  f"{report.get('scenarios', 0)} scenarios survived"
                  + (f"; failed: {', '.join(failed)}" if failed else "")),
            weight=weight))

    def add_degradation(self, report: Any, weight: float = 1.0
                        ) -> Scorecard:
        return self.add(ScorecardEntry(
            name=f"degradation:{report.plan_name}",
            category="degradation",
            passed=bool(report.degraded_gracefully),
            note=f"outcome={report.outcome}",
            weight=weight))

    def add_recovery(self, report: Any, weight: float = 1.0
                     ) -> Scorecard:
        return self.add(ScorecardEntry(
            name=f"recovery:{report.verifier_name}",
            category="recovery",
            passed=bool(report.recovered),
            note=(f"recovered in {report.attempts} attempt(s)"
                  if report.recovered else "not recovered"),
            weight=weight))

    def add_soak(self, report: Any, weight: float = 1.0) -> Scorecard:
        return self.add(ScorecardEntry(
            name="soak",
            category="soak",
            passed=bool(report.passed),
            note=(f"{report.ops_completed} ops, "
                  f"{len(report.violations)} violations, "
                  f"{sum(report.unexpected_errors.values())} "
                  f"unexpected errors"),
            weight=weight))

    def add_crash(self, report: Any, weight: float = 1.0) -> Scorecard:
        return self.add(ScorecardEntry(
            name="crash-only-restart",
            category="recovery",
            passed=bool(report.recovered_cleanly),
            note=(f"SIGKILLed worker recovered at counter "
                  f"{report.recovered_counter}"
                  if report.recovered_cleanly else
                  "worker did not recover cleanly"),
            weight=weight))

    # --- build ---------------------------------------------------------------

    def entry_names(self) -> list[str]:
        with self._lock:
            return sorted(self._entries)

    def build(self) -> ScorecardReport:
        with self._lock:
            entries = [self._entries[n]
                       for n in sorted(self._entries)]
        if not entries:
            raise SpecError("cannot build an empty scorecard")
        return ScorecardReport(title=self._title, entries=entries,
                               threshold=self._threshold)
