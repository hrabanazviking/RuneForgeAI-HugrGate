# Slice 048 — Contract linting

## What existed before
- Validation proved contracts were *well-formed*, but degenerate-yet-
  valid configs (zero cost matrix, anchors never spanning the scale,
  single-field composite, constraint-free distribution) passed silently
  and did nothing in production.

## What changed
- **`hugrgate/contracts/lint.py`** (new):
  - `LintFinding(severity, code, message, contract_id)` — frozen;
    severities `info`/`warning`/`error` (`INFO`/`WARNING`/`ERROR`
    constants).
  - `LintReport` — `errors`/`warnings`/`infos`, `has_errors`, `clean`,
    `by_severity()`, one-line `describe()`.
  - `LINT_CHECKS` — an extensible registry of check functions
    (`register_check`, decorator-friendly); `lint_contract` runs them
    all, `lint_all` lints a fleet, `lint_template` checks parameter
    hygiene (unused/undocumented params).
  - Twelve checks: `undocumented`, `no_metadata`, `single_option`,
    `anchors_not_grounded/capped`, `default_anchors`, `zero_cost_matrix`
    (error), `nonzero_correct_cost`, `vacuous_width_guard`,
    `no_cardinality_rules`, `single_branch`, `all_features_optional`,
    `no_constraints`, `no_required_sections`, `window_in_past`,
    `window_already_open`.
- Every check was verified *reachable*: five first-draft checks
  (`empty_options`, `single_level`, `flat_anchors`, `point_interval`,
  `no_features`, `no_temporal_bound`) turned out to be rejected at
  construction and were replaced with degenerate configs construction
  actually allows.

## Design decisions
- Linting stays separate from validation: validation is total and
  blocking; lint is advisory with severities, so teams can gate deploys
  on `has_errors` while tolerating warnings.
- Custom house rules append to `LINT_CHECKS` — the linter is a
  framework, not a fixed list.

## Tests
- `tests/test_contracts_048.py`: 22 tests — every check's positive and
  negative case, report API, finding guards, custom-check registration.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/lint.py`, `tests/test_contracts_048.py`.
