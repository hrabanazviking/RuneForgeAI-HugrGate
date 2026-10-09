# Slice 208 — Mutual authentication

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_auth.py` (21 tests)

## What existed before

Slice 207's RPC had hooks for auth but no authentication: any peer
that could reach `/cluster/rpc` could ask for decisions. The envelope
had no integrity protection and no replay defense.

## What was built

- `hugrgate/cluster/auth.py`:
  - `ClusterKey`: 256-bit pre-shared key, `generate()`/`save()`/
    `load()` with 0600 file perms (same no-race pattern as node
    identity keys).
  - `Authenticator`: HMAC-SHA256 `seal()`/`verify()` over the exact
    wire bytes; constant-time `compare_digest`; `verify` never raises
    on garbage (returns `False`).
  - `enable_mutual_auth(node, key)`: flips the node to authenticated
    mode and returns the `mac_provider` for `RPCClient`.
- `hugrgate/errors.py`: new `ClusterAuthError` (`cluster_auth_error`,
  not recoverable — a bad tag means wrong key/tamper/replay, retrying
  identical bytes cannot help); taxonomy test lists extended.
- `hugrgate/cluster/rpc.py`: `RPCClient(..., mac_provider=...)` sends
  the tag in the `X-Cluster-MAC` header.
- `hugrgate/cluster/node.py`: `require_auth` + `authenticator`;
  `dispatch(..., auth_tag, raw)` verifies before anything else and
  enforces per-sender `seq` monotonicity (replay rejection).
- `hugrgate/cluster/routes.py`: passes header + raw body to dispatch.
- `tests/test_dependency_rules.py`: added genuinely-stdlib
  `hmac`/`secrets`/`ssl`/`stat` to the allowlist (the gate was red
  since slice 202's `secrets` import — fixed here).

## Bug caught by tests

`test_replay_rejected` deadlocked: `_check_auth` held a plain
`threading.Lock` while `fail()` → `next_seq()` re-acquired it. Fixed
with `RLock` (documented at the declaration).

## Roles

Skald: 207's hooks audited — unwired. Rúnhild: PSK + per-message HMAC
in header (envelope stays clean) + seq replay window. Eldra: forged
stdlib-only (`hmac`, `secrets`). Sólrún: 21 tests green incl. the
deadlock the suite caught. Védis: exports, taxonomy (lists +
allowlist), arch-map, manifest, inventory regenerated; `dispatch`
backward compatible (auth off by default). Scribe: committed
`feat(gjallarbu-208)`.

## Verification

`pytest tests/test_cluster_auth.py tests/test_errors.py` — all green;
ruff clean; mypy clean.
