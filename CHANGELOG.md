# Changelog — HugrGate

## 0.1.0 (2026-10-09) — The Icebox Opens

First implementation release. 50 slices forged via Mythic Engineering.

### Foundation (slices 1–10)
- `DecisionSpec`: categorical, binary, ordinal, numeric, multilabel
- `DecisionResult`: typed value + probability distribution, invariants enforced
- `DecisionPolicy`: application-controlled thresholds
- `Backend` ABC + `BackendRegistry`
- Validation layer, core `decide()`, provenance store, error taxonomy
- `CLEAN_ROOM.md`, `CONTRIBUTING.md`, ADR-001

### Deterministic core (slices 11–20)
- `RuleBackend`: predicates, decision tables, YAML loading, confidence distributions
- `FallbackChain`, abstention, thresholding, health scoring, circuit breakers, timeouts
- Zero-ML milestone: event triage example

### Classical ML + calibration (slices 21–30)
- Feature preprocessing pipeline
- Logistic regression, random forest, gradient boosting backends
- Model manifests + versioned store
- Platt scaling, isotonic regression, temperature scaling (independent implementations)
- Calibration metrics (Brier, log loss, ECE, MCE), versioned profiles
- Calibrated classifier milestone

### Intelligence ladder (slices 31–40)
- `LadderRouter` with confidence gating, latency budgets, privacy gates
- Embedding prototype backend (offline hash embedding)
- NLI backend, constrained-decoding LLM backend
- Capability negotiation, batch inference, decision cache, privacy enforcement

### Service & ecosystem (slices 41–50)
- FastAPI service, daemon mode, Python client, CLI
- Benchmark harness + 3 original datasets (intent/urgency/triage, 500 items each)
- Drift monitoring (PSI), documentation, release checklist
