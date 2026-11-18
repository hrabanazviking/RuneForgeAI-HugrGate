# HugrGate — Tvíheimr Readiness Roadmap

**Owner-directed, 2026-11-18.** Volmarr Wyrd's ruling: source projects are improved **first, in their own houses**, and only then called into Tvíheimr (private repo hrabanazviking/Tviheimr, Connector Fabric, doc 26; decision ADR-010 there). This roadmap is HugrGate's own improvement road to being ready for that call. It changes nothing about HugrGate's existing roadmaps; it adds the Tvíheimr-facing line of work.

## What Tvíheimr needs from HugrGate
Tvíheimr's Connector Fabric puts HugrGate on the event road as its **fast decision layer**: triage of connector event streams, escalation decisions, routing judgment, anomaly watch, honest load shedding — and the same judgment serving two sisters: reflexes inside Verdandi, and salience judgment over Aurelia's sensation stream. Tvíheimr also hosts HugrGate as a **decision server on the new computer** (ROG Flow Z13): rules and classifiers first, a small fast local model kept warm behind them.

## Slices

### HG-T1 — Decision-server form
A long-running local server shape for HugrGate: request/response judgment API plus an event-intake endpoint, health endpoint, structured logging. Runs as a plain process under its operator's control; any resident-service form is the owner's separate explicit decision, never assumed.
**Gate:** server answers judgment requests and event batches on localhost with the existing test suite still green; startup/shutdown are clean and boring.

### HG-T2 — Small-fast-model judgment backend
A local-model backend for the judgments rules/classifiers cannot settle, using a small fast model served locally (Ollama-shaped endpoint). Model pick is by benchmark (latency + judgment accuracy on a fixed case set), recorded with numbers.
**Gate:** benchmark report banked — median judgment latency and accuracy vs the rules-only path; the model path is used only where the case set proves it earns its cost.

### HG-T3 — Event-stream triage profile
A triage profile for connector event streams: input schema (source, kind, time, payload digest), verdict schema (urgency, route, escalate yes/no, basis). Deterministic-first: identical events give identical verdicts unless a model judgment is explicitly in the loop, in which case the basis says so.
**Gate:** a recorded fixture stream of synthetic world events is triaged end-to-end; verdicts match the expected table; every verdict carries its basis; nothing is dropped silently — shedding is a verdict, logged like any other.

### HG-T4 — Reflex API for Verdandi
The declared-reflex surface: a consumer (Verdandi) registers reflexes (trigger pattern → named action), HugrGate judges incoming events against them and returns fire/no-fire with basis, at decision-runtime latency. HugrGate judges; the consumer acts and records.
**Gate:** fixture reflex set fires exactly on its patterns and no others; latency measured and recorded; undeclared patterns cannot fire.

### HG-T5 — Aurelia sensation-stream profile
A judgment profile for sensation events: salience, genuine state change vs noise, urgency. Tuned with Aurelia's own event schema (her house defines it; this slice consumes it).
**Gate:** on Aurelia's recorded fixture stream, salience verdicts match her expected table; noise rejection rate and miss rate both reported honestly.

### HG-T6 — Judgment provenance ledger
Every judgment — rules, classifier, or model — is recorded with its basis, inputs digest, and latency, in an append-only local ledger a caller can audit.
**Gate:** any verdict in the fixture runs can be traced to its ledger entry; the ledger survives restart; no verdict exists without an entry.

## Ready for Tvíheimr — the gate
HugrGate is **ready** when HG-T1…HG-T6 are banked with their gate evidence, the full existing HugrGate suite still passes, and a Tvíheimr-side fixture consumer (the fabric's admission harness) can call the decision server and receive triage, reflex and salience verdicts within the latency budgets recorded here. Until then, Tvíheimr's HugrGate-dependent connector work waits — by the owner's ruling, correctly.
