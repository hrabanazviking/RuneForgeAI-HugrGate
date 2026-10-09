"""Offline-first bootstrap for edge deployment. Slice 192.

:class:`BootstrapPlan` is an ordered list of :class:`BootstrapStep`s
that bring an edge node from cold storage to serving decisions. The
offline-first law is structural, not advisory:

- every step declares ``requires_network``;
- :meth:`BootstrapPlan.validate_offline` raises
  :class:`OfflineBootstrapError` naming any step that needs the
  network — a plan that phones home cannot bootstrap a node that has
  no link;
- :meth:`BootstrapPlan.run` executes steps in order against a shared
  :class:`BootstrapContext`, records per-step outcomes, and aborts on
  the first *critical* failure (non-critical failures are recorded
  and skipped past).

:func:`default_edge_plan` wires the real Campaign VIII components
(platform audit → Pi baseline → memory → wear store → NPU registry →
residency → cache → thermal governor) into one validated plan.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.edge.cachetune import EdgeCache
from hugrgate.edge.memory import MemoryManager
from hugrgate.edge.npu import NPURegistry
from hugrgate.edge.platform import (
    PlatformProbe,
    audit_arm64,
    detect_pi_board,
    pi_baseline,
)
from hugrgate.edge.residency import ResidencyManager
from hugrgate.edge.storage import WearAwareStore
from hugrgate.edge.thermal import SysfsThermalSensor, ThermalGovernor
from hugrgate.errors import HugrGateError

__all__ = [
    "BootstrapContext",
    "BootstrapPlan",
    "BootstrapStep",
    "OfflineBootstrapError",
    "StepOutcome",
    "default_edge_plan",
]


class OfflineBootstrapError(HugrGateError):
    """A bootstrap plan violates the offline-first law."""


@dataclass(frozen=True)
class BootstrapStep:
    """One bootstrap action."""

    name: str
    action: Callable[[BootstrapContext], None]
    requires_network: bool = False
    critical: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise OfflineBootstrapError("step name must be non-empty")


@dataclass
class StepOutcome:
    """What happened when a step ran."""

    name: str
    status: str  # "ok" | "failed" | "skipped"
    detail: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status,
                "detail": self.detail, "duration_s": self.duration_s}


class BootstrapContext:
    """Shared mutable state threaded through bootstrap steps."""

    def __init__(self):
        self._lock = threading.RLock()
        self.values: dict[str, Any] = {}
        self.artifacts: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self.values[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.values.get(key, default)

    def record_artifact(self, key: str, artifact: Any) -> None:
        """Artifacts survive into the completion report (slice 200)."""
        with self._lock:
            self.artifacts[key] = artifact


class BootstrapPlan:
    """An ordered, offline-validated bootstrap sequence."""

    def __init__(self, steps: list[BootstrapStep] | None = None):
        self._steps: list[BootstrapStep] = list(steps or [])
        self._lock = threading.RLock()
        self._outcomes: list[StepOutcome] = []

    def add(self, step: BootstrapStep) -> BootstrapPlan:
        with self._lock:
            if any(s.name == step.name for s in self._steps):
                raise OfflineBootstrapError(
                    f"duplicate bootstrap step {step.name!r}")
            self._steps.append(step)
        return self

    @property
    def steps(self) -> list[BootstrapStep]:
        with self._lock:
            return list(self._steps)

    def validate_offline(self) -> None:
        """Raise if any step requires the network."""
        offenders = [s.name for s in self.steps if s.requires_network]
        if offenders:
            raise OfflineBootstrapError(
                "offline-first violation: these bootstrap steps require "
                f"the network: {offenders}; remove them or gate them "
                f"behind post-bootstrap")

    def run(self, context: BootstrapContext | None = None, *,
            dry_run: bool = False) -> list[StepOutcome]:
        """Validate, then execute in order. Returns per-step outcomes.

        ``dry_run=True`` validates and records every step as
        ``"skipped"`` without executing actions. A critical failure
        aborts the run; later steps are recorded as ``"skipped"``.
        """
        self.validate_offline()
        context = context or BootstrapContext()
        outcomes: list[StepOutcome] = []
        aborted = False
        for step in self.steps:
            if aborted:
                outcomes.append(StepOutcome(step.name, "skipped",
                                            "aborted by earlier failure"))
                continue
            if dry_run:
                outcomes.append(StepOutcome(step.name, "skipped",
                                            "dry run"))
                continue
            start = time.monotonic()
            try:
                step.action(context)
            except Exception as e:  # noqa: BLE001 - recorded, not raised
                duration = time.monotonic() - start
                outcomes.append(StepOutcome(
                    step.name, "failed",
                    f"{type(e).__name__}: {e}", duration))
                if step.critical:
                    aborted = True
            else:
                duration = time.monotonic() - start
                outcomes.append(StepOutcome(step.name, "ok", "",
                                            duration))
        with self._lock:
            self._outcomes = outcomes
        return list(outcomes)

    def last_outcomes(self) -> list[StepOutcome]:
        with self._lock:
            return list(self._outcomes)

    def succeeded(self) -> bool:
        """True when the last run had no failures and wasn't empty."""
        with self._lock:
            return bool(self._outcomes) and all(
                o.status == "ok" for o in self._outcomes)


def default_edge_plan(store_dir: str = "edge-store",
                      write_budget_bytes: int = 256 * 1024 * 1024,
                      ram_budget_bytes: int = 512 * 1024 * 1024,
                      probe: PlatformProbe | None = None,
                      memory: MemoryManager | None = None,
                      npu_registry: NPURegistry | None = None,
                      ) -> BootstrapPlan:
    """The standard offline edge bootstrap wiring Campaign VIII parts.

    Steps (all ``requires_network=False``):
    1. platform-probe — snapshot the host
    2. arm64-audit — fail critical when the audit errors
    3. pi-baseline — record the board baseline when on a Pi
    4. memory-mode — derive the operating mode
    5. wear-store — open the flash-aware store
    6. npu-detect — detect accelerators (absence is fine)
    7. residency — build the model residency manager
    8. edge-cache — build the self-tuning decision cache
    9. thermal — start the thermal governor
    """
    probe = probe or PlatformProbe()
    memory = memory or MemoryManager()
    registry = npu_registry or NPURegistry()

    def _s(name: str, fn: Callable[[BootstrapContext], None], *,
           critical: bool = True, description: str = "") -> BootstrapStep:
        return BootstrapStep(name=name, action=fn, critical=critical,
                             description=description)

    def probe_platform(ctx: BootstrapContext) -> None:
        info = probe.probe()
        ctx.set("platform", info)
        ctx.record_artifact("platform", info.to_dict())

    def audit(ctx: BootstrapContext) -> None:
        report = audit_arm64(ctx.get("platform"))
        ctx.set("arm64_report", report)
        ctx.record_artifact("arm64_audit", report.to_dict())
        if not report.passed:
            raise OfflineBootstrapError(
                f"ARM64 audit failed: {report.summary()}")

    def baseline(ctx: BootstrapContext) -> None:
        board = detect_pi_board()
        if board is None:
            ctx.set("pi_board", None)
            return
        base = pi_baseline(board)
        ctx.set("pi_board", board)
        ctx.set("pi_baseline", base)
        ctx.record_artifact("pi_baseline", base.to_dict())

    def memory_mode(ctx: BootstrapContext) -> None:
        mode = memory.refresh()
        ctx.set("memory", memory)
        ctx.set("memory_mode", mode)
        ctx.record_artifact("memory_mode", mode.value)

    def wear_store(ctx: BootstrapContext) -> None:
        store = WearAwareStore.open(
            store_dir, write_budget_bytes=write_budget_bytes)
        ctx.set("wear_store", store)
        ctx.record_artifact("wear_store", store.to_dict())

    def npu_detect(ctx: BootstrapContext) -> None:
        found = registry.detect_all()
        ctx.set("npu_registry", registry)
        ctx.set("npu_devices", found)
        ctx.record_artifact(
            "npu_devices", {n: c.to_dict() for n, c in found.items()})

    def residency(ctx: BootstrapContext) -> None:
        mgr = ResidencyManager(ram_budget_bytes=ram_budget_bytes,
                               memory=memory)
        ctx.set("residency", mgr)

    def edge_cache(ctx: BootstrapContext) -> None:
        cache = EdgeCache(memory)
        ctx.set("edge_cache", cache)
        ctx.record_artifact("cache_config", cache.config.to_dict())

    def thermal(ctx: BootstrapContext) -> None:
        # SysfsThermalSensor degrades gracefully: on hosts without
        # thermal zones it reads None and the governor holds NORMAL.
        # Threshold tuning still NEEDS_HARDWARE_VALIDATION on-device.
        gov = ThermalGovernor(SysfsThermalSensor())
        gov.sample()
        ctx.set("thermal_governor", gov)
        ctx.record_artifact("thermal", gov.to_dict())

    plan = BootstrapPlan()
    plan.add(_s("platform-probe", probe_platform,
                description="snapshot host platform"))
    plan.add(_s("arm64-audit", audit,
                description="fail when the ARM64 audit errors"))
    plan.add(_s("pi-baseline", baseline, critical=False,
                description="record Pi baseline when on a Pi"))
    plan.add(_s("memory-mode", memory_mode,
                description="derive the low-RAM operating mode"))
    plan.add(_s("wear-store", wear_store,
                description="open the flash-aware store"))
    plan.add(_s("npu-detect", npu_detect, critical=False,
                description="detect accelerators; absence is fine"))
    plan.add(_s("residency", residency,
                description="build the model residency manager"))
    plan.add(_s("edge-cache", edge_cache,
                description="build the self-tuning decision cache"))
    plan.add(_s("thermal", thermal,
                description="start the thermal governor"))
    return plan
