# Slice 062 — Availability-aware routing

## What existed
The ladder retried dead backends on every request: `BackendUnavailable`
was audited and climbed past, but nothing remembered the failure, so
the next request paid the same latency again.

## What changed
- **`hugrgate/routing/availability.py`** (new):
  - `AvailabilityTracker`: per-backend circuit breaker — closed →
    open after `failure_threshold` (3) consecutive failures →
    half-open after `cooldown_s` (60s) → closed on trial success.
    Success resets the counter. Also consults `backend.health()`:
    non-`ok` status or a raising health check means unavailable.
  - `AvailabilityAwarePlanner`: prunes unavailable rungs at plan time,
    stamping `params["availability"]`.
- **`hugrgate/routing/architecture.py`**: `LadderRouterV2` accepts
  `availability_tracker=`; `note_availability(name, succeeded)` feeds
  the breaker; `SerialPlanExecutor` records failure only for
  `RUNG_UNAVAILABLE`/`RUNG_ERROR` — polite `Abstention`s and
  below-gate results don't trip the breaker (a working backend that
  declines is not a broken backend).

## Integration
Composes with the other aware-planners by wrapping; run-time `_attempt`
handling unchanged.

## Tests
`tests/test_routing_062.py` (9 tests): open-after-threshold,
half-open trial after cooldown (real 60ms sleep), re-open on trial
failure, success reset, arg validation, health pruning (degraded
status, raising check), plan-time pruning, router feedback opening the
circuit over two rounds, open-circuit plan skipping the dead backend
(zero calls), abstention neutrality.

## Evidence
- `pytest tests/test_routing_062.py` → 9 passed.
