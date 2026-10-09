# Slice 200 — Edge Intelligence Release Gate

**Campaign VIII, slice 200 of 200.** The campaign's Definition of Done,
made executable.

## What was built

**`hugrgate/edge/gate.py`** — `edge_release_gate(repo_root)` runs eight
checks and returns a `GateReport` (per-check pass/fail, blockers list,
`summary()`, `to_dict()`):

| Check | What it verifies |
|---|---|
| `test-suite` | Full pytest suite via subprocess — the **real** result, recorded |
| `ruff` | Lint clean over `hugrgate/`, `tests/`, `tools/` |
| `mypy` | Type check clean over `hugrgate/` |
| `chaos` | All six built-in fault scenarios green |
| `slice-docs` | All 25 campaign docs (`176`–`200`) present and non-trivial |
| `benchmark-artifacts` | Every `benchmarks/edge/*.json` loads under `edge-bench/1` |
| `stub-scan` | No unfinished-work markers in `hugrgate/edge/` |
| `maps-fresh` | Arch map + API inventory regenerate byte-identically |

Checks are selectable (`only=[...]`); unknown names raise `GateError`.
A failed check becomes a *blocker* — the gate never passes on visited
labels alone.

**`hugrgate/edge/__init__.py`** — the campaign facade: 109 curated
exports (every submodule's full `__all__`), so `from hugrgate.edge
import ThermalGovernor` works at the campaign surface.

## Integration-gap review (slice 200 criterion 2)

Running the gate against the real tree surfaced **four pre-existing
campaign failures** (slices 176–199 had claimed full-suite green, but
the committed tree at slice 199 failed 4 gate tests) plus 2 new ones
from this slice's facade. All fixed here:

1. **Import cycle** (`hugrgate.edge` → `bench` → `hugrgate.edge`):
   `bench.py` did `from hugrgate.edge import quant` inside a function.
   Now `import hugrgate.edge.quant as _quant` (submodule, not package).
2. **Package boundary**: `bench.py` did `from hugrgate import
   DecisionPolicy, DecisionSpec, HugrGate`. Now imports from the
   defining modules (`hugrgate.core`, `hugrgate.policy`,
   `hugrgate.spec`) — exactly what the boundary rule wants.
3. **Error taxonomy promotion**: all 15 edge error classes were raised
   but lived outside the taxonomy, violating the raise-sites contract.
   Promoted into `hugrgate/errors.py` with unique `edge_*` codes and
   deliberate `recoverable` flags; edge modules re-export the same
   class objects (backward compatible). `tests/test_errors.py` extended
   with all 15 (codes, recoverable, wire round-trip cases).
4. **Dependency declarations**: `glob`/`struct`/`zlib` added to the
   test's stdlib allowlist; lazy vendor SDK imports (`hailo_platform`,
   `tensorrt`, `openvino`) declared via a new `npu` extra in
   `pyproject.toml` (`hailort`, `tensorrt`, `openvino`).
5. **Stale generated docs**: architecture map, API inventory, and the
   campaign-i audit manifest regenerated.

The scanner also caught its own reflection: the stub-scan regex
contained the literal marker words, so the gate flagged `gate.py`
itself. The pattern is now built from fragments.

## Recoverable-flag rationale (deliberate per class)

`True` where retrying after a changed environment can plausibly
succeed: affinity (OS may free the CPU), benchmark (install the extra),
memory/residency/storage/power (free, shed, compact, retry), NPU
(hardware may appear; CPU fallback), recovery (retry the write).
`False` where the caller must fix the request: bootstrap (structural
law), cache/quant/telemetry/watchdog (invalid arguments), chaos
(harness bug), gate (unknown check name).

## Needs hardware validation

`edge_release_gate` runs entirely on this host. The `chaos` and
benchmark checks exercise abstractions, not silicon — same
`NEEDS_HARDWARE_VALIDATION` caveat as the rest of the campaign.

## Tests

`tests/test_edge_gate.py` — 8 tests: report mechanics, unknown-check
rejection, fast checks against a fixture skeleton (docs missing/trivial,
stub markers, bad artifacts), the real chaos check (6/6), check ordering.
