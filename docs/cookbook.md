# HugrGate Cookbook

Copy-paste recipes. Every recipe below is a complete program —
each fenced `python` block is extracted and executed by
`tests/test_deveco_443_cookbook.py`, so the cookbook cannot rot.

## 1. Decide in five lines

The in-process runtime with the built-in backends:

```python
from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.server import build_gate

gate = build_gate()
spec = DecisionSpec(type="categorical",
                    options=["ignore", "log", "escalate"])
result = gate.decide({"alert": "disk full on db-02"}, spec,
                     DecisionPolicy())
print(result.value, f"(p={result.probability:.2f})")
assert result.value in ("ignore", "log", "escalate")
```

## 2. Abstain instead of guessing

A high `minimum_probability` turns low-confidence decisions into
an explicit abstention your code can route to a human:

```python
from hugrgate import Abstention, DecisionPolicy, DecisionSpec
from hugrgate.server import build_gate

gate = build_gate()
spec = DecisionSpec(type="categorical",
                    options=["approve", "deny"])
try:
    result = gate.decide({"request": "vague expense report"}, spec,
                         DecisionPolicy(minimum_probability=0.95))
except Abstention as e:
    print("abstained:", e.message)
else:
    print("decided:", result.value)
```

## 3. Add a human review band

Decisions whose confidence lands inside the band come back as a
`review` verdict instead of an accept:

```python
from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.server import build_gate

gate = build_gate()
spec = DecisionSpec(type="categorical",
                    options=["approve", "deny"])
policy = DecisionPolicy(review_band=(0.4, 0.7))
result = gate.decide({"request": "refund for $42.00"}, spec, policy)
print("verdict:", result.value)
assert result.value in ("approve", "deny", "review")
```

## 4. Serve over HTTP and call it with the SDK

Start a real daemon on a free port, decide over HTTP, shut it
down cleanly:

```python
import socket
import time

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.client import HugrGateClient
from hugrgate.daemon import Daemon, DaemonConfig

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()

daemon = Daemon(DaemonConfig(port=port, batch_window_ms=5))
daemon.start()
try:
    client = HugrGateClient(f"http://127.0.0.1:{port}")
    for _ in range(100):
        if client.health().get("reachable"):
            break
        time.sleep(0.05)
    spec = DecisionSpec(type="categorical",
                        options=["ignore", "log", "escalate"])
    result = client.decide({"alert": "disk full on db-02"}, spec,
                           DecisionPolicy(), backend_name="keyword")
    print("http:", result.value,
          f"(transport={result.metadata['client_transport']})")
    assert result.value in ("ignore", "log", "escalate")
    client.close()
finally:
    daemon.stop()
```

## 5. Register your own backend — then conformance-check it

Custom backends subclass `Backend`. Run the conformance battery
(slice 440) before you deploy one:

```python
from collections.abc import Mapping
from typing import Any

from hugrgate.backend import Backend
from hugrgate.conformance import (
    assert_conformance,
    run_backend_conformance,
)
from hugrgate.result import DecisionResult
from hugrgate.server import build_gate
from hugrgate.spec import DecisionSpec


class LengthBackend(Backend):
    """Routes on input length: short text -> first option, else last."""
    name = "length"

    def capabilities(self) -> dict[str, Any]:
        return {"spec_types": ["categorical"]}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type == "categorical"

    def evaluate(self, state: Mapping[str, Any],
                 spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        options = list(spec.options or ["a", "b"])
        text = str(state.get("alert", ""))
        value = options[0] if len(text) < 40 else options[-1]
        dist = {o: (0.9 if o == value else 0.1 / (len(options) - 1))
                for o in options}
        return DecisionResult(
            value=value, probability=0.9, distribution=dist,
            uncertainty=0.1, accepted=True, backend=self.name,
            model="length-1.0", latency_ms=0.2,
            calibration_profile="none", fallback_used=False,
            metadata={})


backend = LengthBackend()
assert_conformance(run_backend_conformance(backend))  # raises if bad

gate = build_gate()
gate.register(backend)
spec = DecisionSpec(type="categorical",
                    options=["log", "escalate"])
result = gate.decide({"alert": "hi"}, spec, backend_name="length")
print("custom backend:", result.value)
assert result.value == "log"
```

## 6. Validate a contract template before deploying it

Templates are checked with the contract conformance kit
(slice 441): every allowed value must render a valid contract,
and bad parameters must be rejected with `ContractError`:

```python
from hugrgate.contracts.conformance import (
    assert_conformance,
    run_template_conformance,
)
from hugrgate.contracts.templates import (
    ContractTemplate,
    TemplateParameter,
)

template = ContractTemplate(
    template_id="triage-v1",
    parameters={
        "levels": TemplateParameter(
            "array", required=True,
            allowed=(["low", "high"], ["low", "mid", "high"])),
    },
    body={"schema_version": "2.0", "kind": "ordinal",
          "contract_id": "triage", "name": "triage",
          "levels": "${levels}"},
)
assert_conformance(run_template_conformance(template))
contract = template.instantiate(levels=["low", "mid", "high"])
print("template ok:", contract.contract_id)
```

## Conventions used by every recipe

- Imports live at the top of each recipe; copy the whole block.
- No network beyond `127.0.0.1`, no credentials, no files
  outside `/tmp`.
- Prefer `build_gate()` for in-process work — it wires the
  built-in backends and policy plumbing for you.
