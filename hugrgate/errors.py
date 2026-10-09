"""Error taxonomy for HugrGate. Slice 10; hardened in slice 007.

Every HugrGate error carries:

- ``code`` — a stable machine-readable string (unique across the taxonomy;
  enforced by ``tests/test_errors.py``), also used on the HTTP wire;
- ``recoverable`` — whether retrying the operation can plausibly succeed;
- ``message`` + ``details`` — human text and structured context.

``to_dict()`` / ``from_dict()`` give a lossless wire round-trip so a
client can reconstruct the exact error class from an HTTP error body.
"""

from __future__ import annotations

from typing import Any, ClassVar

__all__ = [
    "Abstention",
    "BackendError",
    "BackendUnavailable",
    "BenchmarkError",
    "CalibrationError",
    "ChaosError",
    "ClusterAuthError",
    "ContractError",
    "DataFlowDenied",
    "EdgeAffinityError",
    "EdgeCacheError",
    "EdgeMemoryError",
    "GGUFError",
    "GateError",
    "HugrGateError",
    "JurisdictionViolation",
    "LocalOnlyViolation",
    "NPUError",
    "OfflineBootstrapError",
    "PolicyError",
    "PowerBudgetError",
    "PrivacyViolation",
    "QuantError",
    "QueueFull",
    "RecoveryError",
    "ResidencyError",
    "SealError",
    "SecretDetected",
    "SpecError",
    "StorageError",
    "TelemetryError",
    "TimeoutError",
    "WatchdogError",
]


class HugrGateError(Exception):
    """Base for all HugrGate errors."""
    code: ClassVar[str] = "hugrgate_error"
    recoverable: ClassVar[bool] = True

    _registry: ClassVar[dict[str, type[HugrGateError]]] = {}

    def __init__(self, message: str = "", **details: Any):
        super().__init__(message)
        self.message = message
        self.details = details

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Register concrete subclasses by code for from_dict().
        if cls.code != HugrGateError.code:
            HugrGateError._registry[cls.code] = cls

    def to_dict(self) -> dict[str, Any]:
        """Lossless wire representation of this error."""
        return {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HugrGateError:
        """Rebuild the exact error subclass from :meth:`to_dict` output.

        Unknown codes fall back to the base class rather than raising —
        a client must never crash on a newer server's error code.
        """
        code = data.get("code", HugrGateError.code)
        klass = HugrGateError._registry.get(code, HugrGateError)
        error = klass(data.get("message", ""), **data.get("details", {}))
        return error

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}" if self.message else \
            f"[{self.code}]"


class SpecError(HugrGateError):
    code = "spec_error"
    recoverable = False


class PolicyError(HugrGateError):
    code = "policy_error"
    recoverable = False


class BackendError(HugrGateError):
    code = "backend_error"
    recoverable = True


class BackendUnavailable(BackendError):
    code = "backend_unavailable"
    recoverable = True


class CalibrationError(HugrGateError):
    code = "calibration_error"
    recoverable = True


class TimeoutError(BackendError):
    code = "timeout"
    recoverable = True


class PrivacyViolation(HugrGateError):
    code = "privacy_violation"
    recoverable = False


class DataFlowDenied(PrivacyViolation):
    """Raised when a planned data flow violates the data-flow policy.

    Subclass of :class:`PrivacyViolation`: a denied flow is a privacy
    violation, so existing ``except PrivacyViolation`` handlers keep
    working. Not recoverable by blind retry — the caller must change
    the flow (different backend, redaction, lower classification) or
    the policy.
    """

    code = "data_flow_denied"
    recoverable = False


class JurisdictionViolation(PrivacyViolation):
    """Raised when data would cross into a disallowed jurisdiction.

    Subclass of :class:`PrivacyViolation`. Not recoverable by blind
    retry: the destination's jurisdiction is a fact about the world,
    not a transient failure — route to an allowed jurisdiction or
    change the policy.
    """

    code = "jurisdiction_violation"
    recoverable = False


class LocalOnlyViolation(PrivacyViolation):
    """Raised when a local-only field would leave the process.

    Subclass of :class:`PrivacyViolation`. Raised in strict mode by
    the local-only enforcer (slice 231) instead of silently stripping
    the field, so callers get a hard guarantee. Not recoverable by
    blind retry: remove the field or mark it non-local-only.
    """

    code = "local_only_violation"
    recoverable = False


class SecretDetected(PrivacyViolation):
    """Raised when a secret-shaped value is found in outbound data.

    Subclass of :class:`PrivacyViolation`. Not recoverable by blind
    retry: the payload contains a secret and must be cleaned (rotate
    the secret, redact it, or mark the field local-only).
    """

    code = "secret_detected"
    recoverable = False


class SealError(HugrGateError):
    """Raised when authenticated decryption fails (slice 241).

    Wrong key, truncated blob, or failed authentication tag — the
    blob must not be trusted. Not recoverable by blind retry with
    the same blob and key; the caller must supply the right key or
    treat the data as lost/tampered.
    """

    code = "seal_error"
    recoverable = False

    def __init__(self, message: str = "", reason: str = "auth",
                 **details: Any):
        super().__init__(message, reason=reason, **details)
        self.reason = reason


class ClusterAuthError(HugrGateError):
    """Raised when cluster peer authentication fails (slice 208).

    Not recoverable by blind retry: a bad tag means a wrong key, a
    tampered envelope, or a replay — retrying the same bytes cannot
    help. The operator must fix the key or investigate.
    """

    code = "cluster_auth_error"
    recoverable = False


class QueueFull(HugrGateError):
    """Raised when the daemon batching queue is at capacity (back-pressure).

    Moved into the taxonomy in slice 007 (was a bare ``Exception`` in
    ``hugrgate.daemon``). Recoverable: the caller should retry, ideally
    with backoff — the queue drains as the daemon works.
    """
    code = "queue_full"
    recoverable = True


class ContractError(SpecError):
    """A decision contract is malformed, unsupported, or violated.

    Subclass of :class:`SpecError`: a bad contract is a bad spec, so
    existing ``except SpecError`` handlers keep working.
    """
    code = "contract_error"
    recoverable = False


class Abstention(HugrGateError):
    """Raised when the gate abstains — not an error, a decision."""
    code = "abstention"
    recoverable = True

    def __init__(self, message: str = "insufficient confidence",
                 reason: str = "below_threshold", **details: Any):
        super().__init__(message, reason=reason, **details)
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["reason"] = self.reason
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Abstention:
        return cls(data.get("message", "insufficient confidence"),
                   reason=data.get("reason", "below_threshold"),
                   **data.get("details", {}))


class GGUFError(HugrGateError):
    """A GGUF model file is corrupt, truncated, or not GGUF at all.
    Moved into the taxonomy in slice 175 (was a bare ``Exception``
    in ``hugrgate.runtimes.gguf``). Recoverable: callers such as the
    model metadata scanner skip the file and continue with the next
    candidate.
    """
    code = "gguf_error"
    recoverable = True
# --- Campaign VIII: edge-intelligence errors -----------------------------------
# Each slice owned its error locally; slice 200 promotes them into the
# taxonomy so every raise site in the package is a taxonomy error or a
# stdlib validation error (tests/test_errors.py). Codes are unique and
# stable; recoverable is deliberate per class (see slice 200 doc).
class EdgeAffinityError(HugrGateError):
    """An affinity request was invalid or the OS refused it."""
    code = "edge_affinity_error"
class BenchmarkError(HugrGateError):
    """A benchmark definition or artifact was invalid."""
    code = "edge_benchmark_error"
class OfflineBootstrapError(HugrGateError):
    """A bootstrap plan violates the offline-first law."""
    code = "edge_bootstrap_error"
    recoverable = False
class EdgeCacheError(HugrGateError):
    """A cache-tuning request was invalid."""
    code = "edge_cache_error"
    recoverable = False
class ChaosError(HugrGateError):
    """A fault-injection scenario failed its verification."""
    code = "edge_chaos_error"
    recoverable = False
class GateError(HugrGateError):
    """The release gate itself failed to execute (not a check failure)."""
    code = "edge_gate_error"
    recoverable = False
class EdgeMemoryError(HugrGateError):
    """A memory budget was exceeded or an allocation was invalid."""
    code = "edge_memory_error"
class NPUError(HugrGateError):
    """An NPU operation failed (load/infer on a present device)."""
    code = "edge_npu_error"
class PowerBudgetError(HugrGateError):
    """A power-budget invariant was violated."""
    code = "edge_power_budget_error"
class QuantError(HugrGateError):
    """A quantization profile or operation was invalid."""
    code = "edge_quant_error"
    recoverable = False
class RecoveryError(HugrGateError):
    """A checkpoint could not be written or recovered."""
    code = "edge_recovery_error"
class ResidencyError(HugrGateError):
    """A residency invariant was violated (unknown model, no room)."""
    code = "edge_residency_error"
class StorageError(HugrGateError):
    """A storage invariant was violated (budget, format, key)."""
    code = "edge_storage_error"
class TelemetryError(HugrGateError):
    """A telemetry invariant was violated."""
    code = "edge_telemetry_error"
    recoverable = False
class WatchdogError(HugrGateError):
    """A watchdog invariant was violated."""
    code = "edge_watchdog_error"
    recoverable = False
