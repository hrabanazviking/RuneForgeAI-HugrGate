# Slice 206 — LAN discovery adapter

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_lan.py` (14 tests,
marked `slow`)

## What existed before

Slice 204's registry had the static adapter (205) but no zero-config
mechanism: on a fresh LAN, nodes could not find each other without a
pre-written peer file.

## What was built

- `hugrgate/cluster/lan.py` — `LANDiscoveryAdapter`:
  - UDP multicast HELLOs on group `239.0.9.77:18377`, TTL 1
    (LAN-segment only), interface defaulting to `127.0.0.1` so the
    adapter works with no real network.
  - Background thread announces every `announce_interval_s` and parses
    incoming datagrams into `PeerRecord`s (host from the datagram
    source, http port + capabilities + tls from the payload); own
    HELLOs, malformed datagrams, non-HELLO types, and bad capabilities
    are ignored without dying.
  - Socket factory injectable for unit tests; real-socket failures
    raise `SpecError` with cause.
  - Membership built from `inet_aton` bytes (no `struct` import needed).

## Roles

Skald: 204/205 audited — zero-config discovery missing. Rúnhild:
multicast design, loopback-first. Eldra: forged stdlib-only.
Sólrún: 14 tests green — 13 with an injected fake socket, plus a real
two-adapter loopback-multicast discovery test (skips cleanly where the
sandbox forbids multicast). Védis: exports, taxonomy (slow), arch-map,
manifest, inventory regenerated. Scribe: committed `feat(gjallarbu-206)`.

## Verification

`pytest tests/test_cluster_lan.py` — 14 passed (incl. real loopback
discovery); ruff clean; mypy clean.
