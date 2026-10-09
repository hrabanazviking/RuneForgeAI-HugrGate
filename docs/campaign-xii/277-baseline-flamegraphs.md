# Slice 277 — Baseline flamegraphs

**Status:** complete. Commit: `feat(gjallarbu-277)` on `gjallarbu/campaign-xii`.

## What existed before

Slice 276 gave us cProfile integration (`DecisionProfiler`) but no way
to *see* the call tree. This slice adds flamegraph rendering on top of
the real pstats call graph — not a bolted-on sampling tool.

## What was built

- `hugrgate/flame.py` — new module:
  - `FoldedStacks.from_pstats(stats)` — exact tree walk from the pstats
    caller map (roots → leaves, recursion cycles cut); weights are
    **cumulative milliseconds, not samples**, stated in the SVG caption.
  - `FlameGraph.render_svg(stacks)` — self-contained SVG (no JS, no
    assets): proportional frames, per-frame tooltips with ms, warm
    hash-keyed palette, honest "profile flamegraph" caption.
  - `write_baseline(stacks, svg, dir, label)` — persists
    `{label}.folded`, `{label}.svg`, `{label}.json` (schema, host,
    HugrGate version, timestamp).
  - Validation errors raise `ProfilingError` (empty stats, empty stacks,
    bad dimensions).
- `hugrgate/profiling.py` — added `DecisionProfiler.profile_raw()` so
  flame consumers get the true pstats call graph; `profile()` now wraps
  it (no behavior change).
- `benchmarks/flamegraphs/decide-baseline.{folded,svg,json}` — real
  baseline artifact: 25 live `decide()` calls profiled on this host
  (98 stacks, ~11.4 ms cumulative). Regenerate with the snippet in the
  commit; the JSON stamps host + version so cross-host comparisons stay
  honest.

## Tests

`tests/test_perf_277_flame.py` — 12 tests: real call-tree folding (roots,
leaf weights, recursion termination), folded text format, SVG content
(frames, tooltips, caption), empty/bad-config rejection, baseline file
trio + metadata schema, end-to-end `decide()` → profile → flame →
baseline. All green; ruff clean; import-cycle test green.

## Bug found while implementing

pstats caller-map entries are 4-tuples `(cc, nc, tt, ct)`, not 5 — fixed
before any test passed; the recursion test guards the cycle-cut path.
