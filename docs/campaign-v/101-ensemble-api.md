# Slice 101 — Ensemble API

**Status:** complete · **Commit:** `feat(gjallarbu-101): ensemble API`

## Skald (inspect)
No ensemble code existed. The repo had all the primitives: `Backend`
ABC + `BackendRegistry` (slice 6), `DecisionResult` with the
distribution/probability consistency invariant (slice 4, hardened 012),
`DecisionPolicy`, `ProvenanceStore` with hash-chained records (slices
9, 015), `validate_result`/`validate_state` (slices 7, 011), and the
`abstain`/`mark_for_review` vocabulary (slice 15). The natural design:
`Ensemble` **is a `Backend`** — it composes member backends and plugs
into `HugrGate.decide`, policy, provenance, and the HTTP/daemon layers
with zero special casing.

## Rúnhild (design)
New subpackage `hugrgate/ensemble/` ("ensemble" layer in the arch map):
- `base.py` — `MemberVote` (ballot or recorded failure), `collect_votes`
  (per-member fault isolation: abstain/fail/contract-violation/
  unsupported-spec/unexpected-exception → skipped + named, never fatal;
  `BackendError` only when usable votes < `min_members`),
  `finalize_result` (builds the `DecisionResult` + shared
  `metadata["ensemble"]` contract: strategy, ballots, normalized
  weights, winner share, **minority report present from day one**),
  `normalize_weights`, `break_tie` (total deterministic order:
  score → earliest ballot → lexicographic), entropy helpers.
- `api.py` — `STRATEGIES` registry + `register_strategy`/`get_strategy`,
  `EnsembleConfig`, `Ensemble(Backend)` with `evaluate`, `decide_batch`,
  `member_votes` introspection. Weights validated eagerly at
  construction. Emits `soft` by default.
- `voting.py` — reference `soft_voting` combiner (average member
  distributions, argmax wins, uncertainty = normalized entropy).
- `__init__.py` — public surface (top-level `hugrgate.__all__`
  deliberately untouched: the slice-003 snapshot test forbids changes).

## Eldra (code)
Real code, no stubs. Voting strategies restricted to discrete specs
(categorical/binary/ordinal) via `require_discrete_spec`; numeric and
multilabel raise `BackendError` with a clear message.

## Sólrún (tests)
`tests/test_ensemble_101_api.py` — 25 tests green:
success (soft-vote averaging math, metadata contract, deterministic
tie-break, custom strategy registration, `HugrGate.decide` + provenance
integration, `member_votes`, `supports`, batch passthrough),
failure (failing member skipped, all-fail → `BackendError`,
`min_members` enforced, abstaining/unsupported members skipped,
unknown strategy fails fast),
boundary (empty/duplicate/non-Backend members, bad weights incl. NaN,
`min_members=0`, `register_strategy` validation, `break_tie` total
order, numeric spec rejection).
Shared doubles in `tests/ensemble_fakes.py`
(`ConstantBackend`, `ScriptedBackend`, `FailingBackend`,
`AbstainingBackend`, `FnBackend`); imported as `from ensemble_fakes
import …` with `ensemble_fakes` added to `_LOCAL_MODULES` in
`tests/test_dependency_rules.py` (the sanctioned sys.path-trick slot).

## Védis (integrate)
- `tools/gen_arch_map.py`: new `"ensemble"` layer (all 22 planned
  campaign-V modules pre-registered); regenerated
  `docs/campaign-i/architecture-map.md` and
  `docs/campaign-i/003-public-api-inventory.md` via the sanctioned
  generator scripts.
- Repo meta-tests green: api-inventory (incl. `__all__` contracts,
  append-only surface, doc freshness), arch-map (layer assignment,
  determinism, acyclicity), dead-code (also fixed one unused import),
  dependency-rules (no service-layer leaks, third-party coverage),
  mypy clean.

## Scribe
Committed `feat(gjallarbu-101): ensemble API`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/__init__.py`, `base.py`, `api.py`, `voting.py`
- `tests/ensemble_fakes.py`, `tests/test_ensemble_101_api.py`
- `tools/gen_arch_map.py` (ensemble layer), regenerated
  `docs/campaign-i/architecture-map.md`,
  `docs/campaign-i/003-public-api-inventory.md`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_101_api.py -q` → 25 passed
- `venv/bin/python -m pytest tests/test_api_inventory.py tests/test_arch_map.py tests/test_dead_code.py tests/test_dependency_rules.py -q` → all pass
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
- `venv/bin/python tools/gen_arch_map.py`, `venv/bin/python tools/gen_api_inventory.py`
