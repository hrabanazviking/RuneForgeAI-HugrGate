# Slice 150 — Adaptive Routing release gate

**Status:** complete. Full suite green; integration review done; no
release blockers.

## Full test suite (real result)

```
726 tests: 724 passed, 2 failed → both fixed → re-run green
```

Command: `venv/bin/python -m pytest tests/ -q -p no:cacheprovider`
(final full run: **726 passed, 0 failed**, ~2 minutes).

The two failures found during the gate, and their fixes:

1. `test_dead_code.py::test_no_unused_imports_in_package` — 9 unused
   imports across 6 new adaptive modules (leftover `field`, `Optional`,
   `List`, `Mapping`, `Callable`, `CompetenceProfile`). Removed; no
   behavior change.
2. `test_repo_truth.py::test_audit_manifest_matches_live_tree` —
   `docs/campaign-i/manifest.json` (and the generated
   `001-repository-truth-audit.md`) predated the new package. Regenerated
   via `tools/audit_repo.py`, the sanctioned workflow.

Also regenerated (machine-generated, test-enforced):
- `docs/campaign-i/architecture-map.md` (new `adaptive` layer, 220 edges)
- `docs/campaign-i/003-public-api-inventory.md` (68 modules, 318 names)

`mypy hugrgate --check-untyped-defs`: clean (25 adaptive files; 3
narrowing issues found and fixed during the campaign).

## Integration review of slices 126–149

- **No stubs / TODOs / placeholders**: grep over `hugrgate/adaptive/`
  finds none. Two `pragma: no cover` marks are defensive
  internal-consistency guards (feature-column completeness, version
  lineage cycle), not untested behavior.
- **No duplicated architecture**: the adaptive package sits *above* the
  contracts layer and *beside* Campaign III's `hugrgate/routing/`
  (separate branch, to be united at merge). It reuses — not copies —
  `DecisionSpec`/`DecisionResult`/`DecisionPolicy`/`Backend`,
  `FeatureExtractor`, `ProvenanceStore` semantics, `PrivacyGuard`
  semantics, and `hugrgate.drift` PSI. `RoutingCandidate` is the one new
  shared contract, defined once in slice 132 and imported by 133–136.
- **Acyclic imports**: verified by `test_arch_map` (eager graph acyclic).
- **Backward compatibility**: top-level `hugrgate/__init__.py` untouched;
  `PACKAGE_API_SNAPSHOT` unchanged; base install stays stdlib-only
  (no numpy import anywhere in the package — LinUCB is pure Python).
- **Documentation drift**: all 25 completion notes' test counts verified
  against actual collection (269 adaptive tests total); benchmark numbers
  in the slice-149 note read from the checked-in artifact.

## Artifacts delivered

- `hugrgate/adaptive/`: 25 modules (`__init__` + 24 slice modules),
  ~3,900 lines, stdlib-only.
- `tests/test_adaptive_*.py`: 24 files, 269 tests, all green.
- `docs/campaign-vi/126-…-150-*.md`: 25 completion notes.
- `docs/campaign-vi/artifacts/adaptive-routing-benchmark.json`: full
  2000-round benchmark artifact (adaptive 0.8820 vs uniform 0.5840,
  round_robin 0.5764, static_first 0.5991).

## Remaining debt / notes for the coordinator

- Merge coordination: this branch adds `hugrgate/adaptive/`; Campaign
  III's branch adds `hugrgate/routing/`. The adaptive package was designed
  for the union (it references routing concepts only via the shared
  contracts layer), but the merge should wire the bandit into an actual
  `LadderRouterV2` decision path as a follow-up.
- `TelemetryStore` file I/O is synchronous; at very high decision rates
  the JSONL append could become a bottleneck — a batched/async writer is
  future work, not a blocker.
- No blockers. The campaign is releasable.
