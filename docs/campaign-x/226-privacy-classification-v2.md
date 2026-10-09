# Slice 226 — Privacy classification v2

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_classification.py` (19 tests)

## What existed

`DecisionPolicy` accepted exactly two privacy classes (`standard`,
`strict`). `PrivacyGuard` enforced three binary rules: guard-level
remote forbid, `strict` never cached, `strict` provenance redacted.
There was no notion of *how sensitive* data is beyond that binary, no
minimum-trust requirement for backends, and a `strict` payload could
still flow to any remote backend the policy permitted — an unverified
third party could receive the most sensitive data the policy allowed
remotely.

## What changed

- `hugrgate/policy.py`: `DecisionPolicy.PRIVACY_CLASSES` is now the
  five-rung ladder `public < standard < sensitive < strict < forbidden`.
  Unknown classes (typos like `"strcit"`) are still rejected loudly —
  they never silently degrade.
- `hugrgate/privacy.py`: the ladder is machine-enforceable via
  `PRIVACY_CLASS_ORDER`, `TRUST_ORDER`, and `CLASS_SEMANTICS` (per
  class: minimum backend trust, cacheability, remote eligibility,
  provenance mode), plus helpers `class_rank`, `at_least`,
  `semantics_for`, `provenance_mode_for`, `trust_rank`,
  `default_trust_level`.
- `PrivacyGuard.remote_allowed` / `check_backend` now enforce class
  semantics: `forbidden`-class data can never reach a remote backend
  (even with `remote_inference=True` and guard mode `allow`), and
  `strict`-class data requires a `verified`-trust remote backend
  (attestation arrives in slice 229; until then, unattested remotes
  are `basic` and blocked).
- `PrivacyGuard.cache_allowed` now derives from the semantics table
  (`strict` and `forbidden` are non-cacheable).
- `hugrgate/core.py` and `hugrgate/ladder.py`: provenance redaction
  follows `provenance_mode_for(class)` instead of a hard-coded
  `== "strict"` comparison.

## Verification

- `pytest tests/test_privacy_classification.py` — 19 passed.
- Adversarial cases: class-typo rejection, `forbidden` + permissive
  policy + permissive guard still blocks remote, unattested remote +
  `strict` denied with a trust explanation.
- Backward compatibility: `standard` + remote behaves exactly as
  before; local backends are unaffected for every class.
- `ruff check` clean on touched files.
