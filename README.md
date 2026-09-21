# HugrGate

> **Working title.** An open-source, local-first, model-agnostic runtime for adding probabilistic machine judgment to ordinary program logic without making software dependent on one AI vendor, one model family, or one inference method.

**Status:** Concept / Icebox  
**Implementation:** Not started  
**Proposed license:** Apache-2.0  
**Project philosophy:** Local first. Open interfaces. Replaceable intelligence. Deterministic when possible.

---

## Why HugrGate?

Most software decisions are easy to express:

```python
if temperature > 90:
    enable_cooling()
```

Some decisions are not:

```text
Does this event look urgent?
Which subsystem should handle this request?
Is this message probably a security incident?
Does this state look anomalous?
```

Developers often solve those problems by calling a large language model and asking it to emit JSON. That works, but it introduces several problems:

- unnecessary generative inference
- parsing and schema failures
- unpredictable latency
- excessive compute
- cloud dependence
- vendor lock-in
- weak probability calibration
- poor offline behavior
- difficulty choosing the smallest tool that can solve the problem

HugrGate proposes a different abstraction:

```text
unstructured or structured state
            ↓
      DecisionSpec
            ↓
        HugrGate
            ↓
 typed value + probability distribution
            ↓
      ordinary program logic
```

The important part is that **HugrGate is not a model**.

It is an open decision runtime and interface capable of selecting among many inference methods.

---

## Core Principle

> **Intelligence is a replaceable implementation detail, not a vendor dependency.**

A program should be able to ask for a bounded machine judgment without caring whether that judgment came from:

- deterministic rules
- a statistical classifier
- logistic regression
- gradient boosting
- an embedding model
- a small neural network
- an ONNX model
- a local NLI model
- a constrained local LLM
- a specialized decision model
- a remote provider explicitly enabled by the user
- a future inference system that does not exist yet

The application depends on the **decision contract**, not the intelligence provider.

---

## Goals

HugrGate should eventually provide:

1. **Typed machine decisions**
2. **Probabilities and uncertainty**
3. **Local-first inference**
4. **Multiple interchangeable backends**
5. **Deterministic fallbacks**
6. **Automatic escalation to stronger inference only when needed**
7. **Language-neutral integration**
8. **Offline operation**
9. **Auditable decision provenance**
10. **Calibration and benchmarking tools**
11. **No mandatory cloud service**
12. **No mandatory model family**
13. **No mandatory AI at all when ordinary code is sufficient**

---

## Non-Goals

HugrGate is **not** intended to be:

- a clone of any proprietary AI service
- API-compatible with any proprietary decision model
- a reverse-engineered implementation of another company's architecture
- a model-distillation project
- a chatbot
- a general text-generation system
- a replacement for ordinary conditional logic
- a reason to put AI in places where deterministic code is better

The project should avoid copying proprietary API schemas, SDK signatures, terminology, documentation, examples, model outputs, benchmark suites, or branding.

---

## Decision Contract

Rather than defining the runtime around a particular model's output types, HugrGate should use a general schema.

Possible decision families:

### Categorical

Choose among named alternatives.

```yaml
type: categorical
options:
  - normal
  - warning
  - critical
```

### Binary belief

Estimate the probability that a proposition is true.

```yaml
type: binary
statement: "This event represents a security problem."
```

### Ordinal

Estimate position on an ordered scale.

```yaml
type: ordinal
levels:
  - trivial
  - low
  - moderate
  - high
  - critical
```

### Numeric

Estimate a bounded numeric quantity.

```yaml
type: numeric
minimum: 0
maximum: 100
```

### Multi-label

Allow multiple labels to be independently probable.

```yaml
type: multilabel
labels:
  - billing
  - account
  - security
  - technical
```

Future decision types can be added without changing the core abstraction.

---

## Example

Conceptual Python usage:

```python
result = gate.decide(
    state=event,
    spec={
        "type": "categorical",
        "options": ["ignore", "inspect", "escalate"]
    }
)

if result.value == "escalate" and result.probability >= 0.95:
    alert_operator()
```

The same application could later swap:

```text
RuleBackend
     ↓
ONNXClassifierBackend
     ↓
LocalLLMBackend
     ↓
RemoteBackend
```

without rewriting the program's decision logic.

---

## Result Object

A possible language-neutral result:

```json
{
  "value": "escalate",
  "probability": 0.96,
  "distribution": {
    "ignore": 0.01,
    "inspect": 0.03,
    "escalate": 0.96
  },
  "uncertainty": 0.04,
  "backend": "local_onnx_classifier",
  "model": "example-model",
  "calibration_profile": "security-events-v3",
  "latency_ms": 4.7,
  "fallback_used": false
}
```

Not every backend must provide every optional field.

The runtime should never invent precision that the backend cannot support.

---

## Intelligence Ladder

One of HugrGate's central ideas is to use the **least expensive sufficient intelligence**.

```text
Can deterministic code answer it?
            │
       yes ─┴─► rules
            │ no
            ▼
Can a tiny classifier answer it confidently?
            │
       yes ─┴─► classifier
            │ no
            ▼
Can a small local model answer it confidently?
            │
       yes ─┴─► local model
            │ no
            ▼
Is a stronger backend permitted?
            │
       yes ─┴─► stronger model
            │ no
            ▼
      uncertain / review
```

This allows AI judgment without turning every conditional into a heavyweight inference call.

---

## Proposed Architecture

```text
┌──────────────────────────────────────────────┐
│                Application                   │
└─────────────────────┬────────────────────────┘
                      │
                DecisionRequest
                      │
┌─────────────────────▼────────────────────────┐
│                HugrGate Core                 │
│                                              │
│  Schema validation                           │
│  Policy engine                               │
│  Backend selection                           │
│  Calibration                                │
│  Thresholding                                │
│  Fallback / escalation                       │
│  Decision provenance                         │
└───────────────┬──────────────┬───────────────┘
                │              │
       ┌────────▼──────┐ ┌────▼─────────────┐
       │ deterministic │ │ inference backend │
       │    engines     │ │     adapters      │
       └───────────────┘ └────┬──────────────┘
                              │
          ┌───────────────────┼────────────────────┐
          ▼                   ▼                    ▼
       ONNX             local LLM            other local
     classifier        constrained            inference
                        decoding               engines
```

Optional remote adapters should sit outside the trusted local core and should never be required for basic operation.

---

## Backend Interface

A backend needs only a small abstract contract:

```text
capabilities()
supports(spec)
evaluate(state, spec, context)
health()
```

A backend may additionally expose:

```text
warmup()
batch()
calibration_info()
estimated_latency()
estimated_cost()
privacy_properties()
hardware_requirements()
```

This makes routing decisions possible without coupling HugrGate to one inference system.

---

## Language Independence

HugrGate should eventually be callable from virtually any language.

Possible integration surfaces:

1. native library API
2. stable C ABI
3. Unix domain socket
4. local HTTP API
5. local IPC protocol
6. language-specific convenience SDKs

Potential bindings:

- Python
- Rust
- C / C++
- Mojo
- JavaScript / TypeScript
- Go
- Java
- C#
- Kotlin
- Swift

The protocol should be documented independently of any SDK.

---

## Local-First Backends

Early experimental backends could include:

### Rules

Pure deterministic predicates and decision tables.

### Classical ML

- scikit-learn compatible models
- logistic regression
- random forests
- gradient boosting
- small neural classifiers

### ONNX

Portable inference through ONNX Runtime or compatible engines.

### Embedding / Prototype Classification

Compare input embeddings against labeled prototypes.

### Natural Language Inference

Use an open NLI model to estimate whether statements are supported by supplied state.

### Local LLM

Use a local open-weight language model with constrained decoding so only schema-valid outputs are possible.

Possible inference engines could include llama.cpp-compatible runtimes or other open local runtimes.

No single backend should be privileged by the architecture.

---

## Calibration

Probability without calibration can be dangerously persuasive.

HugrGate should treat calibration as a first-class subsystem.

Potential established techniques include:

- Platt scaling
- isotonic regression
- temperature scaling
- histogram/bin calibration
- conformal methods where appropriate

Metrics may include:

- Brier score
- log loss
- expected calibration error
- reliability diagrams
- class-specific calibration
- abstention accuracy
- latency
- throughput

A `0.95` should mean something measurable, not merely look authoritative.

---

## Abstention

The system must be allowed to say:

```text
I do not have enough confidence to make this decision automatically.
```

Example policy:

```yaml
policy:
  accept_above: 0.95
  review_between: [0.70, 0.95]
  abstain_below: 0.70
```

Thresholds belong to the application, not the model.

---

## Privacy and Sovereignty

A default HugrGate installation should be capable of operating:

- offline
- without an account
- without an API key
- without telemetry
- without sending application state to a third party

Remote inference should be an explicit optional capability.

Applications should be able to declare:

```yaml
privacy:
  remote_inference: forbidden
```

and have the runtime enforce it.

---

## Failure Philosophy

If intelligence fails, the software should degrade gracefully.

Possible fallback chain:

```text
preferred local model
        ↓ failure
secondary local model
        ↓ failure
deterministic safe rule
        ↓
abstain / request review
```

A network outage should not silently disable an application that was designed for local operation.

---

## Clean-Room / Intellectual-Property Policy

HugrGate should be developed as an **independent implementation of general decision-inference concepts**, not as a reconstruction of any proprietary service.

### Hard rules

Contributors should not:

- use proprietary model outputs to train, distill, or tune HugrGate
- reverse engineer proprietary services
- attempt to infer proprietary model architecture
- copy proprietary SDK implementation
- copy proprietary API schemas
- copy proprietary examples or documentation
- reproduce proprietary benchmarks verbatim
- use confidential or leaked technical material
- submit code derived from another project's non-compatible source
- describe the project as a drop-in clone of a proprietary product

### Development provenance

Important architectural choices should receive an Architecture Decision Record (ADR) documenting:

- the problem being solved
- public/open references used
- alternatives considered
- independent design rationale
- license information for incorporated dependencies

### Research sources

Prefer:

- textbooks
- academic papers
- standards
- open-source implementations with compatible licenses
- public-domain mathematical methods
- independently developed benchmarks
- well-established machine-learning techniques

### Proprietary-service firewall

For maximum clean-room separation, developers implementing the core should **not use proprietary decision services as behavioral oracles**.

Testing should use independently constructed datasets and open models.

---

## Preliminary TypeSafe/Jev IP Caution

This project concept arose after public discussion of TypeSafe AI's Jev product, but HugrGate must not reproduce TypeSafe's proprietary implementation.

As of September 21, 2026, TypeSafe publicly describes its technology as involving:

- a new model architecture
- a parallel sampler
- a training method it calls Reinforcement Learning for Calibrated Decisions (RLCD)

Those specific mechanisms should be treated as **out of scope** unless later independent legal and prior-art review determines a safe path.

TypeSafe's current customer agreement also restricts customers from using its Services or Output to develop similar or competing products and prohibits attempts to derive underlying algorithms, structure, or organization.

Therefore HugrGate development should not rely on the Jev service, Jev outputs, private documentation, or reverse engineering.

A preliminary web search did **not** identify an obvious public patent filing specifically matching TypeSafe AI, Jev, or RLCD. That is **not** evidence that no relevant patent rights exist. Patent applications can remain unpublished for a period, searches can miss filings, ownership can be held under different entities or names, and future applications may appear.

Before serious implementation or public release, perform a proper patent / freedom-to-operate review.

---

## Branding Policy

**HugrGate is a working title.**

Before public release:

- perform a trademark search
- search GitHub/package registries
- search relevant software marketplaces
- verify domain availability if desired
- choose a distinct project logo and visual identity

Do not use TypeSafe, Jev, System One, or confusingly similar marks as project branding.

A public release should state that the project is independent and not affiliated with proprietary vendors whose products may be discussed for comparison.

---

## Proposed License

**Apache License 2.0** is the initial recommendation because it is permissive while including explicit patent-related provisions for contributions.

Final licensing should be selected before outside code contributions begin.

Possible alternatives:

- MIT
- Apache-2.0
- dual MIT / Apache-2.0

Do not accept code with uncertain provenance.

---

## Possible Relationship to Agent Systems

HugrGate could eventually serve as a lightweight decision layer inside an agent architecture:

```text
event
  ↓
HugrGate
  ↓
route / ignore / inspect / escalate
  ↓
specialized agent or larger reasoning model
```

This lets the larger model concentrate on tasks that genuinely require deeper reasoning.

The runtime itself should remain independent of any particular agent framework.

---

## Example: Local Event Routing

```python
decision = gate.decide(
    state={
        "source": "filesystem",
        "event": "unexpected executable appeared in watched directory"
    },
    spec={
        "type": "categorical",
        "options": [
            "ignore",
            "log",
            "inspect",
            "escalate"
        ]
    },
    policy={
        "remote_inference": False,
        "minimum_probability": 0.90
    }
)

if decision.accepted:
    router.send(decision.value)
else:
    router.send("inspect")
```

The important property is not the syntax.

The important property is that the application controls:

- acceptable output space
- inference policy
- privacy requirements
- confidence thresholds
- escalation behavior

---

## Design Maxim

> **Deterministic where possible. Probabilistic where useful. Generative only where necessary.**

---

## Current Status

HugrGate currently exists only as a project concept and design document.

There is no active implementation schedule.

That is intentional.

A good idea can sit peacefully in the backlog until the right problem makes it worth building.

---
