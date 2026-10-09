# Slice 100 — Calibration Forge release gate

## Full suite result
`~/workspace/RuneForgeAI-HugrGate/venv/bin/python -m pytest tests/ -q
--no-header -p no:cacheprovider` on the merged tree (campaign-iv +
origin/main slices 016–020): **586 passed, 0 failed** (121.7s). The one
warning is a pre-existing FastAPI/httpx deprecation notice, unrelated.

## Regressions found and resolved during the gate
1. **Unused imports** (`test_dead_code`): removed `math` from
   `aleatoric.py`/`decomposition.py`, `field` from `autoselect.py`,
   `List` from `coverage.py`/`decomposition.py`/`epistemic.py`/`window.py`.
2. **Layering** (`test_dependency_rules`): `epistemic` → `abstain` is
   legitimate (core domain module, precedent: `threshold.py`); added
   `hugrgate.abstain` to `CALIB_ALLOWED` with a justifying comment.
3. **Stale test expectation**: `test_auto_select_picks_winner` now
   includes `ensemble` in the default candidates.
4. **Doc drift**: regenerated `docs/campaign-i/manifest.json`,
   `001-repository-truth-audit.md`, `003-public-api-inventory.md`
   (67 modules, 290 public names), `architecture-map.md` (24 new
   calibration modules assigned to the `calibration` layer in
   `tools/gen_arch_map.py`).
5. **mypy**: fixed 4 errors (`autoselect` ranking type, `group`
   metrics type); repo-wide mypy clean (67 files).
6. **Import-order bug** (caught by slice-092 tests): `register()` calls
   moved above submodule imports in `calibration/__init__.py`.

## Integration review (slices 076–099)
- No stubs, TODOs, or placeholder code in any new module (grep-verified).
- Deduplicated the conformal `⌈(n+1)(1−α)⌉/n` quantile helper
  (`conformal_regression` now imports it from `conformal`); the weighted
  PAV in `online.py` stays separate from isotonic's unweighted PAV
  (different semantics, documented).
- `docs/calibration.md` gained a "Calibration Forge" section (append-only;
  no existing prose touched). Per-slice notes: `docs/campaign-iv/076`–`099`.
- `benchmarks/calibration_500.json`: 24 measured dataset×calibrator cells.

## Remaining debt / blockers
- None release-blocking. Known limitations (documented in slice notes):
  pipeline before/after metrics are in-sample (pair with slice-092 CV);
  ECE is not a proper scoring rule and can wiggle under attack (Brier is
  the stress signal); conformal guarantees need exchangeability;
  `beta-binomial` is a labeled research adapter.
- `origin/main` advanced (slices 016–020) during the campaign; merged
  into `gjallarbu/campaign-iv` as merge commit `8f8f6ed` (no conflicts,
  no force-push).

## Verdict
Campaign IV is complete and green. The branch is pushed as
`gjallarbu/campaign-iv`; **not** merged to main (coordinator merges).
