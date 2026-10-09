# Slice 376 — Agent integration contract

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_376_contract.py` (20 tests)

## What already existed

No agent concept existed: HugrGate had backends, routers, decision
memory, observability tracing, and chaos experiments, but nothing
declaring *who* an agent is or what it may do. The nervous system
needed a trust anchor before any routing/gating slice could build on
it — hence shared substrate first.

## What was built

- `hugrgate/agents/__init__.py` — new package. Follows the
  `hugrgate.observability` convention: empty `__init__`, submodules
  imported individually, so importing the package never pulls the
  whole layer in.
- `hugrgate/agents/types.py` — shared vocabulary: `AgentSignal`
  (topic/payload/priority/trace_id/dedup_key, metadata-only payload
  rule), `AgentTicket` (budgets, trace + parent linkage, `child()`
  derivation), `AgentDelivery` (delivered/suppressed/dropped/errors).
- `hugrgate/agents/bus.py` — `EventBus`: exact/prefix/wildcard topic
  patterns, priority-ordered deterministic delivery, dedup windows,
  depth-based backpressure (`raise` → `BackpressureError`,
  `drop-oldest` → shed + count), handler-exception isolation (a dead
  handler can never kill the bus), thread-safe. **Hardening found
  during testing:** the first design tracked in-flight signals in a
  deque and corrupted it under re-entrant publish (inner publish
  popped the outer signal → `IndexError`); replaced with a depth
  counter in a `try/finally`.
- `hugrgate/agents/contract.py` — `AgentContract` (frozen dataclass):
  agent id, semver version, capabilities, intents, tools, input/output
  schemas, latency/cost/confidence SLOs, privacy-ladder clearance,
  escalation depth. `validate_contract()` returns violations
  (pure — registries and the release gate aggregate across agents);
  `assert_contract()` raises `AgentContractViolation` with details;
  `check_input()`/`check_output()` do structural field/type checks
  (`bool` is explicitly not `int`).
- `hugrgate/errors.py` — Campaign XVI error family:
  `AgentError` (base, recoverable), `AgentContractViolation`,
  `AgentNotFound`, `AgentLoopDetected`, `AgentRunaway`,
  `AgentBudgetExhausted`, `AgentEscalationFailed`,
  `HumanReviewTimeout` — each with stable `code` + deliberate
  `recoverable` flag, registered in `tests/test_errors.py`.

## Integration

- Privacy clearance validates against `hugrgate.privacy`'s
  `PRIVACY_CLASS_ORDER` (single source of truth for the ladder).
- Bus backpressure reuses `BackpressureError`; payload-metadata-only
  rule mirrors the observability alerting layer.
- No import cycles; package root untouched (package-boundary rule).

## Verification

`pytest tests/test_agents_376_contract.py tests/test_errors.py` —
32 passed. `ruff check` clean, `mypy` clean on new code.
