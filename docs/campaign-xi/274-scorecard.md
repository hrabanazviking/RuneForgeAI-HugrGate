# Slice 274 — Reliability scorecard

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_scorecard.py` (6 tests, green)

## What existed before

Six reporting shapes (experiment reports, dependency-matrix
dicts, degradation/recovery/soak/crash reports) with no unified
verdict. A release gate (slice 275) needs one page that says
PASS or FAIL — and *why*.

## What was built

**`hugrgate/chaos/scorecard.py`** (new module, exported from
`hugrgate.chaos`):

- **`ScorecardEntry`** — name, category, passed, note, weight
  (> 0), waiver fields; validated.
- **`Scorecard`** — `add()` (duplicates rejected), explicit
  **`waive(name, reason)`** (unknown/passing/already-waived
  entries rejected; the waiver and reason stay visible — nothing
  is silently dropped), and one adapter per campaign report
  shape: `add_experiment`, `add_dependency_matrix`,
  `add_degradation`, `add_recovery`, `add_soak`, `add_crash`.
- **`ScorecardReport`** — weighted `score`, letter `grade`
  (A≥95%, B≥85%, C≥70%, D≥50%, F below), `failed`/`waived`
  lists, JSON `to_dict()`, and a human-readable `render()`.
- **Verdict is strict by default** (`threshold=1.0`): chaos
  findings are release-blockers until fixed or explicitly
  waived, with the waiver auditable in the report.

## Verification

- 6 tests: entry/scorecard validation, all-passing card
  (verdict PASS, score 1.0, grade A, rendered page contains the
  entries), weighted failure (1 of 4 → score 0.25, grade F),
  waiver lifecycle (unknown/blank-reason/double-waive
  rejected; waiver visible but history not rewritten),
  grade bands + threshold boundary, and all six adapters on
  real report shapes (including a real `dependency_failure_matrix()`
  run and a real degradation-plan execution).
- `ruff check` clean. During testing, two real API-design
  fixes: `waive` on an already-waived entry now raises
  (distinct from already-passed), and `add_dependency_matrix`
  takes an optional `name` so multiple matrices can be scored.
