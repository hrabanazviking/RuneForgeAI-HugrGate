# Slice 043 — Output explanation contracts

## What existed before
- Explanations were ad-hoc `DecisionResult.metadata` keys: not required,
  not shaped, and never checked against the decided value.

## What changed
- **`hugrgate/contracts/explanations.py`** (new, kind `"explanation"`):
  - `ExplanationContract(DecisionContract)`: `required_fields`,
    `text_field`/`min_length`, `reasons_field`/`min_reasons` (non-empty
    strings counted), `must_mention_value` faithfulness, and
    `forbidden_phrases`.
  - `violations(value, explanation)` aggregates everything; 
    `validate_explanation` raises one error; `check_result` /
    `validate_result` read value + `metadata["explanation"]` straight off
    an unmodified `DecisionResult`.
- **`hugrgate/contracts/__init__.py`**: lazy `explanations` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Faithfulness uses **word-boundary** matching, not substring: tests caught
  that `"b" in "label"` would otherwise count as "mentioned". Forbidden
  phrases stay substring (strict direction for forbidding).
- Collection values require *every* element mentioned.

## Tests
- `tests/test_contracts_043.py`: 22 tests — all field/length/reason
  checks, faithfulness (incl. the substring trap, case-insensitivity,
  multilabel, numeric values), forbidden phrases, result integration,
  aggregation, construction guards, round-trips.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/explanations.py`, `tests/test_contracts_043.py`.
