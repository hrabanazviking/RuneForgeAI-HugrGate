# Slice 040 — Decision deadlines

## What existed before
- `DecisionPolicy.maximum_latency_ms`: bounds *backend* latency. The
  decision itself had no temporal contract — no time budgets, no validity
  windows.

## What changed
- **`hugrgate/contracts/deadlines.py`** (new, kind `"timed"`):
  - `TimedContract(DecisionContract)`: wraps any inner `DecisionContract`
    or v1 `DecisionSpec` with `budget_ms` (decide within X ms of the
    request), `not_before`/`not_after` (absolute unix-timestamp window).
    At least one bound required; `budget_ms > 0`; `not_before < not_after`.
  - `validate_value` delegates to the inner contract (v1 via the shared
    `_validate_spec_value` helper).
  - `timing_violations(request_ts, decided_ts)` — was it *made* in time
    (budget, window, causality); `check_timing` aggregates into one error.
  - `is_valid_at(now)` — is the decision still *valid* now; 
    `remaining_budget_ms(request_ts, now)` — ms left (None without budget).
  - All temporal checks take explicit timestamps (`now` defaults to
    `time.time()`), so tests run on a fixed clock — deterministic.
- **`hugrgate/contracts/__init__.py`**: lazy `deadlines` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Made-in-time vs still-valid are separate queries: a decision can be
  made within budget yet expire later (window), and vice versa.
- `exactly at budget` / `exactly at window edge` are OK (inclusive) —
  boundaries belong to the allowed region.

## Tests
- `tests/test_contracts_040.py`: 19 tests — in/over budget, window edges,
  validity, remaining budget (incl. negative = overdrawn), delegation to
  v1 and v2 inners, aggregated violations, all construction guards,
  round-trips.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/deadlines.py`, `tests/test_contracts_040.py`.
