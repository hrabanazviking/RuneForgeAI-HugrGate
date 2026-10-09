"""Slice 007 — exception taxonomy hardening.

The error taxonomy is a contract: codes are unique and stable, the
recoverable flag is deliberate per class, every error round-trips
through ``to_dict``/``from_dict`` (wire-safe), and every ``raise`` in
the package uses the taxonomy or a stdlib argument-validation error.
"""

from __future__ import annotations

import ast
from pathlib import Path

import hugrgate
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    BackpressureError,
    BenchmarkError,
    BulkheadRejected,
    CalibrationError,
    ChaosError,
    ClusterAuthError,
    ContractError,
    DataFlowDenied,
    EdgeAffinityError,
    EdgeCacheError,
    EdgeMemoryError,
    GateError,
    GGUFError,
    GpuschedError,
    HugrGateError,
    JurisdictionViolation,
    KeyProviderError,
    LocalOnlyViolation,
    MultiprocError,
    NPUError,
    NumaError,
    OfflineBootstrapError,
    PerfGateError,
    PolicyError,
    PoolError,
    PowerBudgetError,
    PrivacyViolation,
    ProfilingError,
    QuantError,
    QueueFull,
    RecoveryError,
    ResidencyError,
    RetryBudgetExhausted,
    SealError,
    SecretDetected,
    SchedulerError,
    SerdeError,
    SpecError,
    StorageError,
    SupervisionError,
    TelemetryError,
    TimeoutError,
    WatchdogError,
    ZeroCopyError,
)

ROOT = Path(__file__).resolve().parent.parent

ALL_ERRORS = [
    HugrGateError, SpecError, PolicyError, BackendError, BackendUnavailable,
    CalibrationError, TimeoutError, PrivacyViolation, QueueFull, Abstention,
    PerfGateError,
    ContractError,
    GGUFError,
    # Campaign VIII edge-intelligence errors (slice 200 taxonomy promotion).
    EdgeAffinityError, BenchmarkError, OfflineBootstrapError, EdgeCacheError,
    # Campaign XII performance-forge errors (slice 276+).
    ProfilingError, ZeroCopyError, SerdeError, SchedulerError,
    BackpressureError, PoolError, MultiprocError, SupervisionError,
    NumaError, GpuschedError,
    ChaosError, GateError, EdgeMemoryError, NPUError, PowerBudgetError,
    QuantError, RecoveryError, ResidencyError, RetryBudgetExhausted,
    BulkheadRejected,
    StorageError, TelemetryError, WatchdogError,
    ClusterAuthError,
    DataFlowDenied,
    JurisdictionViolation,
    LocalOnlyViolation,
    SecretDetected,
    SealError,
    KeyProviderError,
]

EXPECTED_CODES = {
    HugrGateError: "hugrgate_error",
    SpecError: "spec_error",
    PolicyError: "policy_error",
    PerfGateError: "perfgate_error",
    PoolError: "pool_error",
    MultiprocError: "multiproc_error",
    SupervisionError: "supervision_error",
    GpuschedError: "gpusched_error",
    NumaError: "numa_error",
    BackendError: "backend_error",
    BackendUnavailable: "backend_unavailable",
    BackpressureError: "backpressure_error",
    CalibrationError: "calibration_error",
    TimeoutError: "timeout",
    PrivacyViolation: "privacy_violation",
    QueueFull: "queue_full",
    Abstention: "abstention",
    ContractError: "contract_error",
    GGUFError: "gguf_error",
    EdgeAffinityError: "edge_affinity_error",
    BenchmarkError: "edge_benchmark_error",
    BulkheadRejected: "bulkhead_rejected",
    OfflineBootstrapError: "edge_bootstrap_error",
    EdgeCacheError: "edge_cache_error",
    ChaosError: "edge_chaos_error",
    GateError: "edge_gate_error",
    EdgeMemoryError: "edge_memory_error",
    NPUError: "edge_npu_error",
    PowerBudgetError: "edge_power_budget_error",
    ProfilingError: "profiling_error",
    ZeroCopyError: "zerocopy_error",
    QuantError: "edge_quant_error",
    RecoveryError: "edge_recovery_error",
    ResidencyError: "edge_residency_error",
    RetryBudgetExhausted: "retry_budget_exhausted",
    SchedulerError: "scheduler_error",
    SerdeError: "serde_error",
    StorageError: "edge_storage_error",
    TelemetryError: "edge_telemetry_error",
    WatchdogError: "edge_watchdog_error",
    ClusterAuthError: "cluster_auth_error",
    DataFlowDenied: "data_flow_denied",
    JurisdictionViolation: "jurisdiction_violation",
    LocalOnlyViolation: "local_only_violation",
    SecretDetected: "secret_detected",
    SealError: "seal_error",
    KeyProviderError: "key_provider_error",
}

EXPECTED_RECOVERABLE = {
    HugrGateError: True,
    SpecError: False,
    PolicyError: False,
    PerfGateError: False,
    PoolError: True,
    MultiprocError: True,
    SupervisionError: True,
    GpuschedError: True,
    NumaError: True,
    BackendError: True,
    BackendUnavailable: True,
    BackpressureError: True,
    CalibrationError: True,
    TimeoutError: True,
    PrivacyViolation: False,
    QueueFull: True,
    Abstention: True,
    ContractError: False,
    GGUFError: True,
    # Deliberate per class (slice 200): True where retrying after a changed
    # environment can plausibly succeed (freed memory, installed extra,
    # shed load, appeared hardware); False where the caller must fix the
    # request itself (invalid arguments, structural law violations).
    EdgeAffinityError: True,
    BenchmarkError: True,
    BulkheadRejected: True,
    OfflineBootstrapError: False,
    EdgeCacheError: False,
    ChaosError: False,
    GateError: False,
    EdgeMemoryError: True,
    NPUError: True,
    PowerBudgetError: True,
    ProfilingError: True,
    ZeroCopyError: True,
    QuantError: False,
    RecoveryError: True,
    ResidencyError: True,
    RetryBudgetExhausted: True,
    SchedulerError: True,
    SerdeError: False,
    StorageError: True,
    TelemetryError: False,
    WatchdogError: False,
    ClusterAuthError: False,
    DataFlowDenied: False,
    JurisdictionViolation: False,
    LocalOnlyViolation: False,
    SecretDetected: False,
    SealError: False,
    KeyProviderError: False,
}


def test_codes_are_unique_and_stable():
    codes = [e.code for e in ALL_ERRORS]
    assert len(set(codes)) == len(codes), f"duplicate codes: {codes}"
    for klass, code in EXPECTED_CODES.items():
        assert klass.code == code, f"{klass.__name__}.code changed: {klass.code}"


def test_recoverable_flags_are_deliberate():
    for klass, expected in EXPECTED_RECOVERABLE.items():
        assert klass.recoverable is expected, (
            f"{klass.__name__}.recoverable changed to {klass.recoverable}"
        )


def test_hierarchy_is_sound():
    assert issubclass(BackendUnavailable, BackendError)
    assert issubclass(TimeoutError, BackendError)
    assert issubclass(QueueFull, HugrGateError)
    for klass in ALL_ERRORS:
        assert issubclass(klass, HugrGateError)
        assert issubclass(klass, Exception)


def test_every_error_carries_message_and_details():
    err = BackendError("boom", backend="x", latency_ms=3.5)
    assert err.message == "boom"
    assert err.details == {"backend": "x", "latency_ms": 3.5}
    assert "boom" in str(err) and "backend_error" in str(err)


def test_to_dict_from_dict_round_trip():
    cases = [
        SpecError("bad spec", field="options"),
        PolicyError("denied"),
        BackendError("failed", backend="logreg"),
        BackendUnavailable("down", backend="llm"),
        CalibrationError("not fitted"),
        TimeoutError("too slow", deadline_ms=50.0),
        PrivacyViolation("remote blocked", backend="nli"),
        QueueFull("daemon is shutting down"),
        Abstention("low confidence", reason="below_threshold", p=0.4),
        HugrGateError("generic"),
        # Campaign VIII taxonomy members round-trip identically.
        NPUError("no Hailo device", vendor="hailo"),
        EdgeMemoryError("budget exceeded", needed_bytes=1024),
        ClusterAuthError("bad tag"),
    ]
    for original in cases:
        data = original.to_dict()
        rebuilt = HugrGateError.from_dict(data)
        assert type(rebuilt) is type(original), (
            f"{type(original).__name__} did not round-trip: {data}")
        assert rebuilt.to_dict() == data
    # Abstention keeps its reason through the wire
    abstained = HugrGateError.from_dict(
        Abstention("x", reason="escalation_required").to_dict())
    assert isinstance(abstained, Abstention)
    assert abstained.reason == "escalation_required"


def test_from_dict_with_unknown_code_falls_back_to_base():
    err = HugrGateError.from_dict(
        {"code": "future_error_from_newer_server", "message": "m",
         "recoverable": True, "details": {}})
    assert type(err) is HugrGateError
    assert err.message == "m"


def test_queue_full_is_a_taxonomy_error():
    err = QueueFull("full")
    assert isinstance(err, HugrGateError)
    assert err.code == "queue_full"
    assert err.recoverable is True
    # still importable from its old home
    from hugrgate import daemon
    assert daemon.QueueFull is QueueFull


def test_package_exports_queue_full():
    assert "QueueFull" in hugrgate.__all__
    assert hugrgate.QueueFull is QueueFull


def test_raise_sites_use_taxonomy_or_stdlib_validation():
    """Every ``raise X`` must be a taxonomy error or a stdlib
    argument-validation error (ValueError/TypeError/KeyError/etc.)."""
    allowed = {e.__name__ for e in ALL_ERRORS} | {
        "ValueError", "TypeError", "KeyError", "AttributeError",
        "NotImplementedError", "RuntimeError", "StopIteration",
        "AssertionError",
    }
    offenders = []
    for path in sorted((ROOT / "hugrgate").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            exc = node.exc
            name = None
            if isinstance(exc, ast.Name):
                name = exc.id
            elif isinstance(exc, ast.Call):
                func = exc.func
                name = func.id if isinstance(func, ast.Name) else None
            if name and name not in allowed:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}")
    assert not offenders, f"non-taxonomy raise sites: {offenders}"


def test_chaining_is_preserved():
    try:
        try:
            raise ValueError("root cause")
        except ValueError as e:
            raise BackendError("wrapped") from e
    except BackendError as caught:
        assert isinstance(caught.__cause__, ValueError)


# --- failure / boundary --------------------------------------------------------

def test_abstention_defaults():
    a = Abstention()
    assert a.reason == "below_threshold"
    assert a.message == "insufficient confidence"
    assert a.code == "abstention"


def test_error_with_no_message_still_strs():
    assert str(SpecError()) == "[spec_error]"
