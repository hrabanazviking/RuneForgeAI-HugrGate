# Slice 391 — Agent confidence fusion

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_391_fusion.py` (8 tests)

## What already existed

`hugrgate.ensemble` fuses *backend* votes; dispatch (386) fans
out to *agents* with no reconciliation of their answers.

## What was built

- `hugrgate/agents/fusion.py` — `fuse_confidences(votes,
  method=...)`: `weighted` (mass = Σ weight·confidence, fused
  confidence = supporter-weighted mean), `majority` (one agent
  one vote; ties → higher total confidence → lexicographic),
  `max_conf` (most confident vote wins). `disagreement(votes)`
  scores 0..1 vote split (`1 − winner_mass/total_mass`) for the
  disagreement handler (392). Zero-mass and empty votes are
  `ValueError`; all tie-breaks deterministic.

## Verification

`pytest tests/test_agents_391_fusion.py` — 8 passed (weighted
mass math, heavy-minority win, majority ignoring weights, tie
determinism, disagreement scale, validation). `ruff check`
clean, `mypy` clean.
