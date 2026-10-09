"""Decision profiler — cProfile integration for the decide() path. Slice 276.

Campaign XII (Performance Forge) starts by making the invisible visible:
:class:`DecisionProfiler` wraps :meth:`hugrgate.core.HugrGate.decide` (or
any callable) in :mod:`cProfile` and returns a :class:`ProfileReport` with
ranked function entries, wall time, and call counts.

Integration points (not a bolted-on script):

- **Provenance**: :meth:`DecisionProfiler.profile_decision` can attach a
  compact profile summary to ``result.metadata["profile"]`` so a decision
  record carries its own cost evidence.
- **Privacy**: profiling captures fully-qualified function names, which
  can reveal backend internals.  When the policy's ``privacy_class`` is
  ``"strict"``, the summary is *never* attached to the result metadata —
  the report stays local to the caller.
- **Errors**: misconfiguration raises :class:`ProfilingError`
  (``code="profiling_error"``, recoverable — a failed profile run never
  invalidates the decision itself).

:func:`profile_region` is a lightweight nested-region timer for
instrumenting non-decision code without the overhead of cProfile.
"""

from __future__ import annotations

import cProfile
import pstats
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import ProfilingError
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy

logger = get_logger(__name__)

__all__ = [
    "DecisionProfiler",
    "ProfileEntry",
    "ProfileReport",
    "profile_region",
    "region_report",
]

#: pstats sort keys we accept from callers (anything else is a config error).
_SORT_KEYS = frozenset({
    "cumulative", "tottime", "ncalls", "name", "pcalls",
})


@dataclass
class ProfileEntry:
    """One ranked function row from a profile run."""
    function: str          # "module.Class.method" or "module:func"
    ncalls: int
    tottime_ms: float      # time in the function itself, excluding subcalls
    cumtime_ms: float      # time in the function including subcalls
    percall_ms: float      # cumtime / ncalls


@dataclass
class ProfileReport:
    """The outcome of one profiled run."""
    wall_ms: float
    total_calls: int
    primitive_calls: int
    entries: list[ProfileEntry] = field(default_factory=list)
    label: str = ""

    def top(self, n: int = 10) -> list[ProfileEntry]:
        """Return the ``n`` entries with the largest cumulative time."""
        if n < 1:
            raise ProfilingError(f"top(n) requires n >= 1, got {n}")
        return sorted(self.entries, key=lambda e: e.cumtime_ms,
                      reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "wall_ms": self.wall_ms,
            "total_calls": self.total_calls,
            "primitive_calls": self.primitive_calls,
            "entries": [
                {
                    "function": e.function,
                    "ncalls": e.ncalls,
                    "tottime_ms": e.tottime_ms,
                    "cumtime_ms": e.cumtime_ms,
                    "percall_ms": e.percall_ms,
                }
                for e in self.entries
            ],
        }

    def to_markdown(self, n: int = 15) -> str:
        lines = [
            f"## Profile: {self.label or 'run'}",
            f"wall: {self.wall_ms:.2f} ms, calls: {self.total_calls} "
            f"({self.primitive_calls} primitive)",
            "",
            "| function | ncalls | tottime (ms) | cumtime (ms) | "
            "percall (ms) |",
            "|---|---|---|---|---|",
        ]
        for e in self.top(n):
            lines.append(
                f"| `{e.function}` | {e.ncalls} | {e.tottime_ms:.3f} | "
                f"{e.cumtime_ms:.3f} | {e.percall_ms:.4f} |")
        return "\n".join(lines)


def _format_func(func: tuple[str, int, str]) -> str:
    filename, _lineno, funcname = func
    module = filename.rsplit("/", 1)[-1]
    if module.endswith(".py"):
        module = module[:-3]
    return f"{module}:{funcname}"


def _stats_to_report(stats: pstats.Stats, wall_ms: float,
                     label: str) -> ProfileReport:
    entries: list[ProfileEntry] = []
    # pstats.Stats.stats/total_calls/prim_calls exist at runtime;
    # typeshed does not declare them.
    raw_stats = stats.stats  # type: ignore[attr-defined]
    for func, (_cc, nc, tt, ct, _callers) in raw_stats.items():
        entries.append(ProfileEntry(
            function=_format_func(func),
            ncalls=nc,
            tottime_ms=tt * 1000.0,
            cumtime_ms=ct * 1000.0,
            percall_ms=(ct / nc * 1000.0) if nc else 0.0,
        ))
    return ProfileReport(
        wall_ms=wall_ms,
        total_calls=stats.total_calls,  # type: ignore[attr-defined]
        primitive_calls=stats.prim_calls,  # type: ignore[attr-defined]
        entries=entries,
        label=label,
    )


class DecisionProfiler:
    """Profile HugrGate decisions with :mod:`cProfile`.

    Parameters
    ----------
    sort_by: pstats sort key used when trimming the report.
    max_entries: cap on entries kept in the report (0 = keep all).
    attach_to_metadata: when profiling via :meth:`profile_decision`,
        attach a compact summary to ``result.metadata["profile"]``
        unless the policy forbids it (strict privacy class).
    """

    def __init__(self, sort_by: str = "cumulative",
                 max_entries: int = 500,
                 attach_to_metadata: bool = True) -> None:
        if sort_by not in _SORT_KEYS:
            raise ProfilingError(
                f"unknown sort key {sort_by!r}; choose from "
                f"{sorted(_SORT_KEYS)}")
        if not isinstance(max_entries, int) or max_entries < 0:
            raise ProfilingError(
                f"max_entries must be a non-negative int, "
                f"got {max_entries!r}")
        self.sort_by = sort_by
        self.max_entries = max_entries
        self.attach_to_metadata = attach_to_metadata

    def profile_raw(self, fn: Callable[..., Any], *args: Any,
                    label: str = "", **kwargs: Any
                    ) -> tuple[Any, Any, float]:
        """Run ``fn`` under cProfile; return ``(result, pstats.Stats, wall_ms)``.

        The raw stats object feeds consumers that need the true call
        graph (e.g. :mod:`hugrgate.flame`); :meth:`profile` is the
        friendlier wrapper around this.
        """
        profiler = cProfile.Profile()
        start = time.perf_counter()
        profiler.enable()
        try:
            result = fn(*args, **kwargs)
        finally:
            profiler.disable()
        wall_ms = (time.perf_counter() - start) * 1000.0
        stats = pstats.Stats(profiler).sort_stats(self.sort_by)
        return result, stats, wall_ms

    def profile(self, fn: Callable[..., Any], *args: Any,
                label: str = "", **kwargs: Any) -> tuple[Any, ProfileReport]:
        """Run ``fn(*args, **kwargs)`` under cProfile.

        Returns ``(fn_result, report)``.  Exceptions from ``fn`` propagate
        unchanged — the report is discarded, the error is not swallowed.
        """
        result, stats, wall_ms = self.profile_raw(
            fn, *args, label=label, **kwargs)
        report = _stats_to_report(stats, wall_ms, label or fn.__name__)
        if self.max_entries and len(report.entries) > self.max_entries:
            report.entries = sorted(
                report.entries, key=lambda e: e.cumtime_ms,
                reverse=True)[:self.max_entries]
        return result, report

    def profile_decision(self, gate: Any, state: Mapping[str, Any],
                         spec: Any, policy: DecisionPolicy | None = None,
                         context: Mapping[str, Any] | None = None,
                         backend_name: str | None = None,
                         label: str = "decide"
                         ) -> tuple[Any, ProfileReport]:
        """Profile one :meth:`HugrGate.decide` call.

        The compact summary (top-10 by cumulative time) is attached to
        ``result.metadata["profile"]`` unless ``attach_to_metadata`` is
        False or the policy's ``privacy_class`` is ``"strict"`` — profile
        frames name backend internals, which strict privacy must not leak
        into records.
        """
        policy = policy or DecisionPolicy()
        result, report = self.profile(
            gate.decide, state, spec, policy, context, backend_name,
            label=label)
        if self.attach_to_metadata and policy.privacy_class != "strict":
            result.metadata["profile"] = {
                "wall_ms": report.wall_ms,
                "total_calls": report.total_calls,
                "top": [
                    {"function": e.function,
                     "cumtime_ms": round(e.cumtime_ms, 3),
                     "ncalls": e.ncalls}
                    for e in report.top(10)
                ],
            }
        else:
            logger.debug("profile summary withheld from metadata "
                         "(privacy_class=%s)", policy.privacy_class)
        return result, report


# --- lightweight nested regions ---------------------------------------------

_region_stack: list[dict[str, Any]] = []
_region_totals: dict[str, dict[str, float]] = {}


@contextmanager
def profile_region(name: str):
    """Time a named region; regions may nest.

    Cheaper than cProfile for coarse instrumentation.  Accumulated totals
    are readable via :func:`region_report` and reset by it.
    """
    if not name:
        raise ProfilingError("profile_region requires a non-empty name")
    frame: dict[str, Any] = {"name": name, "start": time.perf_counter(),
                             "child_ms": 0.0}
    _region_stack.append(frame)
    try:
        yield frame
    finally:
        elapsed_ms = (time.perf_counter() - frame["start"]) * 1000.0
        _region_stack.pop()
        own_ms = elapsed_ms - frame["child_ms"]
        totals = _region_totals.setdefault(
            name, {"calls": 0, "total_ms": 0.0, "own_ms": 0.0})
        totals["calls"] += 1
        totals["total_ms"] += elapsed_ms
        totals["own_ms"] += own_ms
        if _region_stack:
            _region_stack[-1]["child_ms"] += elapsed_ms


def region_report(reset: bool = True) -> dict[str, dict[str, float]]:
    """Return accumulated region totals; resets them by default."""
    report = {name: dict(totals)
              for name, totals in _region_totals.items()}
    if reset:
        _region_totals.clear()
    return report
