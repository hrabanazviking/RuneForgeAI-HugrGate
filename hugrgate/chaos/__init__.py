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
from hugrgate.chaos.bulkhead import BulkheadExecutor
from hugrgate.chaos.cache_faults import CacheCorruptor
from hugrgate.chaos.clock import SkewedClock, audit_deadline_clocks
from hugrgate.chaos.crash import CrashOnlyHarness, CrashReport
from hugrgate.chaos.degradation import (
    DegradationPlan,
    DegradationPlanRegistry,
    DegradationReport,
    DegradationStep,
    builtin_degradation_plans,
)
from hugrgate.chaos.experiments import (
    CHAOS_LAB,
    DependencyMatrix,
    DependencyScenario,
    ServiceUnderTest,
    builtin_dependency_matrix,
    dependency_failure_matrix,
    partial_service_failure_experiment,
    run_experiment_on_lab,
)
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
from hugrgate.chaos.recovery import (
    RecoveryProbe,
    RecoveryReport,
    RecoveryVerifier,
    backend_health_probe,
    circuit_closed_probe,
    decision_smoke_probe,
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
from hugrgate.chaos.retry import (
    RetryBudget,
    default_retry_policy,
    retry_with_budget,
)

__all__ = [
    "CHAOS_LAB",
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
    "BulkheadExecutor",
    "CPUStarvationSimulator",
    "CacheCorruptor",
    "ChaosExperiment",
    "CrashOnlyHarness",
    "CrashReport",
    "DegradationPlan",
    "DegradationPlanRegistry",
    "DegradationReport",
    "DegradationStep",
    "DependencyMatrix",
    "DependencyScenario",
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
    "RecoveryProbe",
    "RecoveryReport",
    "RecoveryVerifier",
    "ResourceGuard",
    "RetryBudget",
    "ServiceUnderTest",
    "SkewedClock",
    "SteadyStateProbe",
    "audit_deadline_clocks",
    "backend_health_probe",
    "builtin_degradation_plans",
    "builtin_dependency_matrix",
    "circuit_closed_probe",
    "decision_smoke_probe",
    "default_retry_policy",
    "dependency_failure_matrix",
    "disk_full",
    "partial_service_failure_experiment",
    "read_only",
    "retry_with_budget",
    "run_experiment_on_lab",
]
