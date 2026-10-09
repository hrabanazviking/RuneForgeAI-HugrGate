# Slice 500 — HugrGate 1.0 release decision

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_500_release.py` (5 tests)

## The decision: RELEASE 1.0.0

`pyproject.toml` and `hugrgate.__version__` bumped `0.1.0` →
`1.0.0`, matching the freeze manifest's scheme (`1.0.0rc1` →
`1.0.0`). The service health test now asserts against
`hugrgate.__version__` instead of a hardcoded string so it can
never rot again. The release candidate was rebuilt and
re-verified at 1.0.0 (`tools/rc_build.py`: 5/5 checks).

## Full-suite verification

Final full run (`pytest -q -p no:cacheprovider`, this machine):
**5270 passed, 10 failed, 1 skipped** — then every failure was
triaged and fixed:

| Failure | Cause | Fix |
|---|---|---|
| `test_api_inventory::test_inventory_doc_is_fresh` | **generator nondeterminism**: `describe()` used raw `repr()` for dict constants, so nested frozensets (e.g. `ROLES`) rendered in hash order — the doc differed run to run | route constants through `_stable_repr` (dead code removed); proved byte-identical across `PYTHONHASHSEED` 0/1/42 |
| `test_sec_423_secscan` | my `tools/docs_exec_audit.py` used `compile()` — flagged as dynamic code exec | hardened to `ast.parse()` (syntax check needs no code object) |
| `test_repo_truth` | `docs/campaign-i/manifest.json` stale since before slice 476 (all gauntlet modules missing) | regenerated via `tools/audit_repo.py` |
| `test_perf_283_async_api` (2) | **real regression from slice 490**: hostile-backend containment swallowed `asyncio.CancelledError`, breaking `asyncio.wait_for` timeouts | `CancelledError` now propagates in both containment sites; 2 regression tests added to `test_gauntlet_490_hostile.py` |
| `test_arch_map` (3) | arch map predated the gauntlet package | added `gauntlet` layer to `tools/gen_arch_map.py`, regenerated |
| `test_package_boundaries` | `from hugrgate import …` inside `gauntlet/repro.py` (mine) and `gauntlet/soak.py` (488) | submodule imports |
| `test_errors` | hostile fixtures deliberately raise non-taxonomy errors | principled exclusion with comment |
| `test_dependency_rules` | `select`/`py_compile` stdlib entries missing | added to `_STDLIB` |
| `test_gauntlet_479_linux` | pinned count of guarded `resource` imports (3) missed slice 488's `soak.py` | count 3 → 4 |
| `test_gauntlet_486_api_audit` | baseline recorded mid-campaign (slice 486); 10 gauntlet modules added since | re-recorded `api-baseline-1.0.json` at the 1.0 tree (432 modules, no drift, non-breaking) |
| `test_sec_410_resource_guards` | **real test bug (slice 410)**: `RLIMIT_CPU` counts total process CPU; after a long suite run the process had already exceeded the absolute 60s budget, so arming the guard fired `SIGXCPU` immediately | budget armed relative to already-consumed CPU (`consumed + 60`); proven passing with 65s pre-burned |

After fixes, all affected suites re-run green; the release
checklist (`test_gauntlet_500_release.py`) passes: version 1.0.0
everywhere, all 25 slice docs present, taxonomy covers the new
modules, handoff package complete.

## Campaign XX gap review (476–499)

- Real bugs found and fixed by the gauntlet (not checkboxes):
  unguarded `SIGKILL` default (479→480), unenforced batch
  limits (492), stale `LadderRouter` doc API (496),
  `CancelledError` containment regression (490→500).
- Honest limitations: benchmark baseline numbers are
  machine-specific (the audit compares against bands, not
  absolutes); the license audit's full-venv mode flags
  `scipy`/`pathspec` (dev-only deps — correctly conservative,
  documented); doc snippets that are illustrative fragments are
  marked `# noexec` rather than deleted.
- No new error classes were added (no `ALL_ERRORS` promotion
  needed); no `benchmarks/*.json` artifacts committed;
  README.md untouched.

## Deliverables

25 slices, 25 commits on `gjallarbu/campaign-xx`:
`hugrgate/gauntlet/` gains `freeze`, `pymatrix`, `platforms`,
`deps`, `store_migrate`, `api_audit`, `racehunt`, `soak`,
`fuzz`, `hostile`, `partition`, `exhaustion`, `leakscan`,
`calibration_audit`, `repro`, `license_audit`; `tools/` gains
`docs_exec_audit.py`, `license_audit.py`, `rc_build.py`,
`precision_handoff_check.py`, `fresh_clone_install.sh`;
`docs/gauntlet/` holds all 25 slice notes plus the audit
handoff package.
