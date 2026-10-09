"""Model eviction policy. Slice 171.

When VRAM/RAM is finite, something must decide which resident models
leave. This module provides the decision layer over the slice-170
residency table:

- :class:`LRUPolicy` — evict least-recently-used idle residents;
- :class:`TTLPolicy` — evict residents older than a time-to-live;
- :class:`MemoryPressurePolicy` — while a memory reading is over a
  high watermark, nominate LRU-first candidates (one pass evicts;
  call :meth:`Evictor.run` again while
  :meth:`MemoryPressurePolicy.under_pressure` holds);
- :class:`CompositePolicy` — union of several policies, first
  nominator wins per runtime.

:class:`EvictionBudget` caps evictions per pass and protects named
runtimes. Entries with live leases (``refcount > 0``) are skipped
unless a policy opts into ``evict_in_use``. :class:`Evictor` applies
a policy to a :class:`ResidencyManager` and reports what left and
why.

Memory readings are injected callables (defaults: stdlib
:mod:`resource` RSS of this process on Unix). Real VRAM measurement
needs a provider hook — see the module docstring of each policy.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import SpecError
from hugrgate.runtimes.residency import ResidencyEntry, ResidencyManager

__all__ = [
    "CompositePolicy",
    "EvictionBudget",
    "EvictionDecision",
    "EvictionPolicy",
    "EvictionReport",
    "Evictor",
    "LRUPolicy",
    "MemoryPressurePolicy",
    "TTLPolicy",
]


@dataclass(frozen=True)
class EvictionBudget:
    """Per-pass limits for an eviction run."""

    max_to_evict: int | None = None
    protected: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.max_to_evict is not None and self.max_to_evict < 0:
            raise SpecError(
                f"max_to_evict must be >= 0, got {self.max_to_evict}")


@dataclass(frozen=True)
class EvictionDecision:
    """One nominated eviction: which runtime, and why."""

    runtime_name: str
    reason: str
    policy: str


@dataclass
class EvictionReport:
    """Outcome of one :meth:`Evictor.run` pass."""

    evicted: list[EvictionDecision] = field(default_factory=list)
    skipped_in_use: int = 0
    skipped_protected: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "evicted": [{"runtime": d.runtime_name, "reason": d.reason,
                         "policy": d.policy} for d in self.evicted],
            "skipped_in_use": self.skipped_in_use,
            "skipped_protected": self.skipped_protected,
        }


class EvictionPolicy(ABC):
    """Nominates resident runtimes for eviction, in priority order."""

    name: str = "policy"

    @abstractmethod
    def select(self, entries: list[ResidencyEntry],
               budget: EvictionBudget) -> list[EvictionDecision]:
        """Ordered eviction candidates (highest priority first)."""

    def _eligible(self, entries: list[ResidencyEntry],
                  budget: EvictionBudget, evict_in_use: bool
                  ) -> tuple[list[ResidencyEntry], int, int]:
        """Filter protected/in-use entries.

        Returns ``(eligible, skipped_in_use, skipped_protected)``.
        """
        eligible: list[ResidencyEntry] = []
        skipped_in_use = 0
        skipped_protected = 0
        for entry in entries:
            if entry.runtime_name in budget.protected:
                skipped_protected += 1
                continue
            if entry.refcount > 0 and not evict_in_use:
                skipped_in_use += 1
                continue
            eligible.append(entry)
        return eligible, skipped_in_use, skipped_protected


class LRUPolicy(EvictionPolicy):
    """Evict residents idle longer than ``max_idle_s``, oldest first."""

    name = "lru"

    def __init__(self, max_idle_s: float,
                 evict_in_use: bool = False) -> None:
        if max_idle_s < 0:
            raise SpecError(f"max_idle_s must be >= 0, got {max_idle_s}")
        self.max_idle_s = max_idle_s
        self.evict_in_use = evict_in_use

    def select(self, entries: list[ResidencyEntry],
               budget: EvictionBudget) -> list[EvictionDecision]:
        now = time.time()
        eligible, _, _ = self._eligible(entries, budget, self.evict_in_use)
        idle = [e for e in eligible
                if now - e.last_used_at > self.max_idle_s]
        idle.sort(key=lambda e: e.last_used_at)
        return [EvictionDecision(
            runtime_name=e.runtime_name, policy=self.name,
            reason=f"idle {now - e.last_used_at:.0f}s "
                   f"> {self.max_idle_s:.0f}s")
            for e in idle]


class TTLPolicy(EvictionPolicy):
    """Evict residents older than ``ttl_s`` since acquisition."""

    name = "ttl"

    def __init__(self, ttl_s: float, evict_in_use: bool = False) -> None:
        if ttl_s < 0:
            raise SpecError(f"ttl_s must be >= 0, got {ttl_s}")
        self.ttl_s = ttl_s
        self.evict_in_use = evict_in_use

    def select(self, entries: list[ResidencyEntry],
               budget: EvictionBudget) -> list[EvictionDecision]:
        now = time.time()
        eligible, _, _ = self._eligible(entries, budget, self.evict_in_use)
        old = [e for e in eligible if now - e.acquired_at > self.ttl_s]
        old.sort(key=lambda e: e.acquired_at)
        return [EvictionDecision(
            runtime_name=e.runtime_name, policy=self.name,
            reason=f"age {now - e.acquired_at:.0f}s > {self.ttl_s:.0f}s")
            for e in old]


def _process_rss_bytes() -> int:
    """Current-process RSS via stdlib :mod:`resource` (Unix).

    This is a *process* memory reading, not VRAM. Real GPU memory
    needs a provider hook (e.g. ``torch.cuda.memory_allocated`` or
    NVML) passed as ``used_bytes_fn``.
    """
    try:
        import resource
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes. Heuristic: values
        # below 10**9 can't be bytes for a live process.
        return rss_kb * 1024 if rss_kb < 10**9 else rss_kb
    except Exception:  # noqa: BLE001 - non-Unix: report 0, policy rests
        return 0


class MemoryPressurePolicy(EvictionPolicy):
    """While memory is over the high watermark, nominate LRU-first.

    One :meth:`Evictor.run` pass evicts the nominated candidates;
    repeat while :meth:`under_pressure` holds. ``used_bytes_fn``
    defaults to process RSS (:func:`_process_rss_bytes`); pass a
    provider hook (NVML, ``torch.cuda``) for real VRAM accounting.
    """

    name = "memory-pressure"

    def __init__(self, high_watermark_bytes: int,
                 used_bytes_fn: Callable[[], int] | None = None,
                 evict_in_use: bool = False) -> None:
        if high_watermark_bytes <= 0:
            raise SpecError("high_watermark_bytes must be > 0, "
                            f"got {high_watermark_bytes}")
        self.high_watermark_bytes = high_watermark_bytes
        self.used_bytes_fn = used_bytes_fn or _process_rss_bytes
        self.evict_in_use = evict_in_use

    def under_pressure(self) -> bool:
        return self.used_bytes_fn() > self.high_watermark_bytes

    def select(self, entries: list[ResidencyEntry],
               budget: EvictionBudget) -> list[EvictionDecision]:
        if not self.under_pressure():
            return []
        eligible, _, _ = self._eligible(entries, budget, self.evict_in_use)
        eligible.sort(key=lambda e: e.last_used_at)
        used = self.used_bytes_fn()
        return [EvictionDecision(
            runtime_name=e.runtime_name, policy=self.name,
            reason=f"memory {used}B > watermark "
                   f"{self.high_watermark_bytes}B; LRU order")
            for e in eligible]


class CompositePolicy(EvictionPolicy):
    """Union of policies; first nominator wins per runtime."""

    name = "composite"

    def __init__(self, *policies: EvictionPolicy) -> None:
        if not policies:
            raise SpecError("CompositePolicy needs at least one policy")
        self.policies = policies

    def select(self, entries: list[ResidencyEntry],
               budget: EvictionBudget) -> list[EvictionDecision]:
        seen: set[str] = set()
        decisions: list[EvictionDecision] = []
        for policy in self.policies:
            for decision in policy.select(entries, budget):
                if decision.runtime_name not in seen:
                    seen.add(decision.runtime_name)
                    decisions.append(decision)
        return decisions


class Evictor:
    """Applies an :class:`EvictionPolicy` to a residency manager."""

    def __init__(self, manager: ResidencyManager,
                 policy: EvictionPolicy) -> None:
        self.manager = manager
        self.policy = policy

    def run(self, budget: EvictionBudget | None = None) -> EvictionReport:
        """One eviction pass: select, evict up to budget, report."""
        budget = budget or EvictionBudget()
        entries = list(self.manager.snapshot().values())
        decisions = self.policy.select(entries, budget)
        if budget.max_to_evict is not None:
            decisions = decisions[:budget.max_to_evict]
        report = EvictionReport()
        for decision in decisions:
            if decision.runtime_name in budget.protected:
                report.skipped_protected += 1
                continue
            evicted = self.manager.evict(decision.runtime_name)
            if evicted is None:
                continue  # raced away; not an error
            report.evicted.append(decision)
        # Skip accounting, policy-agnostic: protected entries always
        # count as protected; leased entries that survived the pass
        # count as in-use.
        evicted_names = {d.runtime_name for d in report.evicted}
        for entry in entries:
            if entry.runtime_name in budget.protected:
                report.skipped_protected += 1
            elif (entry.refcount > 0
                  and entry.runtime_name not in evicted_names):
                report.skipped_in_use += 1
        return report
