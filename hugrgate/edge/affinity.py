"""CPU affinity controls for edge inference. Slice 179.

:class:`AffinityController` pins the inference process to a chosen CPU
set so real-time-ish decision loops stop fighting the watchdog, the
telemetry sampler, and the OS on small ARM boards. Everything that
touches the OS is injected (``os_funcs``) or guarded by
``dry_run=True``, so the full policy logic is testable on any host;
the only untestable part is the syscall itself, which is clearly
isolated in :meth:`AffinityController._sys_set_affinity`.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from hugrgate.errors import HugrGateError

__all__ = [
    "PROFILES",
    "AffinityController",
    "EdgeAffinityError",
    "parse_cpu_list",
    "pin_callable",
]

#: Named pinning profiles.
PROFILES: dict[str, str] = {
    "full": "all available CPUs",
    "inference": "all CPUs except core 0 (left for OS/watchdog)",
    "isolated": "highest-numbered CPU only (maximum isolation)",
}


class EdgeAffinityError(HugrGateError):
    """An affinity request was invalid or the OS refused it."""


def parse_cpu_list(spec: str) -> frozenset[int]:
    """Parse ``"0-3,5"``-style CPU lists into a frozenset of ints.

    Raises :class:`EdgeAffinityError` on empty specs, negative ids,
    reversed ranges, or non-numeric tokens. Duplicates are collapsed.
    """
    cpus: set[int] = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            raise EdgeAffinityError(
                f"empty token in CPU list {spec!r}")
        if "-" in token:
            parts = token.split("-")
            if len(parts) != 2:
                raise EdgeAffinityError(
                    f"bad range {token!r} in CPU list {spec!r}")
            try:
                lo, hi = int(parts[0]), int(parts[1])
            except ValueError:
                raise EdgeAffinityError(
                    f"non-numeric range {token!r} in CPU list {spec!r}"
                ) from None
            if lo < 0 or hi < 0:
                raise EdgeAffinityError(
                    f"negative CPU id in {token!r}")
            if lo > hi:
                raise EdgeAffinityError(
                    f"reversed range {token!r} in CPU list {spec!r}")
            cpus.update(range(lo, hi + 1))
        else:
            try:
                cpu = int(token)
            except ValueError:
                raise EdgeAffinityError(
                    f"non-numeric CPU id {token!r} in CPU list {spec!r}"
                ) from None
            if cpu < 0:
                raise EdgeAffinityError(
                    f"negative CPU id {token!r}")
            cpus.add(cpu)
    if not cpus:
        raise EdgeAffinityError(f"CPU list {spec!r} selects no CPUs")
    return frozenset(cpus)


class _OsFuncs:
    """The OS surface AffinityController needs; replaceable in tests."""

    def cpu_count(self) -> int | None:
        return os.cpu_count()

    def sched_affinity(self, pid: int) -> frozenset[int]:
        if not hasattr(os, "sched_getaffinity"):
            raise EdgeAffinityError(
                "os.sched_getaffinity unavailable on this platform")
        return frozenset(os.sched_getaffinity(pid))

    def set_affinity(self, pid: int, cpus: frozenset[int]) -> None:
        if not hasattr(os, "sched_setaffinity"):
            raise EdgeAffinityError(
                "os.sched_setaffinity unavailable on this platform")
        os.sched_setaffinity(pid, set(cpus))


class AffinityController:
    """Owns CPU pinning policy for the edge runtime process."""

    def __init__(self, os_funcs: _OsFuncs | None = None,
                 dry_run: bool = False):
        self._os = os_funcs or _OsFuncs()
        self._dry_run = dry_run
        self._lock = threading.RLock()
        self._requested: frozenset[int] | None = None
        self._applied: frozenset[int] | None = None
        self._ceiling_cpus: frozenset[int] | None = None

    # -- introspection -----------------------------------------------------

    def available_cpus(self) -> frozenset[int]:
        """CPUs the OS currently allows this process to run on."""
        try:
            return self._os.sched_affinity(0)
        except EdgeAffinityError:
            count = self._os.cpu_count() or 1
            return frozenset(range(count))

    def _ceiling(self) -> frozenset[int]:
        """The widest CPU set this controller may ever request.

        Captured once, before any pinning narrows the transient mask:
        ``sched_getaffinity`` reflects the *current* mask, while the
        kernel permits restoring any subset of the cgroup/cpuset
        ceiling. Validating against the transient mask would make
        ``pinned()`` unable to restore its own previous set.
        """
        with self._lock:
            if self._ceiling_cpus is None:
                try:
                    self._ceiling_cpus = self._os.sched_affinity(0)
                except EdgeAffinityError:
                    count = self._os.cpu_count() or 1
                    self._ceiling_cpus = frozenset(range(count))
            return self._ceiling_cpus

    # -- policy -------------------------------------------------------------

    def validate(self, cpus: frozenset[int]) -> frozenset[int]:
        """Reject empty sets and CPUs outside the captured ceiling."""
        if not cpus:
            raise EdgeAffinityError("affinity set must not be empty")
        ceiling = self._ceiling()
        unknown = set(cpus) - set(ceiling)
        if unknown:
            raise EdgeAffinityError(
                f"CPUs {sorted(unknown)} not in available set "
                f"{sorted(ceiling)}")
        return cpus

    def profile_cpus(self, name: str) -> frozenset[int]:
        """Resolve a named :data:`PROFILES` profile against this host."""
        if name not in PROFILES:
            raise EdgeAffinityError(
                f"unknown affinity profile {name!r}; known: "
                f"{sorted(PROFILES)}")
        available = sorted(self.available_cpus())
        if name == "full":
            return frozenset(available)
        if name == "inference":
            return frozenset(available[1:] or available)
        return frozenset([available[-1]])  # isolated

    # -- actuation -----------------------------------------------------------

    def set_affinity(self, cpus: frozenset[int] | str) -> frozenset[int]:
        """Validate and apply a CPU set; returns the applied set.

        In ``dry_run`` mode nothing touches the OS — the request is
        recorded and returned so policy code paths stay testable.
        """
        if isinstance(cpus, str):
            cpus = parse_cpu_list(cpus)
        cpus = self.validate(cpus)
        with self._lock:
            if not self._dry_run:
                try:
                    self._os.set_affinity(0, cpus)
                except OSError as e:
                    raise EdgeAffinityError(
                        f"OS refused affinity {sorted(cpus)}: {e}") from e
                self._applied = frozenset(self._os.sched_affinity(0))
            else:
                self._applied = cpus
            self._requested = cpus
            return self._applied

    def current(self) -> frozenset[int] | None:
        """The last set this controller applied (None if never)."""
        with self._lock:
            return self._applied

    @contextmanager
    def pinned(self, cpus: frozenset[int] | str) -> Iterator[frozenset[int]]:
        """Pin for the duration of the block, then restore.

        If the controller never applied a set before, restores to the
        full available set. The previous set is restored even when the
        block raises; a restore failure is raised (silently dropping a
        pin would lie about isolation).
        """
        previous = self.current() or self.available_cpus()
        applied = self.set_affinity(cpus)
        try:
            yield applied
        finally:
            self.set_affinity(previous)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "dry_run": self._dry_run,
                "requested": sorted(self._requested)
                if self._requested else None,
                "applied": sorted(self._applied)
                if self._applied else None,
                "available": sorted(self.available_cpus()),
            }


def pin_callable(fn: Callable[..., Any], cpus: frozenset[int] | str,
                 controller: AffinityController | None = None) -> Any:
    """Run ``fn()`` pinned to ``cpus``, restoring affinity after."""
    controller = controller or AffinityController()
    with controller.pinned(cpus):
        return fn()
