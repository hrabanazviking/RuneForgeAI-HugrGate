# HTTP API

Localhost-only by default.

## Endpoints

### POST /decide

```json
{
  "state": {"temperature": 95},
  "spec": {"type": "categorical", "options": ["ignore", "escalate"]},
  "policy": {"minimum_probability": 0.8}
}
```

→ `DecisionResult` JSON.

### GET /health

Liveness probe: status, version, backends, uptime, decisions served.

### GET /backends

Registered backend names and capabilities.

### GET /models

Known model catalogue entries.

## Python Client

```python
from hugrgate.client import HugrGateClient

client = HugrGateClient(url="http://127.0.0.1:8000")
result = client.decide(state, spec, policy)
# Falls back to in-process gate if server unreachable.
```

## CLI

```bash
hugrgate decide --spec spec.yaml --state state.json
hugrgate backends
hugrgate serve --port 8000
hugrgate bench --dataset benchmarks/triage_500.json
```
