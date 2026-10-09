# The Intelligence Ladder

## Principle

Use the least expensive sufficient intelligence. Most easy decisions
should never reach expensive inference.

## Configuration

```python
from hugrgate import BackendRegistry
from hugrgate.ladder import LadderRouter, LadderRung

router = LadderRouter(BackendRegistry(), rungs=[
    LadderRung("rules",     min_confidence=0.90),
    LadderRung("logreg",    min_confidence=0.80),
    LadderRung("prototype", min_confidence=0.70),
    # NLI / LLM rungs added when models are available
])
```

## Behavior

1. Try the first rung.
2. If `result.probability >= min_confidence`, return it.
3. Otherwise, climb to the next rung.
4. Per-rung latency budgets: skip rungs that can't fit.
5. Privacy gate: remote rungs require `policy.remote_inference=True`.
6. Exhausted → abstain (honest, not a failure).

## Auditability

Every rung attempted is logged in provenance. You can always answer:
*which rungs were tried, and why did it stop where it did?*

## Capability Negotiation

`hugrgate.negotiate.select_backend()` filters by `supports()`,
privacy, latency, and health score — then ranks by historical accuracy
and calibration quality.
