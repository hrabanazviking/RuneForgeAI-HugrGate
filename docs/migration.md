# Migration guide

How to move between HugrGate generations without breaking
production. The helpers live in `hugrgate/compat.py`.

## v1 client → SDK v2

`HugrGateClient` (`hugrgate.client`) is untouched and keeps
working. `HugrGateSDK` (`hugrgate.sdk`, slice 428) is a strict
superset: the same constructor arguments plus a context manager,
retries with backoff on recoverable failures, taxonomy error
mapping, `decide_batch`, and a versioned `User-Agent`.

The mechanical migration is one import:

```python
# before
from hugrgate.client import HugrGateClient
client = HugrGateClient("http://127.0.0.1:8377", timeout=5.0)

# after
from hugrgate.sdk import HugrGateSDK
client = HugrGateSDK("http://127.0.0.1:8377", timeout=5.0)
```

If the client is constructed in one place and used in many,
`compat.upgrade_client` rebuilds it with identical transport
settings:

```python
from hugrgate.compat import upgrade_client

sdk = upgrade_client(old_client, max_retries=5)
with sdk:  # context manager closes the HTTP pool
    result = sdk.decide(state, spec, policy)
```

Behavior changes to expect:

- Transient failures (connection errors, HTTP 502/503/504, and
  taxonomy errors flagged recoverable) are now **retried**
  automatically with exponential backoff. Caller bugs
  (`SpecError`, `PolicyError`) are never retried.
- HTTP error envelopes are mapped back onto the HugrGate error
  taxonomy (`SpecError`, `BackendUnavailable`, …) instead of
  leaking `httpx.HTTPStatusError` — widen any `except` clauses
  that caught httpx errors.
- The `User-Agent` becomes `hugrgate-sdk-py/2.0`; operators can
  see SDK skew in access logs.

## Contract schema v1 → v2

v1 contracts are `DecisionSpec` dicts; v2 contracts carry
`schema_version: "2.0"` and a `kind`. `contract_from_dict`
refuses v1 dicts with `unsupported_schema_version` and points at
the migration. Migrate explicitly and read the report:

```python
from hugrgate.compat import migrate_contract

contract, report = migrate_contract(old_dict)
print(report.describe())
if report.lossy:
    print("warnings:", report.warnings)  # review before deploying
```

The migration is exact for categorical/binary/ordinal/numeric
specs; check `report.warnings` for anything the v2 contract
could not preserve (e.g. free-form metadata the new schema
normalizes).

## Pre-protocol clients (before slice 426)

Clients older than the stable protocol do not send a version.
No migration is needed: the server negotiates — requests
without a version are treated as 1.0 and every response is
stamped with the negotiated version. To move a fleet forward,
upgrade the server first (it speaks both), then roll the
clients.

## Checklist

1. Upgrade the server; confirm `/protocol` reports 1.0.
2. Migrate contract dicts with `migrate_contract`; review
   `report.lossy` before deploying.
3. Swap `HugrGateClient` → `HugrGateSDK` (or `upgrade_client`);
   widen httpx `except` clauses to the taxonomy.
4. Watch access logs for the `hugrgate-sdk-py/2.0` User-Agent to
   confirm the rollout.
