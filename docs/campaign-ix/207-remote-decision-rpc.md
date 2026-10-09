# Slice 207 — Remote decision RPC

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_rpc.py` (25 tests)

## What existed before

`HugrGateClient` spoke plain HTTP to `/decide`, but there was no
node-to-node RPC: no envelope, no trace correlation, no typed error
round-trip, no way to treat a peer as a backend, and no `/cluster/*`
HTTP surface.

## What was built

- `hugrgate/cluster/rpc.py`:
  - `RPCClient` — sends `ClusterMessage` envelopes to
    `POST /cluster/rpc` (injectable `httpx.Client`; `trust_env=False`
    like `HugrGateClient`); `decide()` and `batch()` with typed error
    mapping (`HugrGateError.from_dict`), `Abstention` propagation,
    `BackendUnavailable` on connect failure, `TimeoutError` on timeout.
    Privacy is **fail-closed on both ends**: client *and* server
    require `policy.remote_inference`, else `PrivacyViolation`.
  - `RemoteBackend` — a `Backend` with `is_remote=True` wrapping a
    peer, so core selection, ladder pruning, and the policy gate treat
    remote nodes as ordinary backends. Proxies advertised capabilities;
    without them it honestly claims all spec types (operator opt-in).
  - `error_envelope()`; `OutboundHook` for slice 208's signing.
- `hugrgate/cluster/node.py` — `ClusterNode`: identity + gate +
  discovery + RPC; handler table keyed by `MessageType` (unknown →
  typed ERROR, never a guess); `handle_decide`/`handle_batch` run the
  local gate with the *peer's* policy; trace ids propagate to replies;
  `serve_remote` kill-switch; `inbound_hook` for slice 208.
- `hugrgate/cluster/routes.py` — `build_cluster_router(node)`:
  `POST /cluster/rpc`, `GET /cluster/peers`, `GET /cluster/health`.
- `server.py`: `create_app(gate, node=None)` mounts the router only
  when a node is given (lazy import keeps the module light);
  `daemon.py`: `create_daemon_app(..., node=None)` passes through.
  Standalone servers are byte-for-byte behavior-identical.

## Roles

Skald: `client.py`/`server.py` audited — no node RPC existed.
Rúnhild: envelope RPC + RemoteBackend-as-Backend designed so *zero*
core/ladder changes were needed. Eldra: forged (~700 lines). Sólrún:
25 tests green (round-trip, abstention, batch, fail-closed privacy
both ends, error mapping, hooks, core integration, HTTP route
end-to-end). Védis: exports, taxonomy, arch-map, manifest, inventory
regenerated; `create_app`/`create_daemon_app` backward compatible.
Scribe: committed `feat(gjallarbu-207)`.

## Verification

`pytest tests/test_cluster_rpc.py` — 25 passed; ruff clean; mypy
clean.
