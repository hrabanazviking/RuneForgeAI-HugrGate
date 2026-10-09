"""Hot-path inventory — ranked cost centers across profiled runs. Slice 278.

:mod:`hugrgate.profiling` profiles one run; this module answers the
campaign question "where does the time *consistently* go?":

- :class:`HotPathInventory` profiles a workload ``runs`` times,
  aggregates per-function cumulative/self time across runs, and ranks
  the results.  Aggregation (not a single run) is what makes it an
  *inventory* rather than an anecdote.
- :meth:`HotPathInventory.hot` flags functions whose cumulative share
  of total time meets ``hot_threshold`` - the actionable hot set for
  the optimization slices that follow (280-281, 292).
- Reports serialize to dict/markdown for the campaign docs.

Privacy: aggregation keeps function names, so the same strict-privacy
rule as :mod:`hugrgate.profiling` applies — inventories that name
backend internals must not be persisted under a strict policy.  The
inventory itself is policy-agnostic; the caller decides what to store.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import ProfilingError
from hugrgate.log import get_logger
from hugrgate.profiling import DecisionProfiler, ProfileReport

logger = get_logger(__name__)

__all__ = [
    "HotFunction",
    "HotPathInventory",
]


@dataclass
class HotFunction:
    """Aggregated cost of one function across inventory runs."""
    function: str
    cumtime_ms: float      # summed across runs
    tottime_ms: float      # summed across runs
    calls: int             # summed across runs
    runs_seen: int         # runs in which the function appeared
    share: float = 0.0     # cumtime_ms / inventory total (filled by rank())

    @property
    def percall_ms(self) -> float:
        return self.cumtime_ms / self.calls if self.calls else 0.0


@dataclass
class HotPathInventory:
    """Ranked aggregate of profiled runs."""
    runs: int
    total_ms: float
    functions: list[HotFunction] = field(default_factory=list)
    label: str = ""

    def ranked(self) -> list[HotFunction]:
        """Functions ordered by cumulative time, descending."""
        return sorted(self.functions, key=lambda f: f.cumtime_ms,
                      reverse=True)

    def hot(self, threshold: float = 0.05) -> list[HotFunction]:
        """Functions whose cumulative share >= ``threshold``.

        ``threshold`` is a fraction in (0, 1]: 0.05 flags everything
        costing ≥5% of total profiled time.
        """
        if not 0.0 < threshold <= 1.0:
            raise ProfilingError(
                f"hot threshold must be in (0, 1], got {threshold!r}")
        return [f for f in self.ranked() if f.share >= threshold]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "runs": self.runs,
            "total_ms": self.total_ms,
            "functions": [
                {
                    "function": f.function,
                    "cumtime_ms": f.cumtime_ms,
                    "tottime_ms": f.tottime_ms,
                    "calls": f.calls,
                    "runs_seen": f.runs_seen,
                    "share": f.share,
                    "percall_ms": f.percall_ms,
                }
                for f in self.ranked()
            ],
        }

    def to_markdown(self, n: int = 20) -> str:
        lines = [
            f"## Hot-path inventory: {self.label or 'run'}",
            f"{self.runs} runs, {self.total_ms:.1f} ms total profiled",
            "",
            "| rank | function | cumtime (ms) | share | calls | "
            "percall (ms) |",
            "|---|---|---|---|---|---|",
        ]
        for i, f in enumerate(self.ranked()[:n], 1):
            lines.append(
                f"| {i} | `{f.function}` | {f.cumtime_ms:.2f} | "
                f"{f.share:.1%} | {f.calls} | {f.percall_ms:.4f} |")
        return "\n".join(lines)


def _aggregate(reports: list[ProfileReport]) -> tuple[float, list[HotFunction]]:
    by_function: dict[str, HotFunction] = {}
    total = 0.0
    for report in reports:
        for entry in report.entries:
            total += entry.cumtime_ms
            hot = by_function.get(entry.function)
            if hot is None:
                hot = by_function[entry.function] = HotFunction(
                    function=entry.function, cumtime_ms=0.0,
                    tottime_ms=0.0, calls=0, runs_seen=0)
            # Count the run once per function even if cProfile splits rows.
            hot.cumtime_ms += entry.cumtime_ms
            hot.tottime_ms += entry.tottime_ms
            hot.calls += entry.ncalls
        seen = {e.function for e in report.entries}
        for name in seen:
            by_function[name].runs_seen += 1
    functions = list(by_function.values())
    if total > 0:
        for hot in functions:
            hot.share = hot.cumtime_ms / total
    return total, functions


class HotPathCollector:
    """Build a :class:`HotPathInventory` by profiling a workload.

    Parameters
    ----------
    profiler: the :class:`DecisionProfiler` to run with.
    runs: how many profiled runs to aggregate (≥ 1).
    label: inventory label for reports.
    """

    def __init__(self, profiler: DecisionProfiler | None = None,
                 runs: int = 5, label: str = "") -> None:
        if not isinstance(runs, int) or runs < 1:
            raise ProfilingError(
                f"inventory runs must be a positive int, got {runs!r}")
        self.profiler = profiler or DecisionProfiler()
        self.runs = runs
        self.label = label

    def collect(self, workload: Callable[[], Any]) -> HotPathInventory:
        """Profile ``workload()`` ``runs`` times and aggregate."""
        reports: list[ProfileReport] = []
        for i in range(self.runs):
            _result, report = self.profiler.profile(
                workload, label=f"{self.label} run {i + 1}")
            reports.append(report)
        total, functions = _aggregate(reports)
        logger.info("hot-path inventory %r: %d runs, %d functions, "
                    "%.1f ms total", self.label, self.runs,
                    len(functions), total)
        return HotPathInventory(runs=self.runs, total_ms=total,
                                functions=functions, label=self.label)
