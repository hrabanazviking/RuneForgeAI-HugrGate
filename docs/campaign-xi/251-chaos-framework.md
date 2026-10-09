# Slice 251 — Chaos framework

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_framework.py` (19 tests, green)

## What existed before

Campaign VIII gave us `hugrgate/edge/chaos.py` — a `ChaosRunner`
executing named `FaultScenario`s against edge-device components — and
Campaign IX gave us `hugrgate/cluster/chaos.py` — a seeded network
fault proxy. Both were domain-specific harnesses with no shared
experiment discipline: no stated hypothesis, no definition of
"healthy" before/after, no safety interlock on what may be touched,
and no separation between "the injector crashed" and "the
verification failed".

## What was built

`hugrgate/chaos/` — the unified experiment framework:

- **`ChaosExperiment`** — a falsifiable claim: `hypothesis` (required,
  non-empty), `faults`, `probes`, `blast_radius`, `seed`. Duplicate
  fault names and empty experiments are rejected at construction
  with `ChaosError`.
- **`Fault`** — `inject` / `verify` / `rollback` as *separate*
  callables. A broken injector can no longer masquerade as a passing
  verification; each phase's outcome is recorded independently in
  `FaultResult` (`injected`, `verified`, `rolled_back`).
- **`SteadyStateProbe`** — named health definitions run before any
  fault and again after the last rollback. A delta (healthy → broken)
  fails the experiment even when every fault "passed": the experiment
  leaked damage. A probe that raises becomes a not-ok outcome, never
  an abort.
- **`BlastRadius`** — allow-list of target names; anything else raises
  `ChaosError` before injection. `dry_run=True` rehearses the whole
  experiment (verify + rollback) without ever injecting.
- **`ExperimentRunner`** — executes experiments, records every
  outcome, never aborts mid-run. Each fault gets a fresh context
  carrying a seeded `random.Random` under `"rng"`, so fault sequences
  are reproducible. Reports are JSON-serializable.

## Hardening of the existing code (Yrsa Law 11)

`hugrgate/edge/chaos.py` was attacked, not duplicated:

- `FaultScenario` gained optional `pre_check` / `post_check`
  steady-state hooks. A failing pre-check fails the scenario *before*
  injection (verification against an unhealthy world is meaningless);
  a failing post-check fails it *after* the callable passed (the
  fault leaked damage).
- `ChaosRunner.run_one(name)` executes a single scenario;
  unknown names raise `ChaosError`.
- `ChaosResult.to_dict()` is byte-identical (pinned by
  `test_result_serializes`); all hardening is additive.

## Integration

- Error semantics: all misuse raises `ChaosError` (`code
  "edge_chaos_error"`, not recoverable — a failed verification is not
  retryable).
- Provenance: `ExperimentReport.to_dict()` carries experiment name,
  hypothesis, target, seed, dry-run flag, steady-state before/after,
  per-fault results, and duration — everything needed to audit a run.
- Privacy: contexts carry only caller-supplied data; nothing is
  logged or persisted by the framework.

## Verification

- `tests/test_chaos_framework.py`: 19 tests — definition validation,
  blast-radius blocking, probe failure semantics, inject/verify/
  rollback failure recording, steady-state delta detection, seed
  reproducibility, dry-run, and the `edge/chaos.py` hardening.
- `ruff check hugrgate/chaos tests/test_chaos_framework.py
  hugrgate/edge/chaos.py` clean.
