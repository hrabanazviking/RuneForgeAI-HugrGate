# Clean-Room Policy — RuneForgeAI-HugrGate

HugrGate is developed as an **independent implementation of general
decision-inference concepts**, not as a reconstruction of any proprietary service.

## Hard Rules

Contributors must not:

- use proprietary model outputs to train, distill, or tune HugrGate
- reverse engineer proprietary decision services
- attempt to infer proprietary model architecture
- copy proprietary SDK implementations or API schemas
- copy proprietary examples, documentation, or benchmarks
- reproduce proprietary benchmarks verbatim
- use confidential or leaked technical material
- submit code derived from non-compatible-licensed sources
- describe the project as a drop-in clone of a proprietary product

## Proprietary-Service Firewall

Developers implementing the core must **not use proprietary decision
services as behavioral oracles**. Testing uses independently constructed
datasets and open models.

## Research Sources (preferred)

- textbooks and academic papers
- public standards
- open-source implementations with compatible licenses
- public-domain mathematical methods
- independently developed benchmarks
- well-established machine-learning techniques

## Architecture Decision Records

Important choices are documented in `docs/adr/` with: problem, public
references used, alternatives considered, independent rationale, license
info for dependencies.
