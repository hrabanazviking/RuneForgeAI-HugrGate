"""Model warmup manager. Slice 169.

:func:`WarmupManager` brings local runtimes to serving temperature:
load the model, run the runtime's own :meth:`warmup` hook, then a few
timed probe inferences to prime caches and establish a latency
baseline. Results are recorded as :class:`WarmupResult` — per-runtime
success, call count, and latency percentiles — and the manager is
idempotent (already-warm runtimes are skipped unless ``rewarm``).

:func:`WarmupManager.warmup_backend` covers the older
:class:`Backend` interface (its ``warmup()`` hook, slice 019), so one
manager warms the whole stack. Failures are recorded, never raised,
so a single cold model can't block a fleet warmup.
"""

from __future__ import annotations

import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import SpecError
from hugrgate.runtimes import (
    CAP_CLASSIFY,
    CAP_EMBED,
    CAP_GENERATE,
    GenerationOptions,
    LocalRuntime,
    ModelRef,
    RuntimeRegistry,
)

__all__ = [
    "WarmupManager",
    "WarmupResult",
]


@dataclass
class WarmupResult:
    """Outcome of warming one runtime (or backend)."""

    name: str
    model: str | None
    success: bool
    calls: int = 0
    latencies_s: list[float] = field(default_factory=list)
    error: str | None = None
    warmed_at: float = field(default_factory=time.time)

    @property
    def latency_p50_s(self) -> float | None:
        if not self.latencies_s:
            return None
        return statistics.median(self.latencies_s)

    @property
    def latency_p95_s(self) -> float | None:
        if not self.latencies_s:
            return None
        ordered = sorted(self.latencies_s)
        return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "success": self.success,
            "calls": self.calls,
            "latency_p50_s": self.latency_p50_s,
            "latency_p95_s": self.latency_p95_s,
            "error": self.error,
        }


class WarmupManager:
    """Warms local runtimes and legacy backends.

    Parameters
    ----------
    repeat: timed probe inferences per capability after the warmup hook.
    max_workers: parallelism for :meth:`warmup_all` (1 = sequential).
    """

    def __init__(self, repeat: int = 3, max_workers: int = 4) -> None:
        if repeat < 0:
            raise SpecError(f"repeat must be >= 0, got {repeat}")
        if max_workers < 1:
            raise SpecError(f"max_workers must be >= 1, got {max_workers}")
        self.repeat = repeat
        self.max_workers = max_workers
        self._warmed: set[str] = set()
        self._results: dict[str, WarmupResult] = {}
        self._lock = threading.RLock()

    @property
    def warmed(self) -> set[str]:
        with self._lock:
            return set(self._warmed)

    def last_result(self, name: str) -> WarmupResult | None:
        with self._lock:
            return self._results.get(name)

    def reset(self, name: str | None = None) -> None:
        """Forget warm state (all, or one runtime)."""
        with self._lock:
            if name is None:
                self._warmed.clear()
                self._results.clear()
            else:
                self._warmed.discard(name)
                self._results.pop(name, None)

    # -- runtimes ---------------------------------------------------------

    def warmup_runtime(self, runtime: LocalRuntime,
                       model: ModelRef | None = None,
                       rewarm: bool = False) -> WarmupResult:
        """Warm one runtime; idempotent unless ``rewarm``."""
        with self._lock:
            if not rewarm and runtime.name in self._warmed:
                cached = self._results.get(runtime.name)
                if cached is not None:
                    return cached
        latencies: list[float] = []
        calls = 0
        try:
            if model is not None:
                runtime.load(model)
            runtime.warmup()
            calls += 1
            caps = runtime.info().capabilities
            for _ in range(self.repeat):
                if CAP_GENERATE in caps:
                    started = time.monotonic()
                    runtime.generate(
                        "warmup", GenerationOptions(max_tokens=1))
                    latencies.append(time.monotonic() - started)
                    calls += 1
                if CAP_EMBED in caps:
                    started = time.monotonic()
                    runtime.embed(["warmup"])
                    latencies.append(time.monotonic() - started)
                    calls += 1
                if CAP_CLASSIFY in caps:
                    started = time.monotonic()
                    runtime.classify(["warmup"], ["warmup", "other"])
                    latencies.append(time.monotonic() - started)
                    calls += 1
            result = WarmupResult(
                name=runtime.name,
                model=(info.model.display if (info := runtime.info()).model
                       else None),
                success=True, calls=calls, latencies_s=latencies)
        except Exception as e:  # noqa: BLE001 - failures are recorded
            result = WarmupResult(
                name=runtime.name, model=None, success=False,
                calls=calls, latencies_s=latencies,
                error=f"{type(e).__name__}: {e}")
        with self._lock:
            self._results[runtime.name] = result
            if result.success:
                self._warmed.add(runtime.name)
            else:
                self._warmed.discard(runtime.name)
        return result

    def warmup_all(self, registry: RuntimeRegistry,
                   models: dict[str, ModelRef] | None = None,
                   rewarm: bool = False) -> list[WarmupResult]:
        """Warm every runtime in ``registry`` (parallel, never raises).

        ``models`` maps runtime names to models to load first.
        """
        models = models or {}
        runtimes: list[LocalRuntime] = []
        for name in registry.list():
            runtime = registry.get(name)
            if runtime is not None:
                runtimes.append(runtime)

        def _one(runtime: LocalRuntime) -> WarmupResult:
            return self.warmup_runtime(runtime, models.get(runtime.name),
                                       rewarm=rewarm)

        if self.max_workers == 1 or len(runtimes) <= 1:
            return [_one(r) for r in runtimes]
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            return list(pool.map(_one, runtimes))

    # -- legacy backends ----------------------------------------------------

    def warmup_backend(self, backend: Backend,
                       rewarm: bool = False) -> WarmupResult:
        """Warm a legacy :class:`Backend` via its ``warmup()`` hook."""
        with self._lock:
            if not rewarm and backend.name in self._warmed:
                cached = self._results.get(backend.name)
                if cached is not None:
                    return cached
        try:
            started = time.monotonic()
            backend.warmup()
            result = WarmupResult(
                name=backend.name, model=None, success=True, calls=1,
                latencies_s=[time.monotonic() - started])
        except Exception as e:  # noqa: BLE001 - failures are recorded
            result = WarmupResult(
                name=backend.name, model=None, success=False,
                error=f"{type(e).__name__}: {e}")
        with self._lock:
            self._results[backend.name] = result
            if result.success:
                self._warmed.add(backend.name)
            else:
                self._warmed.discard(backend.name)
        return result
