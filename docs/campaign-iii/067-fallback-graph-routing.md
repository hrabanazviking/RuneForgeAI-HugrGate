# Slice 067 — Fallback graph routing

## What existed
On rung failure the ladder could only continue in linear plan order —
no way to say "on auth errors go local *now*, on rate limits go to the
patient backend".

## What changed
- **`hugrgate/routing/fallback.py`** (new):
  - `FallbackGraph`: `(backend, error-kind) → [fallbacks]` edges;
    error kinds are exception class names or `"*"`; `add_edge`
    rejects self-loops and empty kinds; `validate()` rejects directed
    cycles via DFS; `fallbacks()` returns specific edges before
    wildcard, deduplicated.
  - `FallbackGraphExecutor`: on rung failure, matching edges are
    followed *instead of* linear order (fallback rungs inherit the
    failed node's gate + latency budget and get fresh audit indices);
    unmatched errors climb linearly; a per-request visited set
    guarantees each backend is attempted at most once (runtime cycle
    guard); error kinds parsed from `_attempt` audit entries
    (`BackendUnavailable` / `BackendError` / `unexpected X` /
    `Abstention`).

## Integration
Drop-in `RungExecutor`; `metadata["execution"] = "fallback_graph"`,
`metadata["fallback_for"]` on graph-won results; same validation,
provenance, feedback, abstention path as other executors.

## Tests
`tests/test_routing_067.py` (9 tests): self-loop/empty-kind rejection,
static cycle detection, specific-before-wildcard ordering, graph
preempting linear order, unmatched-kind linear climb, wildcard match,
runtime cycle termination (each backend attempted exactly once),
gate inheritance by fallback rungs, default executor validation.

## Evidence
- `pytest tests/test_routing_067.py` → 9 passed.
