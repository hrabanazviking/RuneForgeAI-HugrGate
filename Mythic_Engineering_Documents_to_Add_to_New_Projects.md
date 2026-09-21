# Mythic Engineering Documents to Add to All New Projects

---

## **Priority One: Immediate**

**`AGENT_ONBOARDING.md`** — The first file any new AI agent reads before touching code. Thirty seconds to comprehend the project's purpose, its taboos, its current state. Links to the doctrine, the capability ledger, the task queue. Without this, agents wander blindly and produce garbage.

**`TESTING_PROTOCOL.md`** — Exactly how tests are structured, where they live, how to run them, what constitutes adequate coverage for each domain. The doctrine says "test everything" but does not specify how. This fills that gap. Includes the verification checklist an Auditor runs before approving any capability ledger upgrade.

**`GIT_DISCIPLINE.md`** — Branch naming conventions, commit message format expanded with examples, PR requirements, when to squash, when to preserve history. The doctrine mentions commit format briefly. This document makes it unambiguous. Agents who cannot follow git discipline cannot contribute safely.

---

## **Priority Two: Near-Term**

**`PERFORMANCE_BUDGETS.md`** — Concrete targets for inference latency, token throughput, memory overhead, startup time. Without budgets, "fast" means nothing. This document defines what performance success looks like numerically. Example budget: single-user 7B Q4 inference at 30+ tokens per second on 8GB VRAM. Auditors check against these numbers.

**`DEPENDENCY_POLICY.md`** — What external libraries are permitted, what requires justification, what is forbidden. This document draws the line clearly. If an agent wants to pull in a crate or a module, they check this document first.

**`HARDWARE_TARGETS.md`** — The specific hardware configurations the project supports and optimizes for. Consumer GPUs, edge devices, Raspberry Pi class hardware. Each tier has expected performance envelopes. Agents need to know whether they are optimizing for an RTX 4090 or a Jetson Nano before writing kernel code.

---

## **Priority Three: Structural**

**`SECURITY_POSTURE.md`** — Threat models. What we defend against: malicious GGUF files, prompt injection through model weights, memory exhaustion attacks via crafted requests. What we do not defend against: network intrusion (assume local network is trusted). Agents handling file parsing or request processing must read this.

**`ERROR_TAXONOMY.md`** — The standardized error types used across all domains. Currently the doctrine shows `Result[T, E]` patterns but does not enumerate the error enums. This document catalogs every error type, its meaning, and when to use it. Prevents agents from inventing bespoke error types that fracture the error handling landscape.

**`DATA_FORMATS.md`** — Specifications for every data file format the project uses. Config files, model metadata, tokenizer vocabularies, capability ledger entries. If an agent creates a new data file, the format goes here first. Prevents format proliferation where every agent invents their own schema.

---

## **Priority Four: Nice to Have**

**`DEBUGGING_PLAYBOOK.md`** — Known failure modes and their diagnostic procedures. When inference hangs, check these five things. When tokenization produces garbage, check these three things. Builds institutional memory for troubleshooting. Particularly useful for agents who inherit buggy code from predecessors.

**`GLOSSARY.md`** — Norse mythological terms used throughout the codebase mapped to their technical equivalents. Helps agents who do not know the mythology understand the naming scheme without guessing.

---
