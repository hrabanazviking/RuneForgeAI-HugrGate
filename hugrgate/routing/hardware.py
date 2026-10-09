"""Hardware-aware routing. Slice 061.

A rung is only viable if the backend can actually run *here*.
:class:`HostProfile` describes this machine (CPUs, RAM, GPU presence,
platform); :func:`hardware_compatible` checks a backend's
``hardware_requirements()`` against it; :class:`HardwareAwarePlanner`
prunes incompatible rungs at plan time.

Recognized requirement keys (all optional; unknown keys are ignored so
new backends never break old routers):
- ``requires_gpu`` (bool) — needs ``host.has_gpu``;
- ``min_memory_mb`` (number) — needs ``host.memory_mb >=`` it;
- ``min_cpu_count`` (int) — needs ``host.cpu_count >=`` it;
- ``platforms`` (list of ``sys.platform`` strings) — host must be listed.

``HostProfile.detect()`` builds a profile from the real machine using
the standard library only: ``os.cpu_count()``, ``/proc/meminfo`` (or
``sysctl hw.memsize`` on macOS, or a conservative fallback),
``sys.platform``, and ``nvidia-smi`` presence
for GPU detection. GPU detection is best-effort and documented as such.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (
    RouterContext,
    RoutingPlan,
    RungNode,
    RungPlanner,
)

__all__ = [
    "HardwareAwarePlanner",
    "HostProfile",
    "hardware_compatible",
]


@dataclass
class HostProfile:
    """What this machine offers to backends."""

    cpu_count: int = 1
    memory_mb: float = 1024.0
    has_gpu: bool = False
    platform: str = sys.platform
    accelerators: list[str] = field(default_factory=list)

    @classmethod
    def detect(cls) -> HostProfile:
        """Build a profile from the real machine (stdlib only)."""
        cpu = os.cpu_count() or 1
        memory_mb = cls._detect_memory_mb()
        has_gpu = shutil.which("nvidia-smi") is not None
        accelerators = ["cuda"] if has_gpu else []
        return cls(cpu_count=cpu, memory_mb=memory_mb, has_gpu=has_gpu,
                   platform=sys.platform, accelerators=accelerators)

    @staticmethod
    def _detect_memory_mb() -> float:
        try:
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = float(line.split()[1])
                        return round(kb / 1024.0, 1)
        except OSError:
            pass
        if sys.platform == "darwin":
            # macOS has no /proc/meminfo; sysctl hw.memsize reports
            # bytes. Slice 481: without this, macOS hosts silently
            # fell back to the 1024 MB conservative floor.
            try:
                out = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if out.returncode == 0:
                    return round(float(out.stdout.strip()) / (1024.0**2), 1)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        return 1024.0  # conservative fallback when unobservable

    def to_dict(self) -> dict:
        return {
            "cpu_count": self.cpu_count,
            "memory_mb": self.memory_mb,
            "has_gpu": self.has_gpu,
            "platform": self.platform,
            "accelerators": list(self.accelerators),
        }


def hardware_compatible(backend: Backend,
                        host: HostProfile) -> str | None:
    """None when the backend can run on this host, else the reason."""
    reqs = backend.hardware_requirements() or {}
    if reqs.get("requires_gpu") and not host.has_gpu:
        return f"{backend.name} requires a GPU; host has none"
    min_mem = reqs.get("min_memory_mb")
    if isinstance(min_mem, (int, float)) and host.memory_mb < min_mem:
        return (f"{backend.name} needs {min_mem}MB RAM; "
                f"host has {host.memory_mb}MB")
    min_cpu = reqs.get("min_cpu_count")
    if isinstance(min_cpu, int) and host.cpu_count < min_cpu:
        return (f"{backend.name} needs {min_cpu} CPUs; "
                f"host has {host.cpu_count}")
    platforms = reqs.get("platforms")
    if isinstance(platforms, list) and host.platform not in platforms:
        return (f"{backend.name} supports platforms {platforms}; "
                f"host is {host.platform}")
    return None


class HardwareAwarePlanner(RungPlanner):
    """Wrap a planner; prune rungs the host cannot run."""

    def __init__(self, inner: RungPlanner, registry,
                 host: HostProfile | None = None):
        self.inner = inner
        self.registry = registry
        self.host = host or HostProfile.detect()

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        plan = self.inner.plan(ctx)
        kept: list[RungNode] = []
        pruned: list[str] = []
        for node in plan.nodes:
            backend = self.registry.get(node.backend_name)
            reason = (hardware_compatible(backend, self.host)
                      if backend is not None else None)
            node.params["host_compatible"] = reason is None
            if reason is None:
                kept.append(node)
            else:
                pruned.append(reason)
        plan.nodes = kept
        plan.created_by = f"{plan.created_by}+hardware"
        plan.rationale.append(
            f"hardware: host={self.host.to_dict()}, "
            f"pruned {len(pruned)}"
            + (": " + "; ".join(pruned) if pruned else ""))
        return plan
