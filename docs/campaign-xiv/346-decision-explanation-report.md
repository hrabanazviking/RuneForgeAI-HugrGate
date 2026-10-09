# Slice 346 — Decision explanation report

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_explain_replay.py` (14 tests)

## What existed

Provenance told you *what* was decided and traces told you *how
long*, but nothing joined them into a *why*. Worse, this slice
found a real gap: `DecisionRecord.from_decision` **dropped**
`result.metadata`, losing the machine-readable verdict
(`policy_verdict`) and abstention reason downstream consumers need.

## What changed

- `hugrgate/observability/explain.py`: `DecisionExplainer` joins a
  `DecisionRecord` with trace spans into an `ExplanationReport` —
  verdict summary, policy reasoning (threshold vs. probability band,
  review bands, abstention reasons), span timeline, fallback chain,
  explicit caveats (uncalibrated confidence, unsealed provenance,
  fallback engagement). Markdown rendering included. The decision
  value is **redacted by default** (`include_value=True` required)
  because explanations get pasted into tickets and dashboards.
- `hugrgate/provenance.py` (hardening): `from_decision` now merges
  `result.metadata` into the record (operational metadata, not input
  payload) instead of dropping it. Additive and backward-compatible
  — no existing test pinned the old behavior.

## Verification

14 tests (accept/abstain/review paths, redaction default, fallback
chain, timeline inclusion); existing provenance + privacy suites
still green; `ruff`/`mypy` clean.
