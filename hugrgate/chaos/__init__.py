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

__all__ = [
    "CRASH",
    "ERROR_RATE",
    "HANG",
    "LATENCY",
    "MALFORMED",
    "BlastRadius",
    "ChaosExperiment",
    "ExperimentReport",
    "ExperimentRunner",
    "Fault",
    "FaultResult",
    "FaultSpec",
    "FaultyBackend",
    "ProbeOutcome",
    "SteadyStateProbe",
]
