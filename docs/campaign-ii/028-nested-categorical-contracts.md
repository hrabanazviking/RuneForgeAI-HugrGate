# Slice 028 — Nested categorical contracts

## What existed before
- `DecisionSpec(type="categorical")`: flat option lists only — no way to
  express "pick a category, then refine within it".

## What changed
- **`hugrgate/contracts/nested.py`** (new, kind `"nested-categorical"`):
  - `NestedCategoricalContract(DecisionContract)`: `options: List[str]` +
    `children: Dict[str, NestedCategoricalContract]` (child keys ⊆ options).
  - Values are paths — tuples/lists of strings or dotted strings
    (`"animal.mammal.dog"`) — normalized by `parse_path`; `validate_value`
    walks the tree: unknown options, trailing segments past a leaf, and
    paths ending at a branch are all `ContractError`s.
  - Structure API: `depth()`, `leaf_paths()` (every root-to-leaf path),
    `is_leaf()`, `subcontract_at(path)`.
  - Guards: ≥1 unique dot-free options, children ⊆ options, children are
    nested-categorical contracts, depth ≤ `MAX_NESTING_DEPTH` (8).
  - Full `_payload_dict` / `_from_payload` round-trip incl. nested children;
    `canonical_hash` stable across round-trips.
- **`hugrgate/contracts/__init__.py`**: lazy `nested` submodule access.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Deliberately *pure* recursive categorical trees: children must be
  nested-categorical contracts. Heterogeneous children (e.g. an option
  refining into a numeric contract) belong to slice 030 (composite
  decisions); keeping 028 pure preserves clean path semantics where every
  segment is an option string.
- A valid decision is always a root-to-leaf path — a path stopping at a
  branch is incomplete and rejected (`path_ends_at_branch`).

## Tests
- `tests/test_contracts_028.py`: 23 tests — tuple/dotted/list values,
  leaf enumeration, depth, subtree lookup, round-trip + hash stability,
  all rejection modes, and the depth bound (exactly 8 OK, 9 rejected).
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/nested.py`, `tests/test_contracts_028.py`.
