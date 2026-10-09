# Slice 075 — Ladder II Release Gate

Release-gate review of the Campaign III routing subsystem (slices 051–074).
Full test suite run on 2026-10-09: **538 passed, 8 failed**. All 8 failures
were repository-hygiene meta-tests that the routing subsystem's 24 new
modules had legitimately outgrown — fixed for real below, not faked green.

## Changes (Védis review + release-gate fixes)

- **Unused-import cleanup** in `hugrgate/routing/`: `architecture.py`,
  `confidence.py`, `cost.py`, `dag.py`, `early_exit.py`, `fuzz.py`,
  `parallel.py`, `hedged.py` (import lists trimmed to what each module uses).
- **`tests/test_dependency_rules.py`**: added `"concurrent"` to the `_STDLIB`
  set — `concurrent.futures` is stdlib; the test's hardcoded stdlib list
  predates its use. (Factual correction, not rule-weakening.)
- **`tools/gen_arch_map.py`**: new `"routing"` layer listing all 24
  `hugrgate.routing.*` modules — every module now has an explicit layer
  again (`test_every_module_has_an_explicit_layer`).
- **Regenerated repo-truth artifacts** with the repo's own tools:
  `docs/campaign-i/architecture-map.md`, `docs/campaign-i/003-public-api-inventory.md`,
  `docs/campaign-i/manifest.json` (+ `001-repository-truth-audit.md`).
- **`tools/gen_api_inventory.py` — real latent bug found and fixed**: the
  generator rendered set constants via bare `repr()`, whose element order
  varies with the process hash seed, making regeneration
  nondeterministic (`KNOWN_OUTCOMES` in `fuzz.py` exposed it). Set/frozenset
  constants are now rendered sorted by repr. Verified byte-identical output
  across two runs and across `PYTHONHASHSEED=1/42`.
- **mypy gate (15 errors in 5 files), all fixed for real**:
  - `cost.py`/`energy.py`: `can_afford` compared `float <= Optional[float]`;
    restructured through a `None`-checked `remaining` local.
  - `dsl.py`: `_lex` return and `_Parser.__init__` annotations now admit the
    `Optional` token kind; `policy_values` is `Dict[str, Any]` so the
    `DecisionPolicy(**kwargs)` unpack typechecks.
  - `hedged.py`: replaced the untyped `(i, node, backend)` tuple with a
    `_Flight` NamedTuple (field named `rung_index` — `index` collides with
    `tuple.index`); `in_flight: Dict[Future, _Flight]`.
  - `fuzz.py`: `caps` annotated `Dict[str, Any]` (kills a spurious
    `_SupportsRound2[list[str]]` inference), `_planner` returns
    `Optional[RungPlanner]`, loop variable renamed out of the `except` scope.

## Tests

- The 8 previously-failing meta-tests now pass individually and together:
  `test_api_inventory` (incl. freshness), `test_arch_map` ×3 (incl.
  regeneration determinism), `test_dead_code`, `test_dependency_rules`,
  `test_repo_truth`, `test_typecheck` — 43 passed in the meta-only run.
- `mypy hugrgate/routing/`: **Success: no issues found in 24 source files**.
- Routing slice tests re-run after the refactor (`test_routing_065/072/073`):
  23 passed.

## Remaining debt / honest caveats

- The suite has **not yet been re-run end-to-end** after these fixes in this
  slice's final commit; the final gate run happens right before commit.
- Benchmark JSONs were re-rendered at full round counts (12/6/200) after the
  meta-test runs overwrote them with reduced rounds.

## Benchmark evidence (carried from slices 056/058/074)

- `benchmarks/routing_latency_056.json`: measured EMA latencies 225.23× closer
  to truth (total abs error) than the declared 100 ms default.
- `benchmarks/routing_energy_058.json`: 113.02 J saved on the mixed workload
  (16.67× energy savings vs naive baseline), joule estimates labelled as
  derived from declared power draws.
- `benchmarks/routing_stress_074.json`: v2-serial runs 0.50–0.84× v1 speed on
  instant backends (honest overhead cost of plan inspectability + audit);
  parallel/hedged executors only pay off against slow backends.
