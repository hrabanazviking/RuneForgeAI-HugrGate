# Slice 392 — Agent disagreement handling

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_392_disagreement.py` (6 tests)

## What already existed

Fusion (391) always crowns a winner — even at 51/49. Nothing
decided what *happens* about a split vote.

## What was built

- `hugrgate/agents/disagreement.py` — `DisagreementResolver`:
  `fuse` / `majority` / `highest_confidence` strategies fuse and
  mark `escalated=True` when disagreement exceeds the threshold
  (the caller moves the ticket up instead of acting on a split
  vote); `human_review` enqueues the vote slate to the review
  queue (385) and returns the review item id. Threshold is the
  honesty knob: 0.0 escalates on any dissent, 1.0 never.

## Verification

`pytest tests/test_agents_392_disagreement.py` — 6 passed
(split escalates, consensus doesn't, threshold extremes,
strategy mapping, human-review enqueue + stats). `ruff check`
clean, `mypy` clean.
