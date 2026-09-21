# HugrGate Plundering Guide

> **Take inspiration freely. Take code carefully. Take proprietary secrets never.**

HugrGate is intended to be an independent, open-source decision runtime. We absolutely want to learn from the enormous body of existing open-source software, research, standards, and public knowledge.

But every piece brought aboard must have clean provenance.

This guide defines what may be safely “plundered,” what requires inspection, and what stays off the ship entirely.

---

## The Three Laws of Plunder

### 1. Ideas Are Better Treasure Than Copied Code

Prefer learning **how something works** and implementing the underlying concept independently.

Good:

```text
"This project uses temperature scaling for calibration."

→ Read the research.
→ Understand the mathematics.
→ Implement our own version.
```

Less desirable:

```text
Copy 800 lines from their calibration module.
```

Even when copying is legally permitted, independent implementation usually gives HugrGate cleaner architecture and provenance.

---

### 2. Know the License Before Taking Anything

Never copy code before identifying its license.

Preferred sources include:

* Apache-2.0
* MIT
* BSD-2-Clause
* BSD-3-Clause
* similarly permissive licenses

Every imported component should record:

```text
Project:
Source:
Version/commit:
License:
Files used:
Modifications:
Date imported:
Reason:
```

If the license is unclear, **do not use the code**.

---

### 3. Proprietary Systems Are Observation, Not Supply Depots

Do not copy, reconstruct, imitate, extract, distill, scrape, or reverse engineer proprietary decision systems.

For HugrGate specifically:

* do not copy Jev APIs
* do not copy Jev SDK code
* do not imitate proprietary schemas
* do not train against proprietary outputs
* do not probe proprietary services to infer their internals
* do not reproduce proprietary examples
* do not use leaked or confidential material
* do not attempt to reconstruct TypeSafe's model architecture or training methods

If a proprietary product demonstrates that a useful capability exists, treat that only as evidence that **the problem is worth solving**.

Then solve it independently.

---

# Green Treasure

These sources are generally the safest places to raid for knowledge.

## Academic Research

Excellent sources include papers covering:

* probabilistic classification
* calibration
* uncertainty estimation
* selective classification
* abstention
* conformal prediction
* cascaded inference
* mixture-of-experts routing
* natural language inference
* embeddings
* constrained decoding
* classifier ensembles

Prefer algorithms described mathematically rather than implementations copied from proprietary products.

---

## Open Standards

Standards are especially valuable because they reduce dependency on any one implementation.

Potential treasure includes:

* JSON Schema
* HTTP
* OpenAPI
* ONNX
* Unix sockets
* IPC conventions
* C ABIs
* serialization formats

Whenever possible:

> **Standardize the boundary, replace the implementation.**

---

## Permissively Licensed Open Source

Great hunting grounds include projects using:

```text
Apache-2.0
MIT
BSD
```

Potential areas to study:

* ONNX runtimes
* llama.cpp-style local inference
* model routers
* calibration libraries
* classifier pipelines
* schema validators
* embedding systems
* local inference servers
* benchmarking frameworks

Do not automatically copy code merely because the license permits it.

First ask:

> Can we implement the concept more simply ourselves?

---

# Yellow Treasure

These sources may be useful, but require careful inspection.

## MPL-2.0

MPL uses file-level copyleft.

Using an MPL library can be perfectly reasonable, but modified MPL-covered files generally retain MPL obligations.

Prefer keeping MPL components clearly separated.

---

## LGPL

LGPL libraries can often be used by permissively licensed applications, but integration details matter.

Dynamic linking is usually easier to reason about than incorporating LGPL code directly into HugrGate.

---

## GPL

GPL code should generally **not be copied into HugrGate's Apache-2.0 core**.

A separate optional adapter or external process may sometimes be possible, but licensing should be reviewed before integration.

Do not casually mix GPL source into the core repository.

---

## AGPL

Treat AGPL dependencies with even greater caution because network use can trigger source-disclosure obligations.

Do not integrate AGPL components into HugrGate's core without an intentional licensing decision.

---

# Red Treasure

Do not bring these aboard.

* proprietary source code
* leaked source code
* confidential documentation
* code with no license
* code copied from Stack Overflow without checking its licensing implications
* code generated from reverse engineering proprietary software
* proprietary API responses used as training data
* model weights without clear redistribution rights
* datasets without clear usage rights
* copied trademarks or branding
* decompiled binaries
* stolen documentation
* vendor SDK internals copied into compatibility layers

When provenance is uncertain:

```text
DO NOT IMPORT
```

Reimplement independently instead.

---

# The Clean-Room Method

When learning from something legally sensitive, use separation.

## Researcher

The researcher studies:

* public papers
* standards
* open implementations
* documented behavior

They write a neutral specification describing the **problem and required behavior**, not copied implementation details.

Example:

```text
Requirement:

Given a categorical decision with N legal outputs,
the backend returns a probability distribution whose
values sum approximately to 1.
```

## Implementer

The implementer writes HugrGate's implementation from that specification using independent code.

This creates a much cleaner provenance trail.

---

# Plunder the Concept, Not the Shape

Suppose another system offers:

```text
ask(state, choices)
```

Do not automatically reproduce that interface.

Ask what the underlying requirement is:

```text
Need:
Evaluate bounded alternatives against supplied state.
```

Then design a HugrGate-native interface:

```text
DecisionRequest
DecisionSpec
DecisionResult
```

Solve the same general problem through an independently designed architecture.

---

# Model Plundering

Open-weight models require the same care as source code.

Before supporting or redistributing a model, check:

* model license
* commercial-use restrictions
* redistribution rights
* derivative-model restrictions
* acceptable-use clauses
* dataset provenance where known

HugrGate should preferably **support models rather than bundle them**.

For example:

```text
HugrGate
   ↓
user-selected ONNX model
```

is generally cleaner than shipping gigabytes of third-party weights inside the repository.

---

# Dataset Plundering

Datasets can be legally messier than code.

Before importing one, record:

```text
Source
License
Collection method
Redistribution permission
Commercial-use permission
Personal-data concerns
Derivative-data restrictions
```

When practical, create HugrGate's own synthetic or independently curated evaluation sets.

Never assume:

> "It's publicly downloadable, therefore it is free to reuse."

Those are not the same thing.

---

# Benchmark Plundering

Ideas for benchmarks are fair inspiration.

Prefer building original benchmark datasets and harnesses.

Good:

```text
Measure:
latency
accuracy
Brier score
calibration error
memory
throughput
```

Avoid cloning another company's exact private benchmark or reproducing proprietary evaluation datasets.

---

# Architecture Plundering

This is where we should plunder most enthusiastically.

Study successful patterns such as:

```text
adapter interfaces
plugin systems
fallback chains
backend registries
local daemons
capability negotiation
model manifests
circuit breakers
batching
confidence thresholds
abstention
```

These are broad software-engineering patterns.

Take the idea.

Build the HugrGate version.

---

# Dependency Rule

Every dependency should answer:

```text
Why is this here?
Can it be replaced?
Can HugrGate function without its vendor?
Is the license compatible?
Can users audit it?
Can users substitute another implementation?
```

If the answer becomes:

> "The entire project dies if Company X disappears,"

we have probably recreated the problem HugrGate exists to avoid.

---

# The Sovereignty Test

Before adopting a dependency, imagine:

```text
The developer disappears.
The company shuts down.
The website vanishes.
The API is discontinued.
The price becomes absurd.
```

Can HugrGate still function?

If yes:

```text
GOOD ARCHITECTURE
```

If no:

```text
RECONSIDER
```

---

# Plunder Ledger

Create:

```text
docs/PLUNDER_LEDGER.md
```

Every meaningful borrowed implementation or architectural influence can be recorded there.

Suggested format:

```markdown
## Component

Source:
Project:
URL:
License:
Commit/version:

### What we learned

Description.

### What we used

Code / algorithm / interface idea / research concept.

### Implementation

Copied with attribution / independently implemented / dependency.

### Notes

Any compatibility or provenance concerns.
```

This turns provenance into project documentation rather than archaeology five years later.

---

# Final Rule

HugrGate should be able to say:

> We studied the commons, learned from decades of open research and software engineering, and built our own system from legally reusable foundations.

The goal is not isolation.

The goal is **freedom without amnesia**.

Plunder widely.

Document everything.

Copy sparingly.

Reverse engineer nothing proprietary.

And never let a single vendor own the gate.
