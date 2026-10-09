# Slice 223 — Distributed chaos tests

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_chaos.py`
(12 tests)

## What existed before

Every cluster test ran on a perfect wire: no drops, no delays, no
duplicates, no corruption. The failure semantics (failover on
`BackendError`, abort on `SpecError`) were specified but never
exercised under adverse conditions.

## What was built

- `hugrgate/cluster/chaos.py`:
  - `FaultInjector` — seeded, reproducible fault profile:
    `drop_rate` / `delay_s`+`delay_rate` / `duplicate_rate` /
    `corrupt_rate`; one fault per request, priority-ordered
    drop > corrupt > duplicate > delay; `SpecError` on bad rates.
  - `ChaosProxy` — `httpx` transport wrapper applying the profile:
    drop → `ConnectError`, delay → sleep, duplicate → deliver twice
    (first reply wins), corrupt → first wire byte flipped so the
    receiver's `decode_message` rejects the envelope. Counts every
    fault in `stats()`. Test/operator tooling only — nothing in
    production enables it.
- `tests/test_cluster_chaos.py` — loopback chaos scenarios proving
  graceful degradation:
  - drop storm → router fails over to the healthy peer; the dead
    peer pays in health score;
  - delay → shows up in the latency tracker's EWMA;
  - duplicate → delivered twice, client sees one good answer;
  - corrupt → typed `SpecError` surfaces (no hang, no 500);
  - mixed seeded chaos → the cluster keeps deciding; all-candidates-
    failed surfaces as typed `BackendUnavailable`, never a hang.
- Two real findings while forging: (1) `peers()` returns
  freshest-first, not insertion order — tests must not assume
  routing order; (2) `decode_message` already wraps
  `UnicodeDecodeError` as `SpecError` (verified, not assumed).

## Roles

Skald: test suite audited — perfect-wire only. Rúnhild: seeded fault
injection + proxy at the transport layer. Eldra: forged. Sólrún:
12 tests green, 3 consecutive runs stable. Védis: exports, taxonomy,
arch-map, manifest, inventory regenerated. Scribe: committed
`feat(gjallarbu-223)`.

## Verification

`pytest tests/test_cluster_chaos.py` — 12 passed (x3 runs); ruff
clean; mypy clean.
