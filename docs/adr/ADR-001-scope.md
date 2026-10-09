# ADR-001: Project Scope and Identity

**Date:** 2026-10-09
**Status:** Accepted

## Problem

What is HugrGate, precisely, and what is it not?

## Decision

HugrGate is an open decision runtime and interface for adding
probabilistic machine judgment to ordinary program logic — not a model,
not a vendor SDK, not a chatbot, not a text generator.

It is defined by the **decision contract** (DecisionSpec → DecisionResult),
not by any inference implementation.

## Rationale

- Applications need bounded machine judgment without vendor lock-in.
- The intelligence ladder (rules → classifiers → local models → abstain)
  keeps compute proportional to problem difficulty.
- Clean-room development from public methods (Platt scaling, isotonic
  regression, temperature scaling, NLI, constrained decoding) gives the
  project an independent intellectual lineage.

## References

- README.md (project philosophy)
- HugrGate_ROADMAP.md (16-phase plan)
- HugrGate_Plundering_Guide.md (provenance rules)
- CLEAN_ROOM.md

## Consequences

- No proprietary API compatibility goals.
- No model distillation from proprietary outputs.
- Patent/FTO review before serious commercial use.
