# HugrGate Concepts

## DecisionSpec

The application declares **what** decision it needs — never **how**.
Five types: `categorical`, `binary`, `ordinal`, `numeric`, `multilabel`.

## DecisionResult

A typed value plus a probability distribution. Key invariant:
the value is **always** within the spec's decision space. The application
never receives an out-of-space value.

## Backend

A replaceable intelligence implementation. The contract is tiny:
`capabilities()`, `supports(spec)`, `evaluate(state, spec, context)`,
`health()`. Rules, classifiers, ONNX models, NLI, local LLMs — all are
just backends.

## Policy

Thresholds belong to the application, not the model:
`minimum_probability`, `maximum_latency_ms`, `remote_inference`,
`allowed_backends`, `fallback_behavior`, `privacy_class`.

## The Intelligence Ladder

Use the least expensive sufficient intelligence:

```
rules → tiny classifier → embedding → NLI → local LLM → abstain
```

Each rung declares a minimum confidence. Below it, climb. Exhausted, abstain.

## Calibration

A probability without calibration is decoration. HugrGate ships Platt
scaling, isotonic regression, and temperature scaling — implemented
independently from public methods. A `0.95` should mean something measurable.

## Abstention

The system may say: *"I do not have enough confidence."*
This is a first-class outcome, not a failure.

## Provenance

Every decision records: request hash, spec, backend, model version,
calibration profile, probability, policy, threshold, latency, timestamp.
Answer: *why did the program take this branch?*

## Privacy

Default: offline, no account, no telemetry, no third-party data flow.
`remote_inference: forbidden` is enforced at backend selection — remote
backends cannot silently receive data.
