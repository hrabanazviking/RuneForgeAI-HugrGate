# Slice 042 — Input feature contracts

## What existed before
- `hugrgate/features.py`: extractors produce flat `{name: float}` dicts
  with no input contract — no required features, dtypes, ranges, or
  missing/extra policy. Garbage in, model out.

## What changed
- **`hugrgate/contracts/features.py`** (new, kind `"input-features"`):
  - `FeatureSpec(name, dtype, required, minimum/maximum, categories,
    default)` — frozen; dtypes `float`/`int`/`bool`/`category` with a
    deliberate dtype matrix (`True` is not a number, `3.0` is not an int,
    ints accepted for float); ranges on numerics only; categories on
    categoricals only; defaults validated against the spec itself.
  - `FeatureContract(DecisionContract)`: `violations` aggregates missing/
    mistyped/out-of-range/unknown-category/extra; `select(mapping)`
    projects onto the declared column order, fills defaults, and drops
    (or rejects) extras per `allow_extra` — the clean dict a backend can
    consume.
- **`hugrgate/contracts/__init__.py`**: lazy `features` submodule (no
  clash with the existing `hugrgate.features` extractor module).
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Defaults are validated at construction: a bad default is a contract
  bug, caught once, not a runtime surprise per decision.
- `select` raises on any violation before projecting — projection never
  launders bad input.

## Tests
- `tests/test_contracts_042.py`: 24 tests — dtype matrix (8 cases),
  ranges incl. boundaries, categories, required/defaults/extras,
  aggregation, column-order projection, and all construction guards.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/features.py`, `tests/test_contracts_042.py`.
