# Slice 050 — Contract Engine release gate

## The gate
Campaign II is done. This slice ran the release gate over all 25 slices
(026–050): full suite, regression review, dependency inspection, CHANGELOG,
README claim check, and the `HugrGate.decide` integration wiring.

## What changed
- **`hugrgate/core.py`**: `HugrGate.decide()` and `decide_batch()` now
  accept `DecisionSpec | DecisionContract`. A v2 contract with a v1
  equivalent is migrated at the boundary via the slice-047 engine; its
  `contract_id` rides in `result.metadata`. Contracts with no v1 path
  (cost-sensitive, risk, …) raise `ContractError(no_downgrade_path)`;
  non-specs raise `SpecError`. The v1 path is byte-for-byte unchanged.
  The contracts import is lazy — core stays importable without the
  contracts package.
- **`CHANGELOG.md`**: new "Contract Engine (2026-10-09)" entry covering
  all 25 slices.
- **`tests/test_contracts_050.py`**: 8 tests — v2 decide end-to-end,
  batch, v1 backward compat (no `contract_id` stamped), exotic-kind
  rejection, garbage-spec rejection, binary-contract loud failure,
  stdlib-only dependency inspection, top-level API snapshot.

## Gate evidence
- **Full suite**: 876 tests green (final count at commit), mypy clean
  (67 source files, zero errors).
- **Regression review** (`git diff 2523dc6..HEAD`): 80 files, +12,917 /
  −35. Every change is additive except: `hugrgate/errors.py` (+`ContractError`),
  `hugrgate/core.py` (this slice's wiring), `tools/gen_api_inventory.py`
  (memory-address sanitization — the generator was nondeterministic for
  any constant holding a function), `tools/gen_arch_map.py` (LAYERS
  entries), and 4 machine-regenerated docs. `hugrgate/__init__.py`
  untouched — the slice-003 public API snapshot holds.
- **Dependency inspection**: `hugrgate/contracts/` imports stdlib only
  (no third-party additions); import graph acyclic per `test_arch_map`.
- **README claims**: line 90 ("depends on the decision contract") and
  line 702 (typed v1 contracts) remain true; no new claims were added,
  no prose touched.
- **Fuzzer** (049): ~15k invariant checks across 5 seeds, 0 failures.

## Campaign II summary (slices 026–050)
| Slice | Module | Essence |
|---|---|---|
| 026 | schema | v2 contract schema, registry, canonical hash |
| 027 | negotiation | version negotiation, session agreements |
| 028 | nested | categorical trees, leaf paths |
| 029 | hierarchy | label forests, hierarchical P/R |
| 030 | composite | structured composites |
| 031 | conditional | fixpoint field activation |
| 032 | crossfield | declarative constraints |
| 033 | ordinal | anchors, interpolation |
| 034 | uncertainty | interval algebra |
| 035 | distributions | health constraints |
| 036 | multilabel | cardinality rules |
| 037 | cost | cost matrices, Bayes choice |
| 038 | utility | cost↔utility duality |
| 039 | risk | minimax, regret, CVaR |
| 040 | deadlines | budgets, time windows |
| 041 | context | context schemas |
| 042 | features | input feature contracts |
| 043 | explanations | faithfulness checks |
| 044 | inheritance | derive, compatibility |
| 045 | composition | merge, product, wrap |
| 046 | templates | `${param}` templates, library |
| 047 | migration | v1 ↔ v2, version registry |
| 048 | lint | 12+ checks, severities |
| 049 | fuzz | seeded property fuzzer |
| 050 | — | release gate, decide() wiring |

17 contract kinds, 24 modules, zero v1 breakage. The Contract Engine is
released.

## Standing notes for the coordinator
- Branch `gjallarbu/campaign-ii` is pushed; **do NOT merge** — the
  coordinator merges.
- Volmarr's standing order: after ALL big coding roadmaps finish, email
  volmarrwyrd@gmail.com stating completion. This campaign is one
  roadmap; the email goes out when the coordinator confirms every
  roadmap is done.
