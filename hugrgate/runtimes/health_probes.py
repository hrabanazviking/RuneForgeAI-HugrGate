"""Model health probes. Slice 172.

:func:`probe_runtime` runs a battery of health probes against one
:class:`LocalRuntime` and returns a :class:`HealthReport`:

- :class:`LivenessProbe` — the runtime's own ``health()`` report
  (``ok``/``degraded``/``unavailable``);
- :class:`ModelLoadedProbe` — a model is actually resident;
- :class:`InferenceProbe` — a minimal real inference round-trip per
  advertised capability (catches engines that report healthy but are
  wedged);
- :class:`LatencyProbe` — one timed inference against warn/crit
  thresholds.

:func:`probe_all` fans out over a :class:`RuntimeRegistry`
(parallel, never raises — probe crashes are recorded as failed
results, not exceptions). Use with the warmup manager (169) for
bring-up and with the eviction policy (171) to shed unhealthy
residents.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import SpecError
from hugrgate.runtimes import (
    CAP_CLASSIFY,
    CAP_EMBED,
    CAP_GENERATE,
    GenerationOptions,
    LocalRuntime,
    RuntimeRegistry,
)

__all__ = [
    "HealthProbe",
    "HealthReport",
    "InferenceProbe",
    "LatencyProbe",
    "LivenessProbe",
    "ModelLoadedProbe",
    "ProbeResult",
    "probe_all",
    "probe_runtime",
]


@dataclass
class ProbeResult:
    """Outcome of one probe against one runtime."""

    probe: str
    runtime: str
    ok: bool
    latency_s: float = 0.0
    detail: str = ""
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe": self.probe,
            "runtime": self.runtime,
            "ok": self.ok,
            "latency_s": self.latency_s,
            "detail": self.detail,
        }


@dataclass
class HealthReport:
    """All probe results for one runtime."""

    runtime: str
    results: list[ProbeResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(r.ok for r in self.results)

    @property
    def failed(self) -> list[ProbeResult]:
        return [r for r in self.results if not r.ok]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "ok": self.ok,
            "results": [r.to_dict() for r in self.results],
        }


class HealthProbe(ABC):
    """One check against a runtime."""

    name: str = "probe"

    @abstractmethod
    def check(self, runtime: LocalRuntime) -> ProbeResult:
        """Run the probe; raise on failure (the runner records it)."""


class LivenessProbe(HealthProbe):
    """The runtime's own ``health()`` report."""

    name = "liveness"

    def check(self, runtime: LocalRuntime) -> ProbeResult:
        started = time.monotonic()
        report = runtime.health()
        status = str(report.get("status", "unknown"))
        ok = status == "ok"
        return ProbeResult(
            probe=self.name, runtime=runtime.name, ok=ok,
            latency_s=time.monotonic() - started,
            detail=f"status={status}" if not ok else "")


class ModelLoadedProbe(HealthProbe):
    """A model is actually resident in the runtime."""

    name = "model-loaded"

    def check(self, runtime: LocalRuntime) -> ProbeResult:
        model = runtime.info().model
        return ProbeResult(
            probe=self.name, runtime=runtime.name,
            ok=model is not None,
            detail="" if model else "no model loaded")


class InferenceProbe(HealthProbe):
    """A minimal real inference per advertised capability.

    Catches engines that report healthy but are wedged.
    """

    name = "inference"

    def check(self, runtime: LocalRuntime) -> ProbeResult:
        started = time.monotonic()
        caps = runtime.info().capabilities
        ran: list[str] = []
        if CAP_GENERATE in caps:
            runtime.generate("health probe",
                             GenerationOptions(max_tokens=1))
            ran.append("generate")
        if CAP_EMBED in caps:
            runtime.embed(["health probe"])
            ran.append("embed")
        if CAP_CLASSIFY in caps:
            runtime.classify(["health probe"], ["ok", "bad"])
            ran.append("classify")
        if not ran:
            return ProbeResult(
                probe=self.name, runtime=runtime.name, ok=False,
                latency_s=time.monotonic() - started,
                detail="runtime advertises no probed capabilities")
        return ProbeResult(
            probe=self.name, runtime=runtime.name, ok=True,
            latency_s=time.monotonic() - started,
            detail=f"ran: {', '.join(ran)}")


class LatencyProbe(HealthProbe):
    """One timed inference against warn/crit thresholds."""

    name = "latency"

    def __init__(self, warn_s: float = 5.0, crit_s: float = 30.0) -> None:
        if not 0 < warn_s <= crit_s:
            raise SpecError(
                f"need 0 < warn_s <= crit_s, got {warn_s}/{crit_s}")
        self.warn_s = warn_s
        self.crit_s = crit_s

    def check(self, runtime: LocalRuntime) -> ProbeResult:
        started = time.monotonic()
        caps = runtime.info().capabilities
        if CAP_GENERATE in caps:
            runtime.generate("health probe",
                             GenerationOptions(max_tokens=1))
        elif CAP_EMBED in caps:
            runtime.embed(["health probe"])
        else:
            return ProbeResult(
                probe=self.name, runtime=runtime.name, ok=False,
                detail="no generate/embed capability to time")
        elapsed = time.monotonic() - started
        if elapsed > self.crit_s:
            return ProbeResult(
                probe=self.name, runtime=runtime.name, ok=False,
                latency_s=elapsed,
                detail=f"{elapsed:.2f}s > crit {self.crit_s:.2f}s")
        detail = (f"{elapsed:.2f}s > warn {self.warn_s:.2f}s"
                  if elapsed > self.warn_s else "")
        return ProbeResult(
            probe=self.name, runtime=runtime.name, ok=True,
            latency_s=elapsed, detail=detail)


DEFAULT_PROBES: tuple[HealthProbe, ...] = (
    LivenessProbe(),
    ModelLoadedProbe(),
    InferenceProbe(),
    LatencyProbe(),
)


def probe_runtime(runtime: LocalRuntime,
                  probes: tuple[HealthProbe, ...] | None = None
                  ) -> HealthReport:
    """Run ``probes`` (default battery) against one runtime.

    Never raises: a crashing probe is recorded as a failed result.
    """
    probes = probes if probes is not None else DEFAULT_PROBES
    report = HealthReport(runtime=runtime.name)
    for probe in probes:
        try:
            report.results.append(probe.check(runtime))
        except Exception as e:  # noqa: BLE001 - probes must never raise
            report.results.append(ProbeResult(
                probe=probe.name, runtime=runtime.name, ok=False,
                detail=f"{type(e).__name__}: {e}"))
    return report


def probe_all(registry: RuntimeRegistry,
              probes: tuple[HealthProbe, ...] | None = None,
              max_workers: int = 4) -> list[HealthReport]:
    """Probe every runtime in ``registry`` (parallel, never raises)."""
    if max_workers < 1:
        raise SpecError(f"max_workers must be >= 1, got {max_workers}")
    runtimes: list[LocalRuntime] = []
    for name in registry.list():
        runtime = registry.get(name)
        if runtime is not None:
            runtimes.append(runtime)

    def _one(runtime: LocalRuntime) -> HealthReport:
        return probe_runtime(runtime, probes)

    if max_workers == 1 or len(runtimes) <= 1:
        return [_one(r) for r in runtimes]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(_one, runtimes))
