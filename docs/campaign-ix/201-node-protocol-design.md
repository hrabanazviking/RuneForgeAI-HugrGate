# Slice 201 — Node protocol design

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_protocol.py` (16 tests)

## What existed before

HugrGate had a client/server HTTP API (`/decide`, `/health`, `/backends`,
`/models`) but no inter-node wire concept at all: no versioning, no
envelope, no message taxonomy. Slices 202–225 all assume one.

## What was built

- `hugrgate/cluster/__init__.py` — new `hugrgate.cluster` subpackage;
  import-light at top level (no FastAPI/uvicorn dragged in).
- `hugrgate/cluster/protocol.py`:
  - `PROTOCOL_VERSION = 1`, `CLUSTER_RPC_PATH = "/cluster/rpc"`,
    `MAX_MESSAGE_BYTES = 4 MiB`.
  - `MessageType` string enum covering every kind slices 202–225 need
    (hello, heartbeat, decide/batch request+response, policy push/pull,
    provenance pull, steal request/response, trace spans, auth
    challenge/response, error, goodbye).
  - `ClusterMessage` dataclass: validated envelope
    (`protocol_version`, `msg_type`, 64-hex `sender`, monotonic `seq`,
    32-hex `trace_id`, `timestamp`, `payload`); `to_dict`/`from_dict`
    with `SpecError` on any defect.
  - `encode_message` / `decode_message`: compact sorted JSON bytes with
    size enforcement on both ends.
  - **Fail-closed forward compatibility:** envelopes newer than
    `PROTOCOL_VERSION` are rejected, never misread.

## Roles

Skald: audited server/client/daemon — no node concept existed.
Rúnhild: envelope + enum + size/version policy designed from the slice
list 202–225. Eldra: `protocol.py` forged, stdlib-only. Sólrún: 17 tests
green (success/failure/boundary). Védis: new subpackage; no existing
behavior touched; taxonomy table + arch-map LAYERS + manifest +
api-inventory regenerated. Scribe: committed `feat(gjallarbu-201)`.

## Verification

`pytest tests/test_cluster_protocol.py` — 16 passed;
`ruff check hugrgate/cluster tests/test_cluster_protocol.py` clean;
`mypy hugrgate/cluster` clean.
