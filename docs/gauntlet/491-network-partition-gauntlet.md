# Slice 491 — Network partition gauntlet

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_491_partition.py` (5 tests)

## What existed

`hugrgate/chaos/network.py` simulated partitions, but nothing
proved the *decision path* stayed fail-closed under them end to
end.

## What changed

- `hugrgate/gauntlet/partition.py` (new): `snapshot_policy()` /
  `assert_policy_intact()` (network events must never silently
  weaken policy), `run_partition_scenario()` driving the
  up → partitioned → healed phases through a caller-supplied
  decide callable, `PartitionReport.fail_closed_ok`.

## Verification

`pytest tests/test_gauntlet_491_partition.py` green: partitioned
remote fails fast with `BackendUnavailable` (phase outcomes
`ok/unavailable/ok`), the policy object is field-identical before
and after, partial failure leaves the reachable host serving, and
a hostile policy mutation is caught by the intactness assertion;
`ruff`/`mypy` clean.
