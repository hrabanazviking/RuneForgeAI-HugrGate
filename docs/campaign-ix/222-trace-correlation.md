# Slice 222 — Trace correlation

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_trace.py`
(22 tests)

## What existed before

Every envelope carried a `trace_id` and `TRACE_SPAN` existed in the
protocol, but nothing assembled them: no spans, no parent/child
links, no collector — a cross-node decision left no traceable trail.

## What was built

- `hugrgate/cluster/trace.py`:
  - `TraceContext` — `(trace_id, span_id, parent_span_id, node_id)`;
    `root()` / `child()`, strict `to_dict`/`from_dict` (32/16-hex
    validation).
  - `Span` — operation, wall-clock timing, `ok`/`error`/`abstained`
    status, attributes; `finish()` records into its collector and
    returns duration.
  - `TraceCollector` — per-node span sink: `start`/`record`,
    `spans_for(trace_id)` in time order, `trace_tree(trace_id)`
    assembling nested parent/child forests across nodes; bounded
    with oldest-first eviction; `clear()`.
- `hugrgate/cluster/node.py`: every node owns `node.traces`;
  `decide_remote` records a `cluster.decide_remote` client span and
  propagates its context on the wire (`"trace"` payload key,
  additive); `handle_decide` records a `cluster.handle_decide` server
  span as a child of the caller's context, attributed to the serving
  node; `handle_trace_span` accepts pushed spans. A malformed
  incoming context never fails the decision — correlation is best
  effort.
- `hugrgate/cluster/rpc.py`: `decide(..., trace=...)` propagation;
  `send_spans(peer, spans)` push with server receipt count.

## Roles

Skald: trace_id audited — carried everywhere, assembled nowhere.
Rúnhild: context propagation + span assembly + push collection.
Eldra: forged. Sólrún: 22 tests green (context/span roundtrips,
tree nesting incl. orphans, eviction, client→server span linkage
across loopback with correct node attribution, span push).
Védis: exports, taxonomy, arch-map, manifest, inventory regenerated.
Scribe: committed `feat(gjallarbu-222)`.

## Verification

`pytest tests/test_cluster_trace.py` — 22 passed; ruff clean; mypy
clean.
