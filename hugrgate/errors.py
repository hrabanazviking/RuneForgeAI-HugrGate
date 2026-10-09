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
    "AgentBudgetExhausted",
    "AgentContractViolation",
    "AgentError",
    "AgentEscalationFailed",
    "AgentLoopDetected",
    "AgentNotFound",
    "AgentRunaway",
    "BackendError",
    "BackendUnavailable",
    "BackpressureError",
    "BenchmarkError",
    "BulkheadRejected",
    "CalibrationError",
    "ChaosError",
    "ClusterAuthError",
    "ContractError",
    "DataFlowDenied",
    "DatasetError",
    "EdgeAffinityError",
    "EdgeCacheError",
    "EdgeMemoryError",
    "EvalError",
    "EvalGateError",
    "GGUFError",
    "GateError",
    "GpuschedError",
    "HugrGateError",
    "HumanReviewTimeout",
    "JurisdictionViolation",
    "KeyProviderError",
    "LocalOnlyViolation",
    "MemoryAccessDenied",
    "MemoryError",
    "MemoryQuotaExceeded",
    "MultiprocError",
    "NPUError",
    "NumaError",
    "OfflineBootstrapError",
    "PerfGateError",
    "PolicyError",
    "PoolError",
    "PowerBudgetError",
    "PrivacyViolation",
    "ProfilingError",
    "QuantError",
    "QueueFull",
    "RecoveryError",
    "ResidencyError",
    "RetryBudgetExhausted",
    "SchedulerError",
    "SealError",
    "SecretDetected",
    "SerdeError",
    "SpecError",
    "StorageError",
    "SupervisionError",
    "TelemetryError",
    "TimeoutError",
    "WatchdogError",
    "ZeroCopyError",
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


class BulkheadRejected(BackendError):
    """The per-backend bulkhead was full: the call was rejected fast
    instead of queueing behind a stuck backend.

    A backend-family failure so existing failover handlers apply
    (shedding to another backend is the correct response).
    Recoverable: capacity frees as in-flight calls finish.
    Deliberately *not* retried by the default retry policy —
    spinning against a full bulkhead with no backoff helps nobody.
    """
    code = "bulkhead_rejected"
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


class KeyProviderError(HugrGateError):
    """Raised when a key provider cannot supply a key (slice 243).

    Missing environment variable, unreadable key file, unknown key
    id, or malformed key material. Not recoverable by blind retry:
    the operator must fix the key configuration.
    """

    code = "key_provider_error"
    recoverable = False


class MemoryError(HugrGateError):
    """Base for decision-memory failures (slice 301).

    Raised for operational memory problems — unknown episode ids,
    corrupt imports, failed attachments. Recoverable: the history
    itself is intact; the caller should fix the request.
    """

    code = "memory_error"
    recoverable = True


class MemoryQuotaExceeded(MemoryError):
    """Raised when a record would exceed the memory quota (slice 316).

    Recoverable: evict, compact, or raise the quota, then retry.
    """

    code = "memory_quota_exceeded"
    recoverable = True


class MemoryAccessDenied(MemoryError):
    """Raised when a role may not read or mutate an episode (slice 315).

    Not recoverable by blind retry: the caller needs a different
    role or the episode's privacy class must change.
    """

    code = "memory_access_denied"
    recoverable = False


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
class RetryBudgetExhausted(BackendError):
    """The retry budget was exhausted before the operation succeeded.

    A backend-family failure: the call did not succeed, after a
    bounded number of retries. Recoverable: after the budget window
    refills, retrying can plausibly succeed.
    """
    code = "retry_budget_exhausted"
    recoverable = True
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


class ProfilingError(HugrGateError):
    """A profiler run was misconfigured or failed to execute. Slice 276."""
    code = "profiling_error"
    # A failed profile never invalidates the decision itself; retrying
    # without (or with fixed) profiler settings can plausibly succeed.
    recoverable = True


class ZeroCopyError(HugrGateError):
    """A zero-copy invariant was violated (mutation of frozen data).

    Slice 280.  Raised at the mutation site, never silently downstream;
    retrying with an unfrozen path can succeed.
    """
    code = "zerocopy_error"
    recoverable = True


class SerdeError(HugrGateError):
    """A serialization payload was malformed or version-incompatible.

    Slice 281.  A bad payload is a caller bug, not a transient fault:
    retrying the same bytes will fail the same way.
    """
    code = "serde_error"
    recoverable = False


class SchedulerError(HugrGateError):
    """A scheduling invariant was violated (bad config, full queue, down).

    Slice 285.  Queue-full and shutdown races are transient — shedding
    load or retrying later can succeed.
    """
    code = "scheduler_error"
    recoverable = True


class BackpressureError(HugrGateError):
    """Admission refused: the system is saturated, shed load and retry.

    Slice 289.  Carries ``reason`` ("inflight_cap" | "rate_limit") and,
    when the rate limiter can compute one, ``retry_after_s``.
    """
    code = "backpressure_error"
    recoverable = True


class PoolError(HugrGateError):
    """A resource pool was misconfigured, exhausted, or unhealthy.

    Slice 290.  Exhaustion is transient — retrying after load sheds can
    succeed; a poisoned factory is a caller/ops problem.
    """
    code = "pool_error"
    recoverable = True


class MultiprocError(HugrGateError):
    """A multiprocess task could not be executed.

    Slice 294.  Unpicklable tasks are caller errors; worker crashes and
    timeouts are transient — the pool replaces the worker and the caller
    may retry.  Recoverable, because one bad task must never take down
    the gate.
    """
    code = "multiproc_error"
    recoverable = True


class SupervisionError(HugrGateError):
    """A supervised worker could not be kept alive.

    Slice 295.  Raised for supervisor misuse (unknown worker, double
    start); worker *failures* are handled by restart/escalation, not
    exceptions.  Recoverable — the supervisor itself keeps running.
    """
    code = "supervision_error"
    recoverable = True


class NumaError(HugrGateError):
    """A NUMA topology query or thread-pinning request failed.

    Slice 296.  NUMA operations are best-effort performance hints, not
    correctness requirements — failure is always recoverable (run
    unpinned).  Real multi-node hardware validation is still needed
    (see the module docstring of :mod:`hugrgate.numa`).
    """
    code = "numa_error"
    recoverable = True


class GpuschedError(HugrGateError):
    """GPU discovery or device assignment failed.

    Slice 297.  GPU scheduling is a best-effort placement hint; the
    gate always runs correctly on CPU.  Real GPU-hardware validation
    is still needed (see the module docstring of
    :mod:`hugrgate.gpusched`).
    """
    code = "gpusched_error"
    recoverable = True


class PerfGateError(HugrGateError):
    """A performance regression gate failed.

    Slice 298.  Deliberately *not* recoverable: a breached gate is a
    hard quality signal, not a transient fault.  Do not catch-and-
    retry; fix the regression or consciously re-baseline.
    """
    code = "perfgate_error"
    recoverable = False


# --- Campaign XIV: observability errors -----------------------------------------
# Slice 326 promotes the observability failure modes into the taxonomy up
# front so every later slice in the campaign raises taxonomy errors, never
# bare ``ValueError``/``RuntimeError``.  Codes are unique and stable.
# Recoverability is deliberate: observability must never take down a
# decision — recording failures are recoverable; definition errors (bad
# metric name, invalid SLO) are caller bugs and not recoverable.
class ObservabilityError(HugrGateError):
    """Base for all Campaign XIV observability failures.
    Slice 326.  A failed metric recording, dropped span, or missed alert
    must never fail the decision it observes; subclasses keep that
    promise unless the failure is a caller-side definition bug.
    """
    code = "observability_error"
    recoverable = True
class MetricError(ObservabilityError):
    """A metric definition or recording was invalid.
    Slice 326.  Bad metric names, wrong label sets, negative counter
    increments, non-finite observations, and label-cardinality overflow
    all surface here.  Recording is best-effort — the gate must keep
    deciding — so this is recoverable; *definition* bugs should still be
    fixed rather than retried blindly.
    """
    code = "metric_error"
    recoverable = True


class TraceError(ObservabilityError):
    """A trace/span invariant was violated.
    Slice 328.  Malformed traceparent headers, forbidden (payload)
    attribute keys, or a broken span lifecycle surface here.
    Recoverable: a dropped span loses one observation, never the
    decision.
    """
    code = "trace_error"
    recoverable = True
class SLOError(ObservabilityError):
    """An SLO definition or evaluation was invalid.
    Slice 344.  Targets outside (0, 1], non-positive windows, or
    evaluations over empty sample sets surface here.  Not recoverable:
    a bad SLO definition is a configuration bug — fix it, do not retry
    the same definition.
    """
    code = "slo_error"
    recoverable = False
class AlertError(ObservabilityError):
    """An alert rule or alert delivery failed.
    Slice 343.  Bad rule configuration is a caller bug, but a missed
    delivery must never cascade - recoverable so the alerter can keep
    evaluating the remaining rules.
    """
    code = "alert_error"
    recoverable = True


class DatasetError(HugrGateError):
    """A dataset manifest is malformed, fails validation, or is unusable.
    Slice 352.  Deliberately *not* recoverable: a broken manifest is a
    data-integrity signal, not a transient fault.  Fix the dataset or
    its manifest; retrying the same bytes cannot succeed.
    """
    code = "dataset_error"
    recoverable = False
class EvalError(HugrGateError):
    """An evaluation-lab operation failed (bad experiment, empty run).
    Slice 351.  Deliberately *not* recoverable: evaluation failures
    signal misconfiguration or empty data, not transient faults.  Fix
    the experiment definition and re-run.
    """
    code = "eval_error"
    recoverable = False
class EvalGateError(HugrGateError):
    """An evaluation quality gate failed (CI red).
    Slice 373.  Raised by :func:`hugrgate.evlab.gates.assert_gates`
    when one or more declared gates do not pass.  Not recoverable:
    the numbers missed their thresholds — change the code, the data,
    or the gate, then re-run.
    """
    code = "eval_gate_error"
    recoverable = False


# --- Campaign XVI: agent nervous system -------------------------------------
class AgentError(HugrGateError):
    """Base for all agent-nervous-system errors. Slice 376.
    Recoverable by default: most nervous-system faults (a dropped
    signal, a saturated bus, a timed-out review) are transient and
    the loop can continue or retry once the condition clears.
    """
    code = "agent_error"
    recoverable = True
class AgentContractViolation(AgentError):
    """An agent's integration contract is invalid or was breached.
    Slice 376.  Not recoverable: a bad contract is a configuration
    bug — fix the declaration, do not retry the same contract.
    """
    code = "agent_contract_violation"
    recoverable = False
class AgentNotFound(AgentError):
    """No registered agent matches the requested id/capability/intent.
    Slice 376.  Not recoverable: the registry is authoritative —
    register the agent first.
    """
    code = "agent_not_found"
    recoverable = False
class AgentLoopDetected(AgentError):
    """An agent call chain cycled back on itself. Slice 393.
    Recoverable: the loop-breaker severs the cycle and the ticket
    can be rerouted or escalated.
    """
    code = "agent_loop_detected"
class AgentRunaway(AgentError):
    """A ticket breached runaway limits (escalations/steps/tokens) or
    the kill switch tripped. Slice 394.  Not recoverable: a runaway
    ticket is terminated, never resumed — start a new ticket.
    """
    code = "agent_runaway"
    recoverable = False
class AgentBudgetExhausted(AgentError):
    """An agent exhausted its decision/token/latency budget.
    Slice 395.  Recoverable: budgets reset on a new window or a
    supervisor can top them up.
    """
    code = "agent_budget_exhausted"
class AgentEscalationFailed(AgentError):
    """An escalation could not be delivered (no higher level, depth
    cap reached, cooldown storm). Slice 384.  Recoverable: the ticket
    stays with its current owner and can retry after cooldown.
    """
    code = "agent_escalation_failed"
    recoverable = False
class HumanReviewTimeout(AgentError):
    """A human-review item breached its SLA without a decision.
    Slice 385.  Recoverable: the item stays queued and the timeout
    policy (escalate / auto-deny / auto-approve) decides.
    """
    code = "human_review_timeout"
    recoverable = False
class SupplyChainViolation(HugrGateError):
    """A dependency or artifact violates the supply-chain policy.
    Slice 404.  Raised by
    :func:`hugrgate.security.supply_chain.SupplyChainPolicy.enforce`
    when a package comes from an unapproved index, lacks required
    hashes, carries a disallowed license, or is on the blocklist.
    Not recoverable: the dependency declaration itself must change.
    """
    code = "supply_chain_violation"
    recoverable = False
class SignatureVerificationFailed(HugrGateError):
    """A cryptographic signature check failed.
    Slice 405.  Raised by :mod:`hugrgate.security.model_signing` (and
    the checksum enforcer, slice 406) when a signed envelope's tag
    does not verify, the key id is unknown, or the envelope is
    malformed.  Not recoverable: the bytes or the key are wrong —
    retrying the same check cannot succeed.
    """
    code = "signature_verification_failed"
    recoverable = False
class PluginTrustError(HugrGateError):
    """A plugin failed the trust model.
    Slice 407.  Raised by :mod:`hugrgate.security.plugins` when a
    plugin manifest is unsigned/invalid, its trust level does not
    permit loading, its entry point escapes the module allowlist, or
    it claims a capability its trust level does not grant.  Not
    recoverable: the plugin declaration itself must change.
    """
    code = "plugin_trust_error"
    recoverable = False
class SandboxViolation(HugrGateError):
    """A sandboxed backend attempted a forbidden operation.
    Slice 408.  Raised by :mod:`hugrgate.security.sandbox` when an
    audit hook observes a denied syscall-class event (subprocess,
    network, filesystem write) inside a sandbox boundary.  Not
    recoverable: the backend's behavior violates its policy.
    """
    code = "sandbox_violation"
    recoverable = False
class InputTooLarge(HugrGateError):
    """An input exceeded the configured size limits.
    Slice 409.  Raised by :mod:`hugrgate.security.input_limits`
    when a state payload, batch, or prompt crosses its limit.  Not
    recoverable: the same bytes will fail again — shrink the input
    or raise the limit deliberately.
    """
    code = "input_too_large"
    recoverable = False
class ResourceBudgetExceeded(HugrGateError):
    """A resource budget was exhausted inside a guarded region.
    Slice 410.  Raised by :mod:`hugrgate.security.resource_guards`
    when CPU time, address-space, or charged cost units exceed the
    declared budget.  Not recoverable: the same work will exceed
    the same budget again — shrink the work or raise the budget.
    """
    code = "resource_budget_exceeded"
    recoverable = False
class DeserializationBlocked(HugrGateError):
    """Untrusted bytes were refused deserialization.
    Slice 411.  Raised by :mod:`hugrgate.security.serde_guards`
    when a pickle payload references a class outside the allowlist,
    when pickle is disabled by policy, or when opaque bytes are not
    a recognized safe encoding.  Not recoverable: the bytes are
    hostile or the policy forbids them.
    """
    code = "deserialization_blocked"
    recoverable = False
class PathTraversalBlocked(HugrGateError):
    """A path escaped its jail directory.
    Slice 412.  Raised by :mod:`hugrgate.security.path_guards` when
    a user-influenced path resolves outside the root it was jailed
    to (``..`` segments, absolute paths, symlink escapes, null
    bytes).  Not recoverable: the path itself is hostile.
    """
    code = "path_traversal_blocked"
    recoverable = False
class PromptInjectionBlocked(HugrGateError):
    """A prompt-injection attempt was stopped at the boundary.
    Slice 414.  Raised by :mod:`hugrgate.security.prompt_injection`
    when untrusted content carries a high-confidence instruction-
    override attempt.  Not recoverable: the content is hostile.
    """
    code = "prompt_injection_blocked"
    recoverable = False
class ReplayDetected(HugrGateError):
    """A replayed or stale message was rejected.
    Slice 418.  Raised by :mod:`hugrgate.security.replay` when a
    nonce repeats inside the window, a timestamp is outside the
    freshness window, or a signed envelope fails verification.
    Not recoverable: the message itself is hostile or stale.
    """
    code = "replay_detected"
    recoverable = False
class AuthzDenied(HugrGateError):
    """An authorization check denied the request.
    Slice 419.  Raised by :mod:`hugrgate.security.authz` when a
    principal is unknown, presents a bad/revoked credential, or
    lacks the capability for the operation. Deny-by-default:
    anything not explicitly granted is denied. Not recoverable —
    the caller must obtain the right credential or capability.
    """
    code = "authz_denied"
    recoverable = False
class RateLimitExceeded(HugrGateError):
    """A per-key rate limit was exceeded.
    Slice 420.  Raised by :mod:`hugrgate.security.ratelimit` when a
    caller's token bucket is empty. Recoverable: the caller may
    retry after ``retry_after_ms``. Carries ``key`` (the throttled
    identity) and ``retry_after_ms`` in details.
    """
    code = "rate_limit_exceeded"
    recoverable = True
class ProtocolError(HugrGateError):
    """Wire-protocol violation (unknown/unsupported protocol version).

    Slice 426.  Deliberately *not* recoverable by blind retry: the
    client must upgrade (or downgrade) to a protocol version the
    service speaks.  Retrying the same bytes against the same
    service cannot succeed.
    """
    code = "protocol_error"
    recoverable = False


class SDKError(HugrGateError):
    """The Python SDK v2 client failed (transport down, bad response).

    Slice 428.  Recoverable: transient network or service faults can
    succeed on retry, and the SDK retries recoverable failures
    automatically.
    """
    code = "sdk_error"
    recoverable = True


class PluginError(HugrGateError):
    """A backend plugin failed to load, register, or validate.

    Slice 439.  Recoverable: plugins are isolated — a broken plugin
    never poisons the core runtime, and fixing or removing the
    plugin restores discovery.
    """
    code = "plugin_error"
    recoverable = True


class ConformanceError(HugrGateError):
    """A backend or contract failed its conformance battery.

    Slices 440-441.  Deliberately *not* recoverable: a conformance
    failure is a correctness signal about the plugin or template
    itself.  Fix the implementation, then re-run the kit.
    """
    code = "conformance_error"
    recoverable = False


class ConfigError(HugrGateError):
    """A generated or supplied configuration is invalid.

    Slice 437.  Deliberately *not* recoverable: the operator must
    fix the configuration (the generator never emits an invalid
    file, so this signals hand-editing or version skew).
    """
    code = "config_error"
    recoverable = False


class ScaffoldError(HugrGateError):
    """Project scaffolding failed (bad name, target exists, write error).

    Slice 438.  Deliberately *not* recoverable: the filesystem or
    project name must change before retrying.
    """
    code = "scaffold_error"
    recoverable = False
class AutotuneError(HugrGateError):
    """Base for all Campaign XIX autonomous-optimization failures.
    Slice 451. Tuning is advisory to the decision path: optimizer-side
    faults (a crashed tuner, a rejected proposal) are recoverable so a
    single bad tuner cannot halt the whole cycle.
    """
    code = "autotune_error"
    recoverable = True
class ObjectiveError(AutotuneError):
    """An objective specification is malformed or unusable.
    Slice 452. A bad objective (unknown metric, empty weights, wrong
    direction) is a caller/operator bug — not recoverable by retry.
    """
    code = "objective_error"
    recoverable = False
class ConstraintViolation(AutotuneError):
    """A proposed parameter change violated a declared constraint.
    Slice 453. The proposal is skipped and the tuner continues; the
    rejection itself is routine search behavior, hence recoverable.
    """
    code = "constraint_violation"
    recoverable = True
class TunerError(AutotuneError):
    """A tuner raised while producing a proposal.
    Slice 451. Recoverable: the controller logs, skips the tuner, and
    finishes the cycle with the remaining tuners.
    """
    code = "tuner_error"
    recoverable = True
class UnsafeProposalError(AutotuneError):
    """A proposal was blocked by optimizer safety limits.
    Slice 472. Not recoverable: the limits are the operator's stated
    policy — retrying the identical proposal cannot succeed.
    """
    code = "unsafe_proposal"
    recoverable = False
class RollbackError(AutotuneError):
    """An automatic rollback failed or left the config indeterminate.
    Slice 469. Not recoverable: a failed rollback is a pager-grade
    state-integrity problem, not a transient fault.
    """
    code = "rollback_error"
    recoverable = False
class ReproducibilityError(AutotuneError):
    """A tuning run could not be reproduced from its recorded seed.
    Slice 471. Not recoverable: non-reproducibility signals tampering
    or a broken recorder — fix the recorder, do not retry blindly.
    """
    code = "reproducibility_error"
    recoverable = False
class ParameterError(AutotuneError):
    """A tunable-parameter definition or value is invalid.
    Slice 451. Unknown parameter names, out-of-bounds values, and
    wrong-typed values are caller bugs — not recoverable by retry.
    """
    code = "parameter_error"
    recoverable = False
