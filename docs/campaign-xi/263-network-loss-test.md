# Slice 263 — Network-loss test

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_network_loss.py` (10 tests, green)

## What existed before

`hugrgate/cluster/chaos.py` (slice 223) injected drop/delay/
duplicate/corrupt faults at the httpx transport level — but there
was no *host-level* network story for remote backends: nothing
modeled "this host is unreachable", nothing failed fast instead of
hanging on dead sockets, and nothing proved a network outage can't
silently weaken policy.

## What was built

`hugrgate/chaos/network.py`:

- **`NetworkSimulator`** — scripted per-host reachability:
  `set_down` / `set_up` / `set_all_up` / `partition({"h": DOWN})`;
  unknown hosts are reachable by default; unknown states raise
  `SpecError`.
- **`NetworkGuard`** — fail-fast `Backend` wrapper for remotes:
  while its host is unreachable, `evaluate` raises
  `BackendUnavailable("network unreachable …")` *without calling
  the backend* (no socket-timeout wait). Local backends always
  delegate — they never touch the network. Stats (`allowed` /
  `blocked`) and `health()["network_reachable"]` for observability.

## Partial failure & the policy invariant

- **Partial failure**: with `dead-host` down and `live-host` up,
  the fallback chain skips the dead host and the live remote
  serves (`decided_by` provenance intact).
- **Total loss**: all remotes down → local backends serve.
- **No silent weakening**: after network loss,
  `policy.remote_inference` and `policy.minimum_probability` are
  byte-identical; when the bar can't be met the gate **abstains**
  instead of serving a below-threshold result. And
  `remote_inference=False` still blocks remotes even with the
  network up — the simulator changes nothing about policy.

## Integration

- Error semantics: `BackendUnavailable` (`code
  "backend_unavailable"`, recoverable) — the network heals, the
  backend becomes reachable again, `set_up` restores service with
  no restart.
- No new error class.

## Verification

- 10 tests: partition/heal semantics, fail-fast blocking (backend
  never called), pass-through when up, local-backend exemption,
  heal recovery, arg validation, partial-failure routing, total-
  loss local fallback, policy-immutability under loss, policy
  still gating remotes.
- `ruff check` clean.
