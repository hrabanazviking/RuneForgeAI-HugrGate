# HTTP API

Localhost-only by default (`hugrgate serve` binds `127.0.0.1:8377`;
binding elsewhere prints a warning — the API has no auth).

## Endpoints

### POST /decide

```json
{
  "state": {"temperature": 95},
  "spec": {"type": "categorical", "options": ["ignore", "escalate"]},
  "policy": {"minimum_probability": 0.8},
  "backend_name": "rules",
  "context": {}
}
```

→ the `DecisionResult` JSON directly on success. Abstention is HTTP 200
with `{"abstained": true, "reason": ..., "code": "abstention"}` —
not an error.

Status codes: `400` malformed JSON · `422` invalid spec/policy ·
`429` daemon queue full · `502` backend failed · `503` no backend
available.

### GET /health

Liveness probe: status, version, backends, uptime, decisions served.

### GET /backends

List of registered backends: name, capabilities, latency/cost
estimates, calibration info, privacy properties, health.

### GET /models

Known model catalogue entries (`hugrgate.server.register_model`).

### GET /daemon (daemon mode only)

Batching stats, configured client policies, warm pool contents.

## Daemon mode

`hugrgate-server` (or `hugrgate serve`) runs the long-lived daemon:

```bash
hugrgate serve --port 8377 --unix-socket /tmp/hugrgate.sock \
    --batch-window-ms 5 --max-batch 32 \
    --client-policies policies.json
```

- **Unix socket + localhost HTTP** from one process.
- **Model warm pool**: every backend's `warmup()` runs at startup.
- **Request batching**: `/decide` calls are coalesced over a short
  window and executed concurrently.
- **Per-client policies**: the `X-Client-Id` header selects a
  server-side policy from the JSON policy file; it overrides any policy
  in the request body.
- **Back-pressure**: a bounded queue; overload returns HTTP 429.
- **Graceful shutdown**: SIGINT/SIGTERM drains the queue first.

## Python Client

```python
from hugrgate.client import HugrGateClient

client = HugrGateClient(url="http://127.0.0.1:8377")
result = client.decide(state, spec, policy)
# Falls back to an in-process gate if the service is unreachable.
# Or skip HTTP entirely:
client = HugrGateClient(gate=my_gate)
```

## CLI

```bash
hugrgate decide --spec spec.yaml --state state.json [--backend rules]
hugrgate backends
hugrgate models
hugrgate health
hugrgate serve --port 8377
hugrgate bench --dataset benchmarks/triage_500.json \
    --backends keyword,uniform --out /tmp/bench.json
hugrgate report --report /tmp/bench.json --out /tmp/bench.md
```
