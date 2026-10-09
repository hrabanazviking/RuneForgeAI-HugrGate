# Slice 068 — Conditional routing DAGs

## What existed
Routing topologies were lines: serial ladders, parallel waves, hedged
primaries, fallback chains. No branching on the request itself.

## What changed
- **`hugrgate/routing/dag.py`** (new):
  - `evaluate_condition`: declarative conditions (`always`,
    `key_present`/`key_absent`, `spec_type`, `qos`/`qos_in`,
    `min_state_keys`, `all`/`any`/`not`) plus raw callables (marked
    non-serializable); unknown operators rejected.
  - `DAGNode`: named conditional rung (name ≠ backend — one backend
    can appear at several nodes); conditions validated eagerly.
  - `RoutingDAG`: `add_node`/`add_edge` with duplicate/self-loop/
    unknown-ref rejection; `validate()` via Kahn's algorithm raising
    `SpecError` on cycles or empty graphs; `roots()`, `to_dict()`.
  - `DAGExecutor`: topological walk — a node runs only when its
    condition holds (false conditions skip but still release
    successors); first gate-clear wins and stops the DAG; below-gate,
    abstain, error, and skip outcomes all release successors; each
    join runs exactly once.

## Integration
Drop-in `RungExecutor` (DAG via executor arg or `router.dag`);
`metadata["execution"] = "dag"`, `metadata["dag_node"]`, and the full
DAG in `metadata["dag"]`. Same validation/provenance/feedback path.

## Tests
`tests/test_routing_068.py` (9 tests): all condition operators +
invalid shapes, callable non-serializability, cycle/duplicate/
unknown-ref/empty rejection, roots, linear chain order + winner stops
DAG, false-condition skip with successor release, state-key routing
(PII scrubber vs plain), diamond join-once, exhausted abstention,
missing-DAG error.

## Evidence
- `pytest tests/test_routing_068.py` → 9 passed.
