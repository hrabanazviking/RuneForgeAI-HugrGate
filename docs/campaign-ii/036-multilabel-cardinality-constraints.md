# Slice 036 — Multilabel cardinality constraints

## What existed before
- `HierarchicalLabelContract` (029): membership only — every label known
  and unique. No cardinality ("pick 1–3"), no required/forbidden, no
  co-occurrence rules.

## What changed
- **`hugrgate/contracts/multilabel.py`** (new, kind
  `"multilabel-cardinality"`):
  - `MultilabelContract(DecisionContract)`: `labels`, `min_count` /
    `max_count` (`max_count=0` = unbounded), `exact_count` (−1 = unset,
    wins when set), `required`, `forbidden`, `implies` (label → required
    consequents), `excludes` (label → antagonists, symmetrized at
    construction since exclusion is mutual).
  - `violations(value)` aggregates *every* problem (unknown/duplicates,
    cardinality, missing required, forbidden present, broken implications,
    each conflicting exclusion pair once); `validate_value` raises one
    `ContractError` with all of them.
  - Construction coherence guards: counts in range, min ≤ max,
    required/forbidden ⊆ labels and disjoint, rules reference known
    labels, no self-rules, required labels can't exclude each other, and
    required can't exceed `exact_count`.
- **`hugrgate/contracts/__init__.py`**: lazy `multilabel` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Exclusion symmetrized at construction and persisted in symmetrized
  form — canonical, round-trips exactly, no silent asymmetry.
- `max_count=0` as "unbounded" documented on the field; `exact_count=-1`
  as "unset".

## Tests
- `tests/test_contracts_036.py`: 24 tests — valid selections, symmetrized
  exclusion, exact counts, implication chains, aggregated violations,
  string/duplicate/unknown rejections, and all construction guards.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/multilabel.py`, `tests/test_contracts_036.py`.
