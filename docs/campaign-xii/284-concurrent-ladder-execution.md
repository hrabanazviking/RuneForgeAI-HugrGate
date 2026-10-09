# Slice 284 — Concurrent ladder execution

**Status:** complete. Commit: `feat(gjallarbu-284)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

`LadderRouter.decide` (slices 31–32) climbed strictly sequentially: a
below-confidence rung paid its full latency before the next rung even
started. With N rungs the worst case summed all rung latencies.

## What was built

- `hugrgate/ladder.py` — `LadderRouter.decide_concurrent(state, spec,
  policy, context, max_workers=4)`:
  - **Phase 1 (sequential):** identical pre-run pruning
    (support/privacy/latency) — cheap, deterministic audit order.
  - **Phase 2 (ordered race):** surviving rungs evaluate in a
    `ThreadPoolExecutor`; futures are consumed in *ladder order* and
    the lowest-index rung clearing its gate wins — even when a higher
    rung finished first (verified by test).
  - The winner cancels stragglers; they are audited as
    `RUNG_CANCELLED` (reusing the slice-065 constant, not a new one).
  - Each worker fills a private audit list merged in ladder order —
    no shared mutation from threads. Provenance logging matches the
    sequential path rung-for-rung.
  - Exhaustion raises the same `Abstention(reason="ladder_exhausted")`;
    invalid `max_workers` raises `SpecError`; results carry
    `metadata["ladder_concurrent"] = True`.
  - Documented requirement: concurrently-used backends must be
    thread-safe.

## Tests

`tests/test_perf_284_ladder_concurrent.py` — 9 tests: ordered-race
(lowest sufficient wins over a faster higher rung; cancellation
audited), below-confidence climb, **measured latency overlap**
(concurrent climb < sequential sum), exhaustion abstention with trace,
pruning parity vs sequential `decide` (identical outcomes incl.
`RUNG_SKIPPED_LATENCY`), failed-rung climb, abstaining-rung climb,
`max_workers` validation, single-worker equivalence. Existing
`test_ladder.py` (62 tests) untouched and green. Ruff clean;
import-cycle test green.
