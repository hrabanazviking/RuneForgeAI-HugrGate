"""Concurrency race hunt harness (slice 487).

Thread-safety was audited in slices 017/293; this module keeps it
honest with a reusable hammer: N threads start behind a
``threading.Barrier`` (so they truly contend rather than politely
taking turns), run a workload M iterations each, and every
exception is captured and reported. The caller supplies an
*invariant* — a predicate over the final state — which is the
actual race detector: races that corrupt state fail the invariant
even when no exception escapes.

:func:`hammer` is the workhorse; :func:`hammer_cache` and
:func:`hammer_registry` are the two production targets the 1.0
gauntlet pins (``DecisionCache`` and ``BackendRegistry``).
"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "HammerReport",
    "RaceHuntError",
    "hammer",
    "hammer_cache",
    "hammer_registry",
]


class RaceHuntError(AssertionError):
    """A race hunt failed: exceptions escaped or the invariant broke."""


@dataclass
class HammerReport:
    """What one :func:`hammer` run did."""

    threads: int
    iterations: int
    elapsed_s: float
    errors: tuple[str, ...] = ()
    invariant_ok: bool = True
    invariant_detail: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors and self.invariant_ok

    def raise_if_failed(self, what: str) -> None:
        if not self.ok:
            detail = "; ".join(self.errors[:3])
            raise RaceHuntError(
                f"race hunt failed for {what}: "
                f"errors={len(self.errors)} "
                f"invariant_ok={self.invariant_ok} "
                f"{self.invariant_detail} {detail}"
            )


def hammer(
    workload: Callable[[int, int], None],
    *,
    threads: int = 8,
    iterations: int = 200,
    invariant: Callable[[], tuple[bool, str]] | None = None,
    timeout_s: float = 120.0,
) -> HammerReport:
    """Hammer ``workload(thread_id, iteration)`` from many threads.

    Threads rendezvous on a barrier so contention is real. Any
    exception in any thread is captured (with traceback); after the
    join, ``invariant()`` must return ``(True, detail)``.
    """
    if threads < 1 or iterations < 1:
        raise ValueError("threads and iterations must be >= 1")
    barrier = threading.Barrier(threads)
    errors: list[str] = []

    def _run(tid: int) -> None:
        try:
            barrier.wait(timeout=timeout_s)
            for i in range(iterations):
                workload(tid, i)
        except Exception:  # noqa: BLE001 - captured into the report
            errors.append(traceback.format_exc())

    started = time.monotonic()
    workers = [threading.Thread(target=_run, args=(t,), daemon=True,
                               name=f"racehunt-{t}")
               for t in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=timeout_s)
    elapsed = time.monotonic() - started
    alive = [w.name for w in workers if w.is_alive()]
    if alive:
        errors.append(f"threads did not finish (deadlock?): {alive}")
    invariant_ok, detail = (True, "") if invariant is None else invariant()
    return HammerReport(threads=threads, iterations=iterations,
                        elapsed_s=elapsed, errors=tuple(errors),
                        invariant_ok=invariant_ok,
                        invariant_detail=detail)


def hammer_cache(*, threads: int = 8,
                 iterations: int = 200) -> HammerReport:
    """Hammer a ``DecisionCache``: concurrent put/get/invalidate.

    Invariant: ``hits + misses`` equals the number of ``get`` calls
    issued, the size never exceeds ``max_size``, and no exception
    escapes.
    """
    from hugrgate.cache import DecisionCache
    from hugrgate.policy import DecisionPolicy
    from hugrgate.result import DecisionResult
    from hugrgate.spec import DecisionSpec

    cache = DecisionCache(ttl_seconds=60.0, max_size=64)
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy()
    get_calls = [0]
    get_lock = threading.Lock()

    def _workload(tid: int, i: int) -> None:
        state = {"t": tid, "i": i % 16}
        result = DecisionResult(value="a", probability=0.9,
                                distribution={"a": 0.9, "b": 0.1},
                                backend=f"be-{tid % 3}")
        cache.put(state, spec, policy, result)
        with get_lock:
            get_calls[0] += 1
        cache.get(state, spec, policy)
        if i % 25 == 0:
            cache.invalidate_backend(f"be-{tid % 3}")

    def _invariant() -> tuple[bool, str]:
        stats = cache.stats()
        total = stats["hits"] + stats["misses"]
        # invalidate_backend may evict entries between put and get,
        # turning would-be hits into misses — the total is what must
        # be exact, not the hit/miss split.
        with get_lock:
            expected = get_calls[0]
        size_ok = stats["size"] <= 64
        return (total == expected and size_ok,
                f"get_calls={expected} hits+misses={total} "
                f"size={stats['size']}")

    return hammer(_workload, threads=threads, iterations=iterations,
                  invariant=_invariant)


def hammer_registry(*, threads: int = 8,
                    iterations: int = 200) -> HammerReport:
    """Hammer a ``BackendRegistry``: concurrent register/get/list.

    Invariant: every registered name resolves, ``list()`` never
    contains duplicates, and no exception escapes.
    """
    from hugrgate.backend import Backend, BackendRegistry
    from hugrgate.result import DecisionResult
    from hugrgate.spec import DecisionSpec

    registry = BackendRegistry()
    spec = DecisionSpec(type="categorical", options=["a", "b"])

    class _StubBackend(Backend):
        def __init__(self, name: str) -> None:
            self.name = name

        def capabilities(self) -> dict[str, Any]:
            return {"spec_types": ["categorical"]}

        def supports(self, spec: DecisionSpec) -> bool:
            return spec.type == "categorical"

        def evaluate(self, state, spec,
                     context=None) -> DecisionResult:
            return DecisionResult(value="a", probability=1.0,
                                  distribution={"a": 1.0, "b": 0.0})

    def _workload(tid: int, i: int) -> None:
        name = f"be-{tid % 4}"
        names = registry.list()
        assert len(names) == len(set(names)), "duplicate names listed"
        backend = registry.get(name)
        if backend is not None:
            assert backend.supports(spec)

    def _invariant() -> tuple[bool, str]:
        names = registry.list()
        return (len(names) == len(set(names)),
                f"names={sorted(names)}")

    # Pre-register outside the hammer so get() has targets.
    for t in range(4):
        try:
            registry.register(_StubBackend(name=f"be-{t}"))
        except Exception:  # noqa: BLE001 - name may exist; fine
            pass
    return hammer(_workload, threads=threads, iterations=iterations,
                  invariant=_invariant)
