# HugrGate Roadmap

> **Working title.** Open-source, local-first, model-agnostic probabilistic decision runtime.

**Current state:** Icebox / future project  
**Priority:** Below existing active projects  
**Implementation commitment:** None yet

This roadmap is intentionally designed so HugrGate can remain dormant for months or years without losing the core idea.

---

# Phase 0 — Legal, Prior Art, and Project Hygiene

**Goal:** Establish a defensible clean-room foundation before implementation.

## 0.1 Freeze the clean-room rules

Create:

```text
LEGAL-NOTES.md
CLEAN_ROOM.md
CONTRIBUTING.md
PROVENANCE.md
docs/adr/
```

Document that the project will not:

- reverse engineer proprietary decision services
- use proprietary outputs for distillation
- imitate proprietary API signatures
- reproduce vendor examples
- reconstruct undocumented architecture
- use confidential or leaked information

## 0.2 Patent / freedom-to-operate review

Before substantial implementation:

- search USPTO
- search WIPO PATENTSCOPE
- search Google Patents
- search EPO Espacenet
- search assignments by company name
- search inventor names
- search parent/subsidiary entities
- search terminology related to calibrated machine decisions
- search parallel decision sampling
- search structured probabilistic inference APIs

Record:

```text
search date
database
query
results
relevant claims
reason considered relevant/not relevant
```

If the project becomes serious or commercial, obtain professional patent counsel.

### Important

A lack of visible patents today does not prove freedom to operate.

Applications may be unpublished, newly filed, assigned through another entity, or described with terminology that does not match marketing language.

## 0.3 Trademark / naming review

`HugrGate` is provisional.

Before publishing packages:

- search USPTO trademarks
- search WIPO Global Brand Database
- search GitHub
- search PyPI
- search npm
- search crates.io
- search Maven
- search package managers
- search ordinary web usage

Rename before release if necessary.

## 0.4 Prior-art bibliography

Build a bibliography around independent, established methods:

- probabilistic classification
- logistic regression
- Bayesian classification
- neural classifiers
- NLI
- model calibration
- temperature scaling
- Platt scaling
- isotonic regression
- conformal prediction
- constrained decoding
- finite-state grammars
- schema-constrained generation
- mixture-of-experts routing
- cascaded classifiers
- selective classification
- abstention / reject options

This gives the architecture its own intellectual lineage.

---

# Phase 1 — Decision Contract

**Goal:** Define the project without implementing AI.

## 1.1 DecisionSpec

Define a model-independent schema.

Initial candidate types:

```text
categorical
binary
ordinal
numeric
multilabel
```

Do not model the schema after a proprietary vendor API.

## 1.2 DecisionResult

Core fields:

```text
value
probability
distribution
uncertainty
accepted
backend
model
latency
calibration_profile
fallback_used
metadata
```

## 1.3 Policy

Possible policy controls:

```text
minimum_probability
maximum_latency
remote_inference
allowed_backends
preferred_backends
fallback_behavior
privacy_class
max_cost
```

## 1.4 Validation

All request and response structures must be locally validated.

The application must never receive a value outside its declared decision space.

### Milestone

A complete protocol specification with **zero AI code**.

---

# Phase 2 — Deterministic Reference Runtime

**Goal:** Prove the interface without machine learning.

Implement:

- schema parser
- result validator
- decision policy engine
- threshold logic
- backend registry
- deterministic rule backend
- fallback engine
- provenance records
- test suite

Example:

```text
state
 ↓
rules
 ↓
DecisionResult
```

This phase is deliberately boring.

If the architecture cannot work elegantly with ordinary rules, adding AI will not fix it.

### Milestone

A local runtime that can already be used as a structured decision abstraction.

---

# Phase 3 — Classical ML Backends

**Goal:** Add fast local probabilistic intelligence.

Possible adapters:

- logistic regression
- linear SVM + probability calibration
- random forest
- gradient boosting
- compact neural classifier
- scikit-learn compatible models
- ONNX classifiers

Add:

- feature preprocessing contract
- probability extraction
- calibration metadata
- batch inference
- model manifests
- hardware capability reporting

### Milestone

Useful AI decisions in milliseconds without a generative model.

---

# Phase 4 — Calibration Layer

**Goal:** Make probabilities empirically meaningful.

Implement evaluation support for:

- Brier score
- log loss
- expected calibration error
- maximum calibration error
- reliability diagrams
- threshold precision / recall
- abstention curves

Implement optional calibrators:

- Platt scaling
- isotonic regression
- temperature scaling

Store calibration profiles separately from model weights.

Example:

```text
raw model score
      ↓
calibrator
      ↓
usable probability
```

### Milestone

A decision engine where confidence thresholds can be justified with measurements.

---

# Phase 5 — Open Local Language Intelligence

**Goal:** Handle fuzzy natural-language decisions without cloud dependency.

## 5.1 NLI backend

Evaluate statements using an open natural-language-inference model.

Useful for:

```text
"The message concerns billing."
"The event represents a security problem."
"The request requires immediate attention."
```

## 5.2 Embedding backend

Prototype / nearest-label classification.

## 5.3 Local LLM backend

Use open-weight models through a replaceable inference adapter.

Requirements:

- schema-constrained decoding
- no free-form output requirement
- local execution
- bounded output space
- timeout support
- token budget
- model capability metadata

Possible runtimes may include open local inference engines such as llama.cpp-compatible systems.

### Milestone

Natural-language judgment while remaining offline.

---

# Phase 6 — Intelligence Ladder / Cascade Router

**Goal:** Automatically use the smallest sufficient inference method.

Example cascade:

```text
RuleBackend
    ↓ uncertain
TinyClassifier
    ↓ uncertain
LocalNLI
    ↓ uncertain
LocalLLM
    ↓ uncertain
OptionalStrongBackend
    ↓
abstain
```

Routing inputs:

```text
decision type
latency budget
privacy policy
hardware
model availability
historical accuracy
calibration
cost
confidence
```

The router itself must remain auditable.

### Milestone

Most easy decisions never reach expensive inference.

---

# Phase 7 — Language-Neutral Runtime

**Goal:** Make HugrGate genuinely "bolt-on."

Candidate architecture:

```text
                 HugrGate Core
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
     C ABI        Local IPC      Local HTTP
        │             │             │
        ▼             ▼             ▼
     Rust/C++       Python        anything
     Mojo           JS/TS         with HTTP
     Go             Java
```

Priority bindings:

1. Python
2. Rust
3. C ABI
4. Mojo
5. JavaScript / TypeScript
6. Go

Avoid making language SDKs the canonical specification.

The wire protocol is canonical.

### Milestone

The same decision runtime can serve programs written in unrelated languages.

---

# Phase 8 — Local Service Mode

**Goal:** Share one warmed inference runtime between applications.

Features:

- localhost-only default
- Unix socket option
- authenticated local HTTP option
- model warm pool
- batching
- request priorities
- per-client policies
- memory limits
- GPU scheduling
- CPU fallback
- health endpoint
- zero required external connectivity

Potential process model:

```text
Application A ─┐
Application B ─┼─► HugrGate daemon ─► local models
Application C ─┘
```

### Milestone

One small local intelligence service can support many programs without each loading duplicate model weights.

---

# Phase 9 — Benchmark Suite

**Goal:** Compare inference methods without depending on vendor benchmarks.

Create original datasets for tasks such as:

- intent classification
- urgency
- routing
- anomaly triage
- relevance
- policy classification
- event prioritization

Measure:

```text
accuracy
precision
recall
F1
Brier score
calibration
latency
throughput
RAM
VRAM
energy where measurable
cold-start time
warm inference time
```

Every benchmark should state:

- hardware
- model
- quantization
- runtime
- dataset
- sample count
- calibration procedure

### Milestone

Users can choose backends based on measured tradeoffs rather than marketing.

---

# Phase 10 — Decision Provenance and Replay

**Goal:** Make automated decisions inspectable.

Record optionally:

```text
request hash
decision spec
backend
model
model version
calibration profile
probability
policy
threshold
result
latency
timestamp
```

Support deterministic replay where possible.

Privacy controls must allow applications to avoid storing raw sensitive input.

### Milestone

A developer can answer:

> Why did the program take this branch?

---

# Phase 11 — Reliability

Add:

- circuit breakers
- watchdogs
- backend health scoring
- timeouts
- safe defaults
- graceful degradation
- load shedding
- model quarantine
- calibration drift detection
- regression testing
- rollback

Principle:

> Failure of intelligence must not automatically become failure of software.

---

# Phase 12 — Optional Remote Providers

**Goal:** Permit cloud inference without requiring it.

Remote adapters must be:

- optional
- disabled by default in privacy-strict deployments
- replaceable
- clearly identified in provenance
- subject to user policy
- unable to silently receive data

Example:

```yaml
privacy:
  remote_inference: allowed

providers:
  allowed:
    - example_provider
```

A HugrGate-compatible application must remain architecturally capable of running without any single remote provider unless the application author explicitly chooses otherwise.

### Milestone

Cloud becomes an optional accelerator rather than the foundation of the system.

---

# Phase 13 — Agent-System Integration

Possible future adapters:

- event buses
- agent routers
- task queues
- memory systems
- security monitors
- robotics event layers
- local AI companions

Potential pattern:

```text
event
 ↓
fast deterministic checks
 ↓
HugrGate judgment
 ↓
agent route / escalation
 ↓
deep reasoning model only when necessary
```

HugrGate should not become dependent on any one agent architecture.

---

# Phase 14 — Edge Optimization

Possible targets:

- Raspberry Pi
- Jetson
- laptops
- mini PCs
- offline workstations
- embedded Linux

Research:

- INT8 classifiers
- small ONNX graphs
- quantized embedding models
- quantized NLI
- compact local LLMs
- batching
- speculative backend selection
- CPU/GPU/NPU dispatch

### Milestone

Useful probabilistic decisions on modest hardware without network access.

---

# Phase 15 — Ecosystem

Potential extras:

```text
hugrgate-core
hugrgate-server
hugrgate-python
hugrgate-rust
hugrgate-mojo
hugrgate-js
hugrgate-onnx
hugrgate-llamacpp
hugrgate-nli
hugrgate-bench
hugrgate-calibrate
```

These package names are placeholders until naming and trademark review is complete.

---

# Release Gates

Do not call the project production-ready until:

- API semantics are stable
- calibration is tested
- failure modes are documented
- remote use is never implicit
- clean-room provenance exists
- dependency licenses are audited
- project name is cleared
- patent/FTO review appropriate to the project's intended use has been completed
- benchmark methodology is public
- reproducible tests exist

---

# Someday / Maybe

Interesting ideas that do **not** belong in the MVP:

- learned backend routing
- adaptive cascades
- multi-model consensus
- uncertainty decomposition
- conformal abstention
- hardware-aware model selection
- automatic calibration drift correction
- WASM runtime
- embedded/no-std client
- distributed local decision mesh
- decision caching
- temporal belief tracking
- domain-specific calibration packs
- compiler integration
- language syntax sugar for probabilistic conditionals

Example future syntax:

```text
if? event_is_dangerous(state) @ confidence >= 0.95:
    escalate()
```

That syntax would only be sugar over the runtime, not a new programming language requirement.

---

# Minimum Viable Project

If this project ever moves out of the icebox, resist the temptation to build the cathedral immediately.

The MVP can be tiny:

```text
1. DecisionSpec
2. DecisionResult
3. RuleBackend
4. ONNX classifier backend
5. calibration support
6. local Python API
7. tests
```

That alone would prove whether the abstraction is useful.

Everything else can wait.

---

# Backlog Priority Note

HugrGate is intentionally documented now so the idea does not need to compete with active projects for attention.

The correct next action today is:

```text
save the design
close the forge
work on higher-priority projects
```

The roadmap will still be here when a real use case makes the project worth waking up.
