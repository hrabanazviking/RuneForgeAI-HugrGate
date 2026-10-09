"""Reliability & chaos engineering. Campaign XI (slices 251-275).

This package unifies HugrGate's fault-injection, resilience, and
recovery machinery behind one experiment discipline:

- :mod:`hugrgate.chaos.framework` — the experiment model: hypothesis,
  steady-state probes, faults with rollback, blast-radius guards, and
  a runner that records every outcome instead of aborting;
- later slices add fault libraries (backend, model, cache, filesystem,
  network, clock), resilience primitives (retry budgets, bulkheads,
  degradation plans, recovery verification), and the chaos scorecard.

The older :mod:`hugrgate.edge.chaos` edge-device scenarios and
:mod:`hugrgate.cluster.chaos` network fault proxy remain the
domain-specific fault sources; the framework here is the shared
experiment harness they can run inside.
"""

from hugrgate.chaos.backend_faults import (
    CRASH,
    ERROR_RATE,
    HANG,
    LATENCY,
    MALFORMED,
    FaultSpec,
    FaultyBackend,
)
from hugrgate.chaos.cache_faults import CacheCorruptor
from hugrgate.chaos.filesystem import disk_full, read_only
from hugrgate.chaos.framework import (
    BlastRadius,
    ChaosExperiment,
    ExperimentReport,
    ExperimentRunner,
    Fault,
    FaultResult,
    ProbeOutcome,
    SteadyStateProbe,
)
from hugrgate.chaos.model_faults import (
    CORRUPTION_KINDS,
    MUST_REJECT_KINDS,
    ModelCorruptor,
)
from hugrgate.chaos.network import (
    DOWN,
    UP,
    NetworkGuard,
    NetworkSimulator,
)
from hugrgate.chaos.resources import (
    CRITICAL,
    OK,
    WARN,
    CPUStarvationSimulator,
    MemoryPressureSimulator,
    MemoryReading,
    ResourceGuard,
)

__all__ = [
    "CORRUPTION_KINDS",
    "CRASH",
    "CRITICAL",
    "DOWN",
    "ERROR_RATE",
    "HANG",
    "LATENCY",
    "MALFORMED",
    "MUST_REJECT_KINDS",
    "OK",
    "UP",
    "WARN",
    "BlastRadius",
    "CPUStarvationSimulator",
    "CacheCorruptor",
    "ChaosExperiment",
    "ExperimentReport",
    "ExperimentRunner",
    "Fault",
    "FaultResult",
    "FaultSpec",
    "FaultyBackend",
    "MemoryPressureSimulator",
    "MemoryReading",
    "ModelCorruptor",
    "NetworkGuard",
    "NetworkSimulator",
    "ProbeOutcome",
    "ResourceGuard",
    "SteadyStateProbe",
    "disk_full",
    "read_only",
]
