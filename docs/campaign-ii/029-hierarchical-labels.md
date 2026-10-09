# Slice 029 — Hierarchical labels

## What existed before
- `DecisionSpec(type="multilabel")`: flat label lists — `"siamese"` and
  `"animal"` unrelated strings; no ancestor semantics, no hierarchy-aware
  scoring.

## What changed
- **`hugrgate/contracts/hierarchy.py`** (new, kind `"hierarchical-labels"`):
  - `LabelHierarchy`: immutable label forest. Built via `from_edges`
    (`(parent, child)` pairs + optional isolated `nodes`) or `from_nested`.
    Guards: non-empty names, no self-parent, one parent per node (true
    forest), cycle detection via iterative DFS.
  - Queries: `ancestors` (root-down), `descendants`, `parent_of`,
    `children_of`, `depth_of`, `lowest_common_ancestor` (None across trees),
    `roots`, `leaves`, `labels`, `close` (ancestor closure), `edges`.
  - `HierarchicalLabelContract(DecisionContract)`: values are label
    collections; every label must be known, no duplicates; `close_value`
    expands with implied ancestors.
  - `hierarchical_precision` / `hierarchical_recall` over ancestor-closed
    sets — predicting a parent of the truth gets partial credit instead of
    all-or-nothing flat matching.
  - Full serialization round-trip (`edges` + isolated `labels`).
- **`hugrgate/contracts/__init__.py`**: lazy `hierarchy` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Forest, not DAG: one parent per label keeps LCA/closure unambiguous.
- A mid-development gap was found and fixed: isolated root labels (a
  single-label hierarchy) were unrepresentable because nodes only came
  from edges — `nodes`/`labels` support added with tests.

## Tests
- `tests/test_contracts_029.py`: 25 tests — nested/edge construction
  equivalence, all queries, LCA incl. cross-tree None, closure, metrics
  (exact, partial-credit, empty edge cases), round-trip, and every
  rejection mode (cycle, self-parent, multi-parent, unknown/duplicate
  labels, bad shapes, empty hierarchy).
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/hierarchy.py`, `tests/test_contracts_029.py`.
