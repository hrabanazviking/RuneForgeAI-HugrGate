# HugrGate Quickstart

## Install

```bash
pip install hugrgate
# With ML backends:
pip install "hugrgate[ml]"
# With the HTTP server:
pip install "hugrgate[server]"
```

## Your First Decision

```python
from hugrgate import HugrGate, DecisionSpec, DecisionPolicy
from hugrgate.backends.rules import RuleBackend

gate = HugrGate()
gate.register(RuleBackend.from_dicts([
    {"if": {"field": "temperature", "gt": 90},
     "then": "escalate", "confidence": 0.99},
    {"default": "ignore", "confidence": 0.6},
]))

spec = DecisionSpec(type="categorical",
                    options=["ignore", "log", "inspect", "escalate"])
policy = DecisionPolicy(minimum_probability=0.8,
                        remote_inference=False)

result = gate.decide({"temperature": 95}, spec, policy)
print(result.value)         # "escalate"
print(result.probability)   # 0.99
print(result.backend)       # "rules"
```

## The Intelligence Ladder

```python
from hugrgate.ladder import LadderRouter

router = LadderRouter([
    {"backend": "rules", "min_confidence": 0.9},
    {"backend": "logreg", "min_confidence": 0.8},
])
# Easy cases stop at rules; hard cases climb.
```

## Local Server

```bash
hugrgate serve --port 8000   # localhost only by default
curl -X POST localhost:8000/decide -d '{"state": {...}, "spec": {...}}'
```

## Design Maxim

> Deterministic where possible. Probabilistic where useful.
> Generative only where necessary.
