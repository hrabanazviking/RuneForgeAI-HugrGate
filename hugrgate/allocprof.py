"""Allocation profiling — tracemalloc integration for decisions. Slice 279.

Time profiles (slices 276-278) say *where the clock goes*; this module
says *where the bytes go*:

- :class:`AllocationProfiler` wraps :mod:`tracemalloc` with a
  HugrGate-shaped API: :meth:`AllocationProfiler.track` snapshots
  allocations inside a region, :meth:`profile_decision` diffs the heap
  across one :meth:`HugrGate.decide` call.
- :class:`AllocationReport` ranks allocation sites
  (``filename:lineno``) by bytes and block count, with before/after
  totals.
- Privacy: allocation *sites* are code locations, not values, but a
  site's frame can still name backend internals.  Under a strict policy
  only aggregate totals are attached to ``result.metadata``; the full
  site list stays local to the caller.
- Errors: misuse (bad ``nframes``/``top_n``, tracking without
  :mod:`tracemalloc` started) raises :class:`ProfilingError` — the
  slice-276 taxonomy error, reused per the Anti-Checkbox Rule.
"""

from __future__ import annotations

import tracemalloc
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import ProfilingError
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy

logger = get_logger(__name__)

__all__ = [
    "AllocationProfiler",
    "AllocationReport",
    "AllocationSite",
]

#: tracemalloc traceback depth bounds.
_MIN_NFRAMES = 1
_MAX_NFRAMES = 256


class _TrackCarrier:
    """Carrier for :meth:`AllocationProfiler.track` — holds ``report``."""

    def __init__(self) -> None:
        self.report: AllocationReport | None = None


@dataclass
class AllocationSite:
    """One ranked allocation site."""
    location: str      # "filename:lineno" of the allocating frame
    size_bytes: int    # bytes attributed to this site in the diff
    count: int         # blocks attributed to this site in the diff

    @property
    def size_kb(self) -> float:
        return self.size_bytes / 1024.0


@dataclass
class AllocationReport:
    """Outcome of one allocation-tracked region."""
    label: str
    before_bytes: int
    after_bytes: int
    sites: list[AllocationSite] = field(default_factory=list)

    @property
    def delta_bytes(self) -> int:
        return self.after_bytes - self.before_bytes

    @property
    def delta_kb(self) -> float:
        return self.delta_bytes / 1024.0

    def top(self, n: int = 10) -> list[AllocationSite]:
        if n < 1:
            raise ProfilingError(f"top(n) requires n >= 1, got {n}")
        return sorted(self.sites, key=lambda s: s.size_bytes,
                      reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "before_bytes": self.before_bytes,
            "after_bytes": self.after_bytes,
            "delta_bytes": self.delta_bytes,
            "sites": [
                {"location": s.location, "size_bytes": s.size_bytes,
                 "count": s.count}
                for s in self.sites
            ],
        }

    def to_markdown(self, n: int = 15) -> str:
        lines = [
            f"## Allocations: {self.label or 'run'}",
            f"heap {self.before_bytes} -> {self.after_bytes} bytes "
            f"(delta {self.delta_bytes:+d})",
            "",
            "| site | bytes | blocks |",
            "|---|---|---|",
        ]
        for s in self.top(n):
            lines.append(f"| `{s.location}` | {s.size_bytes} | {s.count} |")
        return "\n".join(lines)


def _site_location(trace: tracemalloc.Trace) -> str:
    # Attribute to the outermost user frame (last in the traceback),
    # which is the call site that triggered the allocation chain.
    frame = trace.traceback[-1]
    filename = frame.filename.rsplit("/", 1)[-1]
    return f"{filename}:{frame.lineno}"


class AllocationProfiler:
    """Track Python heap allocations with :mod:`tracemalloc`.

    Parameters
    ----------
    nframes: traceback depth captured per block (1-256).
    top_n: cap on sites kept per report (0 = keep all).
    attach_to_metadata: attach aggregate totals to
        ``result.metadata["allocations"]`` in :meth:`profile_decision`
        unless the policy is strict-privacy.
    """

    def __init__(self, nframes: int = 8, top_n: int = 200,
                 attach_to_metadata: bool = True) -> None:
        if not isinstance(nframes, int) or not (
                _MIN_NFRAMES <= nframes <= _MAX_NFRAMES):
            raise ProfilingError(
                f"nframes must be an int in [{_MIN_NFRAMES}, "
                f"{_MAX_NFRAMES}], got {nframes!r}")
        if not isinstance(top_n, int) or top_n < 0:
            raise ProfilingError(
                f"top_n must be a non-negative int, got {top_n!r}")
        self.nframes = nframes
        self.top_n = top_n
        self.attach_to_metadata = attach_to_metadata
        self._started_here = False

    # -- lifecycle ------------------------------------------------------

    def start(self) -> None:
        """Start tracemalloc if it is not already running."""
        if not tracemalloc.is_tracing():
            tracemalloc.start(self.nframes)
            self._started_here = True

    def stop(self) -> None:
        """Stop tracemalloc only if this profiler started it."""
        if self._started_here and tracemalloc.is_tracing():
            tracemalloc.stop()
            self._started_here = False

    def _require_tracing(self) -> None:
        if not tracemalloc.is_tracing():
            raise ProfilingError(
                "tracemalloc is not tracing; call start() (or use the "
                "track() context manager) before taking snapshots")

    # -- tracking -------------------------------------------------------

    @contextmanager
    def track(self, label: str = ""):
        """Context manager: diff the heap across the enclosed region.

        Yields a carrier whose ``report`` attribute holds the
        :class:`AllocationReport` after the block exits::

            with profiler.track("ingest") as tracked:
                ingest(data)
            print(tracked.report.delta_kb)
        """
        carrier = _TrackCarrier()
        self.start()
        try:
            before = tracemalloc.take_snapshot()
            before_total = sum(s.size for s in before.statistics("filename"))
            yield carrier
            after = tracemalloc.take_snapshot()
            after_total = sum(s.size for s in after.statistics("filename"))
            carrier.report = self._diff_to_report(
                before, after, before_total, after_total, label)
        finally:
            self.stop()

    def _diff_to_report(self, before: tracemalloc.Snapshot,
                        after: tracemalloc.Snapshot,
                        before_total: int, after_total: int,
                        label: str) -> AllocationReport:
        grouped: dict[str, AllocationSite] = {}
        for trace in after.compare_to(before, "traceback"):
            size_diff, count_diff = trace.size_diff, trace.count_diff
            if size_diff <= 0:
                continue
            loc = _site_location(trace)
            site = grouped.get(loc)
            if site is None:
                site = grouped[loc] = AllocationSite(
                    location=loc, size_bytes=0, count=0)
            site.size_bytes += size_diff
            site.count += count_diff
        sites = sorted(grouped.values(),
                       key=lambda s: s.size_bytes, reverse=True)
        if self.top_n:
            sites = sites[:self.top_n]
        return AllocationReport(label=label, before_bytes=before_total,
                                after_bytes=after_total, sites=sites)

    def snapshot_report(self, label: str = "") -> AllocationReport:
        """Take a single snapshot and report current heap by site.

        Useful for leak checks: compare two ``snapshot_report`` calls.
        """
        self._require_tracing()
        snapshot = tracemalloc.take_snapshot()
        total = 0
        grouped: dict[str, AllocationSite] = {}
        # statistics("traceback") groups by full traceback; attribute each
        # group to the outermost frame (the allocating call site).
        for stat in snapshot.statistics("traceback"):
            total += stat.size
            frame = stat.traceback[-1]
            loc = f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}"
            site = grouped.get(loc)
            if site is None:
                site = grouped[loc] = AllocationSite(
                    location=loc, size_bytes=0, count=0)
            site.size_bytes += stat.size
            site.count += stat.count
        sites = sorted(grouped.values(),
                       key=lambda s: s.size_bytes, reverse=True)
        if self.top_n:
            sites = sites[:self.top_n]
        return AllocationReport(label=label, before_bytes=0,
                                after_bytes=total, sites=sites)

    def profile_decision(self, gate: Any, state: Mapping[str, Any],
                         spec: Any, policy: DecisionPolicy | None = None,
                         context: Mapping[str, Any] | None = None,
                         backend_name: str | None = None,
                         label: str = "decide"
                         ) -> tuple[Any, AllocationReport]:
        """Diff the heap across one :meth:`HugrGate.decide` call."""
        policy = policy or DecisionPolicy()
        self.start()
        try:
            before = tracemalloc.take_snapshot()
            before_total = sum(s.size for s in before.statistics("filename"))
            result = gate.decide(state, spec, policy, context, backend_name)
            after = tracemalloc.take_snapshot()
            after_total = sum(s.size for s in after.statistics("filename"))
        finally:
            self.stop()
        report = self._diff_to_report(before, after, before_total,
                                      after_total, label)
        if self.attach_to_metadata and policy.privacy_class != "strict":
            result.metadata["allocations"] = {
                "delta_bytes": report.delta_bytes,
                "after_bytes": report.after_bytes,
                "top_sites": [
                    {"location": s.location, "size_bytes": s.size_bytes}
                    for s in report.top(5)
                ],
            }
        else:
            logger.debug("allocation summary withheld from metadata "
                         "(privacy_class=%s)", policy.privacy_class)
        return result, report
