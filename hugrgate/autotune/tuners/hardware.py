"""Hardware-aware tuner. Slice 462.

The same HugrGate deployment runs on a 2-core edge box and a 64-core
server; one static config fits neither. This tuner detects the host
(cpu count, RAM, architecture) and selects the matching hardware
tier, proposing that tier's parameter profile.

Tiers are operator-declared: each :class:`HardwareTier` names minimum
cpu/memory requirements and a dict of parameter values. The tuner
picks the *most demanding tier the hardware satisfies* (tiers sorted
by requirements descending), diffs its profile against the live
config, and proposes only the differing params.

What this tuner does *not* do (marked honestly): it cannot verify
that a tier's profile actually performs well on the hardware — that
is the operator's benchmarking job (slice 474's autotuning benchmark
can validate a profile before it ships). Detection uses stdlib only
(``os.cpu_count``, ``/proc/meminfo`` on Linux with a conservative
fallback); no vendor SDKs.

For tests and dry-runs the detected profile can be injected, so tier
selection is deterministic without mocking the OS.
"""

from __future__ import annotations

import os
import platform
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner
from hugrgate.errors import TunerError

__all__ = ["HardwareAwareTuner", "HardwareProfile", "HardwareTier",
           "detect_hardware"]


@dataclass(frozen=True)
class HardwareProfile:
    """Detected (or injected) host description."""

    cpu_count: int
    memory_mb: float
    arch: str
    system: str

    def to_dict(self) -> dict[str, Any]:
        return {"cpu_count": self.cpu_count, "memory_mb": self.memory_mb,
                "arch": self.arch, "system": self.system}


def detect_hardware() -> HardwareProfile:
    """Detect the host with stdlib only."""
    cpu = os.cpu_count() or 1
    mem_mb = 0.0
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"MemTotal:\s+(\d+)\s+kB", line)
                if m:
                    mem_mb = int(m.group(1)) / 1024.0
                    break
    except OSError:
        mem_mb = 0.0  # non-Linux or unreadable: unknown, not zero-trust
    return HardwareProfile(cpu_count=cpu, memory_mb=mem_mb,
                           arch=platform.machine(),
                           system=platform.system())


@dataclass(frozen=True)
class HardwareTier:
    """One hardware class and the config profile for it."""

    name: str
    min_cpu: int
    min_memory_mb: float
    profile: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.name:
            raise TunerError("tier needs a name")
        if self.min_cpu < 1 or self.min_memory_mb < 0:
            raise TunerError("tier requirements must be positive",
                             tier=self.name)
        if not self.profile:
            raise TunerError("tier needs a non-empty profile",
                             tier=self.name)

    def matches(self, hw: HardwareProfile) -> bool:
        mem_ok = hw.memory_mb <= 0 or hw.memory_mb >= self.min_memory_mb
        return hw.cpu_count >= self.min_cpu and mem_ok


@dataclass
class HardwareAwareTuner(BaseTuner):
    """Propose the config profile for the detected hardware tier."""

    name: str = "hardware_aware_tuner"
    tiers: list[HardwareTier] = field(default_factory=list)
    injected_hardware: HardwareProfile | None = None

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise TunerError("hardware tuner needs an objective_id")
        if not self.tiers:
            raise TunerError("hardware tuner needs at least one tier")
        names = [t.name for t in self.tiers]
        if len(set(names)) != len(names):
            raise TunerError("duplicate tier names")
        # Most demanding tier first: sort by (cpu, memory) descending.
        self.tiers = sorted(self.tiers,
                            key=lambda t: (t.min_cpu, t.min_memory_mb),
                            reverse=True)

    def select_tier(self, hw: HardwareProfile) -> HardwareTier:
        for tier in self.tiers:
            if tier.matches(hw):
                return tier
        return self.tiers[-1]  # weakest tier always matches

    def tune(self, ctx: TuningContext) -> Proposal | None:
        hw = self.injected_hardware or detect_hardware()
        tier = self.select_tier(hw)
        changes: dict[str, Any] = {}
        for pname, pvalue in tier.profile.items():
            param = ctx.store.describe(pname)  # unknown -> ParameterError
            coerced = param.coerce(pvalue)  # validates type/bounds
            if ctx.store.get(pname) != coerced:
                changes[pname] = coerced
        evidence: dict[str, Any] = {
            "hardware": hw.to_dict(),
            "tier": tier.name,
            "tier_requirements": {"min_cpu": tier.min_cpu,
                                  "min_memory_mb": tier.min_memory_mb},
            "note": ("tier selection is measured detection, but profile "
                     "quality on the hardware still requires real-world "
                     "validation (see slice 474)"),
        }
        if not changes:
            return None
        # Score: fraction of tier params already correct (higher better);
        # baseline 0 proposals only when something differs.
        return self._propose(ctx, changes, 0.0, 1.0, evidence)
