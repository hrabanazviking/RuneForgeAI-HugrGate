# RuneForgeAI HugrGate --- Gjallarbrú 500-Slice Moonshot Roadmap

**Codename:** Gjallarbrú\
**Scope:** 500 individually verifiable engineering slices\
**Structure:** 20 campaigns × 25 slices\
**Target:** Transform HugrGate from a fast-growing alpha into an
unusually advanced, local-first, model-agnostic bounded-decision runtime
and research platform.\
**Primary implementation agent:** Yrsa, Viking seiðr witch / Meta Muse
AI engineer\
**Human architect and final authority:** Volmarr Wyrd\
**Method:** Mythic Engineering

> **Deterministic where possible. Probabilistic where useful. Generative
> only where necessary.**

------------------------------------------------------------------------

## 0. Mission

Gjallarbrú is not a feature checklist. It is a 500-slice engineering
campaign intended to force HugrGate through repeated cycles of
implementation, measurement, attack, repair, integration, and
verification.

The roadmap assumes that earlier HugrGate roadmaps have already produced
a substantial codebase. Existing functionality does **not**
automatically satisfy a slice. If the requested capability already
exists, Yrsa must inspect it, test it, identify weaknesses, improve it,
benchmark it, harden it, or prove through evidence that it already meets
the slice's acceptance criteria.

The goal is depth, not checkbox velocity.

## 1. Yrsa Execution Law

For every slice:

1.  Inspect the current repository before changing anything.
2.  Reuse sound existing architecture rather than duplicating it.
3.  Produce real executable implementation where the slice calls for
    implementation.
4.  Do not substitute pseudo-code, TODOs, placeholder functions, empty
    adapters, fake benchmarks, or documentation claims for working
    functionality.
5.  Add or update tests appropriate to the change.
6.  Run the narrowest relevant tests during implementation, then the
    appropriate broader suite before declaring the slice complete.
7.  Preserve backward compatibility unless the slice explicitly
    authorizes a breaking change.
8.  Record significant architectural choices.
9.  Update documentation when public behavior changes.
10. Leave an observable artifact: code, test, benchmark, schema, report,
    migration, validated documentation, or other inspectable evidence.
11. If the feature already exists, attack and improve it instead of
    marking the slice complete.
12. Never invent test results, benchmark numbers, hardware results,
    compatibility claims, or security guarantees.
13. When hardware or external services are unavailable, build the
    testable abstraction and clearly mark what still requires real-world
    validation.
14. Prefer bounded, typed, auditable behavior over opaque convenience.
15. Preserve HugrGate's local-first and replaceable-intelligence
    philosophy.

## 2. Definition of Done for a Slice

A slice is complete only when all applicable items are true:

-   implementation is present and integrated;
-   tests exist and pass;
-   public interfaces are typed and documented;
-   error/failure behavior is deliberate;
-   privacy implications are considered;
-   provenance/observability is integrated where relevant;
-   benchmarks are updated where performance or quality could change;
-   no new accidental TODO/stub debt was introduced;
-   the change works with the project's supported installation profile;
-   repository status/documentation reflects reality.

## 3. Anti-Checkbox Rule

A 500-slice roadmap can fail by becoming 500 tiny clerical edits. Avoid
that.

A slice may contain a substantial subsystem. Yrsa is explicitly
authorized to make each slice as deep as necessary. File creation alone
is never an accomplishment. A class name alone is never an
implementation. A test that merely asserts `True` is not a test. A
benchmark that measures nothing meaningful is not a benchmark.

**Every slice must make HugrGate observably stronger.**

## 4. Cross-Campaign Gates

At the end of every 25-slice campaign:

-   run the complete relevant test suite;
-   perform a regression review;
-   inspect new dependencies;
-   update CHANGELOG/roadmap status;
-   verify README claims still match reality;
-   record unresolved debt;
-   create a campaign completion report;
-   do not hide failures to preserve apparent velocity.

------------------------------------------------------------------------

# Campaign I --- Iron Foundation

**Mission:** Audit and harden the existing codebase before expanding it.

## Slice 001 --- Repository truth audit

**Objective:** Advance the campaign mission by completing **Repository
truth audit** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 002 --- Architecture map regeneration

**Objective:** Advance the campaign mission by completing **Architecture
map regeneration** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 003 --- Public API inventory

**Objective:** Advance the campaign mission by completing **Public API
inventory** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 004 --- Dependency graph audit

**Objective:** Advance the campaign mission by completing **Dependency
graph audit** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 005 --- Dead-code elimination

**Objective:** Advance the campaign mission by completing **Dead-code
elimination** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 006 --- Type-system hardening

**Objective:** Advance the campaign mission by completing **Type-system
hardening** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 007 --- Exception taxonomy hardening

**Objective:** Advance the campaign mission by completing **Exception
taxonomy hardening** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 008 --- Configuration normalization

**Objective:** Advance the campaign mission by completing
**Configuration normalization** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 009 --- Logging architecture

**Objective:** Advance the campaign mission by completing **Logging
architecture** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 010 --- Determinism audit

**Objective:** Advance the campaign mission by completing **Determinism
audit** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 011 --- State validation hardening

**Objective:** Advance the campaign mission by completing **State
validation hardening** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 012 --- Result invariant hardening

**Objective:** Advance the campaign mission by completing **Result
invariant hardening** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 013 --- Policy invariant hardening

**Objective:** Advance the campaign mission by completing **Policy
invariant hardening** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 014 --- Backend registry hardening

**Objective:** Advance the campaign mission by completing **Backend
registry hardening** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 015 --- Provenance integrity

**Objective:** Advance the campaign mission by completing **Provenance
integrity** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 016 --- Serialization contracts

**Objective:** Advance the campaign mission by completing
**Serialization contracts** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 017 --- Thread-safety baseline

**Objective:** Advance the campaign mission by completing
**Thread-safety baseline** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 018 --- Async-readiness audit

**Objective:** Advance the campaign mission by completing
**Async-readiness audit** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 019 --- Resource lifecycle management

**Objective:** Advance the campaign mission by completing **Resource
lifecycle management** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 020 --- Package boundary cleanup

**Objective:** Advance the campaign mission by completing **Package
boundary cleanup** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 021 --- Import-cycle elimination

**Objective:** Advance the campaign mission by completing **Import-cycle
elimination** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 022 --- Static-analysis gate

**Objective:** Advance the campaign mission by completing
**Static-analysis gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 023 --- Test taxonomy rebuild

**Objective:** Advance the campaign mission by completing **Test
taxonomy rebuild** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 024 --- Coverage gap attack

**Objective:** Advance the campaign mission by completing **Coverage gap
attack** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 025 --- Foundation release gate

**Objective:** Advance the campaign mission by completing **Foundation
release gate** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign II --- Contract Engine

**Mission:** Turn DecisionSpec into a rich, extensible machine-decision
contract language.

## Slice 026 --- Contract schema v2

**Objective:** Advance the campaign mission by completing **Contract
schema v2** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 027 --- Contract version negotiation

**Objective:** Advance the campaign mission by completing **Contract
version negotiation** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 028 --- Nested categorical contracts

**Objective:** Advance the campaign mission by completing **Nested
categorical contracts** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 029 --- Hierarchical labels

**Objective:** Advance the campaign mission by completing **Hierarchical
labels** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 030 --- Structured composite decisions

**Objective:** Advance the campaign mission by completing **Structured
composite decisions** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 031 --- Conditional decision fields

**Objective:** Advance the campaign mission by completing **Conditional
decision fields** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 032 --- Cross-field constraints

**Objective:** Advance the campaign mission by completing **Cross-field
constraints** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 033 --- Rich ordinal semantics

**Objective:** Advance the campaign mission by completing **Rich ordinal
semantics** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 034 --- Numeric uncertainty intervals

**Objective:** Advance the campaign mission by completing **Numeric
uncertainty intervals** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 035 --- Distribution constraints

**Objective:** Advance the campaign mission by completing **Distribution
constraints** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 036 --- Multilabel cardinality constraints

**Objective:** Advance the campaign mission by completing **Multilabel
cardinality constraints** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 037 --- Cost-sensitive decisions

**Objective:** Advance the campaign mission by completing
**Cost-sensitive decisions** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 038 --- Utility matrices

**Objective:** Advance the campaign mission by completing **Utility
matrices** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 039 --- Risk matrices

**Objective:** Advance the campaign mission by completing **Risk
matrices** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 040 --- Decision deadlines

**Objective:** Advance the campaign mission by completing **Decision
deadlines** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 041 --- Context schemas

**Objective:** Advance the campaign mission by completing **Context
schemas** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 042 --- Input feature contracts

**Objective:** Advance the campaign mission by completing **Input
feature contracts** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 043 --- Output explanation contracts

**Objective:** Advance the campaign mission by completing **Output
explanation contracts** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 044 --- Contract inheritance

**Objective:** Advance the campaign mission by completing **Contract
inheritance** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 045 --- Contract composition

**Objective:** Advance the campaign mission by completing **Contract
composition** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 046 --- Contract templates

**Objective:** Advance the campaign mission by completing **Contract
templates** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 047 --- Contract migration engine

**Objective:** Advance the campaign mission by completing **Contract
migration engine** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 048 --- Contract linting

**Objective:** Advance the campaign mission by completing **Contract
linting** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 049 --- Contract fuzzing

**Objective:** Advance the campaign mission by completing **Contract
fuzzing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 050 --- Contract Engine release gate

**Objective:** Advance the campaign mission by completing **Contract
Engine release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign III --- Intelligence Ladder II

**Mission:** Evolve routing from a static cascade into a sophisticated
decision-routing engine.

## Slice 051 --- Router architecture v2

**Objective:** Advance the campaign mission by completing **Router
architecture v2** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 052 --- Dynamic rung construction

**Objective:** Advance the campaign mission by completing **Dynamic rung
construction** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 053 --- Per-request ladder synthesis

**Objective:** Advance the campaign mission by completing **Per-request
ladder synthesis** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 054 --- Capability scoring

**Objective:** Advance the campaign mission by completing **Capability
scoring** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 055 --- Confidence-aware routing

**Objective:** Advance the campaign mission by completing
**Confidence-aware routing** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 056 --- Latency-aware routing

**Objective:** Advance the campaign mission by completing
**Latency-aware routing** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 057 --- Cost-aware routing

**Objective:** Advance the campaign mission by completing **Cost-aware
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 058 --- Energy-aware routing

**Objective:** Advance the campaign mission by completing **Energy-aware
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 059 --- Memory-aware routing

**Objective:** Advance the campaign mission by completing **Memory-aware
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 060 --- Privacy-aware routing v2

**Objective:** Advance the campaign mission by completing
**Privacy-aware routing v2** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 061 --- Hardware-aware routing

**Objective:** Advance the campaign mission by completing
**Hardware-aware routing** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 062 --- Availability-aware routing

**Objective:** Advance the campaign mission by completing
**Availability-aware routing** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 063 --- Quality-of-service classes

**Objective:** Advance the campaign mission by completing
**Quality-of-service classes** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 064 --- Parallel speculative rungs

**Objective:** Advance the campaign mission by completing **Parallel
speculative rungs** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 065 --- Hedged inference

**Objective:** Advance the campaign mission by completing **Hedged
inference** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 066 --- Early-exit routing

**Objective:** Advance the campaign mission by completing **Early-exit
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 067 --- Fallback graph routing

**Objective:** Advance the campaign mission by completing **Fallback
graph routing** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 068 --- Conditional routing DAGs

**Objective:** Advance the campaign mission by completing **Conditional
routing DAGs** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 069 --- Route explanation

**Objective:** Advance the campaign mission by completing **Route
explanation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 070 --- Route replay

**Objective:** Advance the campaign mission by completing **Route
replay** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 071 --- Route simulation

**Objective:** Advance the campaign mission by completing **Route
simulation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 072 --- Route policy DSL

**Objective:** Advance the campaign mission by completing **Route policy
DSL** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 073 --- Routing fuzz tests

**Objective:** Advance the campaign mission by completing **Routing fuzz
tests** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 074 --- Routing stress benchmark

**Objective:** Advance the campaign mission by completing **Routing
stress benchmark** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 075 --- Ladder II release gate

**Objective:** Advance the campaign mission by completing **Ladder II
release gate** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign IV --- Calibration Forge

**Mission:** Build a serious uncertainty, calibration, and
selective-prediction laboratory.

## Slice 076 --- Calibration architecture v2

**Objective:** Advance the campaign mission by completing **Calibration
architecture v2** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 077 --- Per-class calibration

**Objective:** Advance the campaign mission by completing **Per-class
calibration** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 078 --- Group calibration

**Objective:** Advance the campaign mission by completing **Group
calibration** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 079 --- Online calibration

**Objective:** Advance the campaign mission by completing **Online
calibration** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 080 --- Sliding-window calibration

**Objective:** Advance the campaign mission by completing
**Sliding-window calibration** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 081 --- Bayesian calibration research adapter

**Objective:** Advance the campaign mission by completing **Bayesian
calibration research adapter** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 082 --- Conformal classification

**Objective:** Advance the campaign mission by completing **Conformal
classification** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 083 --- Conformal regression

**Objective:** Advance the campaign mission by completing **Conformal
regression** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 084 --- Prediction sets

**Objective:** Advance the campaign mission by completing **Prediction
sets** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 085 --- Coverage guarantees tooling

**Objective:** Advance the campaign mission by completing **Coverage
guarantees tooling** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 086 --- Selective prediction curves

**Objective:** Advance the campaign mission by completing **Selective
prediction curves** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 087 --- Risk-coverage curves

**Objective:** Advance the campaign mission by completing
**Risk-coverage curves** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 088 --- Calibration under drift

**Objective:** Advance the campaign mission by completing **Calibration
under drift** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 089 --- Calibration under imbalance

**Objective:** Advance the campaign mission by completing **Calibration
under imbalance** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 090 --- Calibration under shift

**Objective:** Advance the campaign mission by completing **Calibration
under shift** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 091 --- Calibration registry

**Objective:** Advance the campaign mission by completing **Calibration
registry** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 092 --- Calibration auto-selection

**Objective:** Advance the campaign mission by completing **Calibration
auto-selection** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 093 --- Calibration ensemble

**Objective:** Advance the campaign mission by completing **Calibration
ensemble** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 094 --- Uncertainty decomposition

**Objective:** Advance the campaign mission by completing **Uncertainty
decomposition** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 095 --- Epistemic uncertainty adapters

**Objective:** Advance the campaign mission by completing **Epistemic
uncertainty adapters** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 096 --- Aleatoric uncertainty adapters

**Objective:** Advance the campaign mission by completing **Aleatoric
uncertainty adapters** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 097 --- Calibration visualization data

**Objective:** Advance the campaign mission by completing **Calibration
visualization data** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 098 --- Calibration adversarial tests

**Objective:** Advance the campaign mission by completing **Calibration
adversarial tests** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 099 --- Calibration benchmark suite

**Objective:** Advance the campaign mission by completing **Calibration
benchmark suite** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 100 --- Calibration Forge release gate

**Objective:** Advance the campaign mission by completing **Calibration
Forge release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign V --- Ensemble Intelligence

**Mission:** Combine heterogeneous decision systems without losing
boundedness or auditability.

## Slice 101 --- Ensemble API

**Objective:** Advance the campaign mission by completing **Ensemble
API** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 102 --- Hard voting

**Objective:** Advance the campaign mission by completing **Hard
voting** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 103 --- Soft voting

**Objective:** Advance the campaign mission by completing **Soft
voting** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 104 --- Weighted voting

**Objective:** Advance the campaign mission by completing **Weighted
voting** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 105 --- Confidence-weighted voting

**Objective:** Advance the campaign mission by completing
**Confidence-weighted voting** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 106 --- Bayesian model averaging adapter

**Objective:** Advance the campaign mission by completing **Bayesian
model averaging adapter** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 107 --- Stacking engine

**Objective:** Advance the campaign mission by completing **Stacking
engine** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 108 --- Blending engine

**Objective:** Advance the campaign mission by completing **Blending
engine** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 109 --- Mixture-of-experts router

**Objective:** Advance the campaign mission by completing
**Mixture-of-experts router** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 110 --- Diversity metrics

**Objective:** Advance the campaign mission by completing **Diversity
metrics** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 111 --- Disagreement detection

**Objective:** Advance the campaign mission by completing **Disagreement
detection** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 112 --- Disagreement escalation

**Objective:** Advance the campaign mission by completing **Disagreement
escalation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 113 --- Consensus thresholds

**Objective:** Advance the campaign mission by completing **Consensus
thresholds** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 114 --- Minority-report preservation

**Objective:** Advance the campaign mission by completing
**Minority-report preservation** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 115 --- Correlated-error detection

**Objective:** Advance the campaign mission by completing
**Correlated-error detection** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 116 --- Backend reliability weighting

**Objective:** Advance the campaign mission by completing **Backend
reliability weighting** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 117 --- Dynamic ensemble membership

**Objective:** Advance the campaign mission by completing **Dynamic
ensemble membership** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 118 --- Ensemble calibration

**Objective:** Advance the campaign mission by completing **Ensemble
calibration** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 119 --- Ensemble provenance

**Objective:** Advance the campaign mission by completing **Ensemble
provenance** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 120 --- Ensemble explanations

**Objective:** Advance the campaign mission by completing **Ensemble
explanations** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 121 --- Ensemble caching

**Objective:** Advance the campaign mission by completing **Ensemble
caching** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 122 --- Ensemble batch mode

**Objective:** Advance the campaign mission by completing **Ensemble
batch mode** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 123 --- Ensemble adversarial tests

**Objective:** Advance the campaign mission by completing **Ensemble
adversarial tests** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 124 --- Ensemble benchmarks

**Objective:** Advance the campaign mission by completing **Ensemble
benchmarks** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 125 --- Ensemble release gate

**Objective:** Advance the campaign mission by completing **Ensemble
release gate** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign VI --- Adaptive Routing

**Mission:** Let HugrGate learn which inference path works best for each
workload.

## Slice 126 --- Routing telemetry dataset

**Objective:** Advance the campaign mission by completing **Routing
telemetry dataset** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 127 --- Outcome feedback API

**Objective:** Advance the campaign mission by completing **Outcome
feedback API** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 128 --- Delayed-label ingestion

**Objective:** Advance the campaign mission by completing
**Delayed-label ingestion** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 129 --- Router feature extraction

**Objective:** Advance the campaign mission by completing **Router
feature extraction** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 130 --- Contextual bandit adapter

**Objective:** Advance the campaign mission by completing **Contextual
bandit adapter** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 131 --- Offline policy learning

**Objective:** Advance the campaign mission by completing **Offline
policy learning** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 132 --- Cost-quality objective

**Objective:** Advance the campaign mission by completing **Cost-quality
objective** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 133 --- Latency-quality objective

**Objective:** Advance the campaign mission by completing
**Latency-quality objective** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 134 --- Energy-quality objective

**Objective:** Advance the campaign mission by completing
**Energy-quality objective** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 135 --- Privacy-constrained objective

**Objective:** Advance the campaign mission by completing
**Privacy-constrained objective** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 136 --- Multi-objective routing

**Objective:** Advance the campaign mission by completing
**Multi-objective routing** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 137 --- Backend competence profiles

**Objective:** Advance the campaign mission by completing **Backend
competence profiles** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 138 --- Per-domain competence

**Objective:** Advance the campaign mission by completing **Per-domain
competence** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 139 --- Per-contract competence

**Objective:** Advance the campaign mission by completing **Per-contract
competence** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 140 --- Cold-start routing

**Objective:** Advance the campaign mission by completing **Cold-start
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 141 --- Exploration controls

**Objective:** Advance the campaign mission by completing **Exploration
controls** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 142 --- Safe exploration

**Objective:** Advance the campaign mission by completing **Safe
exploration** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 143 --- Router shadow mode

**Objective:** Advance the campaign mission by completing **Router
shadow mode** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 144 --- Counterfactual route evaluation

**Objective:** Advance the campaign mission by completing
**Counterfactual route evaluation** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 145 --- Router rollback

**Objective:** Advance the campaign mission by completing **Router
rollback** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 146 --- Adaptive policy versioning

**Objective:** Advance the campaign mission by completing **Adaptive
policy versioning** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 147 --- Adaptive-route explanations

**Objective:** Advance the campaign mission by completing
**Adaptive-route explanations** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 148 --- Adaptive-route drift detection

**Objective:** Advance the campaign mission by completing
**Adaptive-route drift detection** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 149 --- Adaptive routing benchmark

**Objective:** Advance the campaign mission by completing **Adaptive
routing benchmark** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 150 --- Adaptive Routing release gate

**Objective:** Advance the campaign mission by completing **Adaptive
Routing release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign VII --- Local Model Fabric

**Mission:** Make local inference a first-class pluggable fabric across
common runtimes.

## Slice 151 --- Local runtime interface v2

**Objective:** Advance the campaign mission by completing **Local
runtime interface v2** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 152 --- llama.cpp adapter

**Objective:** Advance the campaign mission by completing **llama.cpp
adapter** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 153 --- Ollama-compatible adapter

**Objective:** Advance the campaign mission by completing
**Ollama-compatible adapter** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 154 --- ONNX Runtime adapter

**Objective:** Advance the campaign mission by completing **ONNX Runtime
adapter** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 155 --- Transformers adapter

**Objective:** Advance the campaign mission by completing **Transformers
adapter** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 156 --- vLLM local adapter

**Objective:** Advance the campaign mission by completing **vLLM local
adapter** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 157 --- MLX adapter boundary

**Objective:** Advance the campaign mission by completing **MLX adapter
boundary** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 158 --- OpenVINO adapter

**Objective:** Advance the campaign mission by completing **OpenVINO
adapter** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 159 --- TensorRT adapter boundary

**Objective:** Advance the campaign mission by completing **TensorRT
adapter boundary** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 160 --- GGUF model discovery

**Objective:** Advance the campaign mission by completing **GGUF model
discovery** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 161 --- Model metadata scanner

**Objective:** Advance the campaign mission by completing **Model
metadata scanner** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 162 --- Model capability probing

**Objective:** Advance the campaign mission by completing **Model
capability probing** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 163 --- Structured-output adapter

**Objective:** Advance the campaign mission by completing
**Structured-output adapter** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 164 --- Grammar-constrained decoding

**Objective:** Advance the campaign mission by completing
**Grammar-constrained decoding** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 165 --- JSON-schema constrained decoding

**Objective:** Advance the campaign mission by completing **JSON-schema
constrained decoding** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 166 --- Local NLI model pack

**Objective:** Advance the campaign mission by completing **Local NLI
model pack** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 167 --- Local embedding model pack

**Objective:** Advance the campaign mission by completing **Local
embedding model pack** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 168 --- Local classifier model pack

**Objective:** Advance the campaign mission by completing **Local
classifier model pack** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 169 --- Model warmup manager

**Objective:** Advance the campaign mission by completing **Model warmup
manager** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 170 --- Model residency manager

**Objective:** Advance the campaign mission by completing **Model
residency manager** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 171 --- Model eviction policy

**Objective:** Advance the campaign mission by completing **Model
eviction policy** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 172 --- Model health probes

**Objective:** Advance the campaign mission by completing **Model health
probes** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 173 --- Local runtime conformance tests

**Objective:** Advance the campaign mission by completing **Local
runtime conformance tests** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 174 --- Local runtime benchmark matrix

**Objective:** Advance the campaign mission by completing **Local
runtime benchmark matrix** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 175 --- Local Model Fabric release gate

**Objective:** Advance the campaign mission by completing **Local Model
Fabric release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign VIII --- Edge Intelligence

**Mission:** Push HugrGate onto constrained ARM, SBC, NPU, and
heterogeneous edge systems.

## Slice 176 --- ARM64 compatibility audit

**Objective:** Advance the campaign mission by completing **ARM64
compatibility audit** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 177 --- Raspberry Pi baseline

**Objective:** Advance the campaign mission by completing **Raspberry Pi
baseline** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 178 --- Low-RAM operating mode

**Objective:** Advance the campaign mission by completing **Low-RAM
operating mode** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 179 --- CPU affinity controls

**Objective:** Advance the campaign mission by completing **CPU affinity
controls** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 180 --- Thermal-aware routing

**Objective:** Advance the campaign mission by completing
**Thermal-aware routing** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 181 --- Power-budget routing

**Objective:** Advance the campaign mission by completing **Power-budget
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 182 --- Quantized-model profiles

**Objective:** Advance the campaign mission by completing
**Quantized-model profiles** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 183 --- INT8 inference path

**Objective:** Advance the campaign mission by completing **INT8
inference path** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 184 --- INT4 adapter support

**Objective:** Advance the campaign mission by completing **INT4 adapter
support** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 185 --- NPU capability abstraction

**Objective:** Advance the campaign mission by completing **NPU
capability abstraction** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 186 --- Hailo adapter boundary

**Objective:** Advance the campaign mission by completing **Hailo
adapter boundary** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 187 --- Jetson adapter boundary

**Objective:** Advance the campaign mission by completing **Jetson
adapter boundary** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 188 --- OpenVINO NPU path

**Objective:** Advance the campaign mission by completing **OpenVINO NPU
path** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 189 --- Edge model residency

**Objective:** Advance the campaign mission by completing **Edge model
residency** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 190 --- Edge cache tuning

**Objective:** Advance the campaign mission by completing **Edge cache
tuning** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 191 --- Flash-wear-aware storage

**Objective:** Advance the campaign mission by completing
**Flash-wear-aware storage** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 192 --- Offline-first bootstrap

**Objective:** Advance the campaign mission by completing
**Offline-first bootstrap** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 193 --- Intermittent-power recovery

**Objective:** Advance the campaign mission by completing
**Intermittent-power recovery** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 194 --- Edge watchdog

**Objective:** Advance the campaign mission by completing **Edge
watchdog** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 195 --- Edge telemetry lite

**Objective:** Advance the campaign mission by completing **Edge
telemetry lite** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 196 --- Edge benchmark harness

**Objective:** Advance the campaign mission by completing **Edge
benchmark harness** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 197 --- Pi benchmark suite

**Objective:** Advance the campaign mission by completing **Pi benchmark
suite** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 198 --- Jetson benchmark suite

**Objective:** Advance the campaign mission by completing **Jetson
benchmark suite** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 199 --- Edge failure testing

**Objective:** Advance the campaign mission by completing **Edge failure
testing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 200 --- Edge Intelligence release gate

**Objective:** Advance the campaign mission by completing **Edge
Intelligence release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign IX --- Distributed HugrGate

**Mission:** Allow multiple HugrGate nodes to cooperate while preserving
policy and provenance.

## Slice 201 --- Node protocol design

**Objective:** Advance the campaign mission by completing **Node
protocol design** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 202 --- Node identity

**Objective:** Advance the campaign mission by completing **Node
identity** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 203 --- Node capability advertisement

**Objective:** Advance the campaign mission by completing **Node
capability advertisement** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 204 --- Node discovery

**Objective:** Advance the campaign mission by completing **Node
discovery** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 205 --- Static peer configuration

**Objective:** Advance the campaign mission by completing **Static peer
configuration** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 206 --- LAN discovery adapter

**Objective:** Advance the campaign mission by completing **LAN
discovery adapter** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 207 --- Remote decision RPC

**Objective:** Advance the campaign mission by completing **Remote
decision RPC** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 208 --- Mutual authentication

**Objective:** Advance the campaign mission by completing **Mutual
authentication** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 209 --- Encrypted transport

**Objective:** Advance the campaign mission by completing **Encrypted
transport** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 210 --- Policy propagation

**Objective:** Advance the campaign mission by completing **Policy
propagation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 211 --- Privacy boundary enforcement

**Objective:** Advance the campaign mission by completing **Privacy
boundary enforcement** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 212 --- Distributed ladder routing

**Objective:** Advance the campaign mission by completing **Distributed
ladder routing** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 213 --- Node health scoring

**Objective:** Advance the campaign mission by completing **Node health
scoring** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 214 --- Node latency scoring

**Objective:** Advance the campaign mission by completing **Node latency
scoring** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 215 --- Node cost scoring

**Objective:** Advance the campaign mission by completing **Node cost
scoring** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 216 --- Work stealing

**Objective:** Advance the campaign mission by completing **Work
stealing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 217 --- Distributed batching

**Objective:** Advance the campaign mission by completing **Distributed
batching** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 218 --- Backpressure protocol

**Objective:** Advance the campaign mission by completing **Backpressure
protocol** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 219 --- Network partition handling

**Objective:** Advance the campaign mission by completing **Network
partition handling** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 220 --- Offline peer recovery

**Objective:** Advance the campaign mission by completing **Offline peer
recovery** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 221 --- Distributed provenance

**Objective:** Advance the campaign mission by completing **Distributed
provenance** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 222 --- Trace correlation

**Objective:** Advance the campaign mission by completing **Trace
correlation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 223 --- Distributed chaos tests

**Objective:** Advance the campaign mission by completing **Distributed
chaos tests** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 224 --- Cluster benchmark suite

**Objective:** Advance the campaign mission by completing **Cluster
benchmark suite** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 225 --- Distributed release gate

**Objective:** Advance the campaign mission by completing **Distributed
release gate** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign X --- Privacy Fortress

**Mission:** Make data sovereignty and enforceable information-flow
constraints core architecture.

## Slice 226 --- Privacy classification v2

**Objective:** Advance the campaign mission by completing **Privacy
classification v2** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 227 --- Field-level sensitivity labels

**Objective:** Advance the campaign mission by completing **Field-level
sensitivity labels** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 228 --- Data-flow policy engine

**Objective:** Advance the campaign mission by completing **Data-flow
policy engine** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 229 --- Backend trust levels

**Objective:** Advance the campaign mission by completing **Backend
trust levels** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 230 --- Jurisdiction metadata

**Objective:** Advance the campaign mission by completing **Jurisdiction
metadata** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 231 --- Local-only field enforcement

**Objective:** Advance the campaign mission by completing **Local-only
field enforcement** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 232 --- Redaction pipeline v2

**Objective:** Advance the campaign mission by completing **Redaction
pipeline v2** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 233 --- Tokenization/pseudonymization

**Objective:** Advance the campaign mission by completing
**Tokenization/pseudonymization** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 234 --- Secret detection hooks

**Objective:** Advance the campaign mission by completing **Secret
detection hooks** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 235 --- PII detector interface

**Objective:** Advance the campaign mission by completing **PII detector
interface** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 236 --- Prompt/data minimization

**Objective:** Advance the campaign mission by completing **Prompt/data
minimization** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 237 --- Remote payload compiler

**Objective:** Advance the campaign mission by completing **Remote
payload compiler** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 238 --- Privacy-preserving provenance

**Objective:** Advance the campaign mission by completing
**Privacy-preserving provenance** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 239 --- Retention policies

**Objective:** Advance the campaign mission by completing **Retention
policies** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 240 --- Secure deletion hooks

**Objective:** Advance the campaign mission by completing **Secure
deletion hooks** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 241 --- Encrypted cache option

**Objective:** Advance the campaign mission by completing **Encrypted
cache option** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 242 --- Encrypted provenance option

**Objective:** Advance the campaign mission by completing **Encrypted
provenance option** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 243 --- Key-provider abstraction

**Objective:** Advance the campaign mission by completing **Key-provider
abstraction** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 244 --- Policy violation audit

**Objective:** Advance the campaign mission by completing **Policy
violation audit** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 245 --- Privacy dry-run mode

**Objective:** Advance the campaign mission by completing **Privacy
dry-run mode** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 246 --- Privacy explanation reports

**Objective:** Advance the campaign mission by completing **Privacy
explanation reports** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 247 --- Privacy fuzz tests

**Objective:** Advance the campaign mission by completing **Privacy fuzz
tests** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 248 --- Exfiltration simulation

**Objective:** Advance the campaign mission by completing **Exfiltration
simulation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 249 --- Privacy benchmark suite

**Objective:** Advance the campaign mission by completing **Privacy
benchmark suite** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 250 --- Privacy Fortress release gate

**Objective:** Advance the campaign mission by completing **Privacy
Fortress release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XI --- Reliability & Chaos

**Mission:** Engineer HugrGate to survive broken models, broken
networks, broken disks, and bad days.

## Slice 251 --- Chaos framework

**Objective:** Advance the campaign mission by completing **Chaos
framework** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 252 --- Backend crash injection

**Objective:** Advance the campaign mission by completing **Backend
crash injection** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 253 --- Backend hang injection

**Objective:** Advance the campaign mission by completing **Backend hang
injection** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 254 --- Latency injection

**Objective:** Advance the campaign mission by completing **Latency
injection** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 255 --- Error-rate injection

**Objective:** Advance the campaign mission by completing **Error-rate
injection** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 256 --- Malformed-result injection

**Objective:** Advance the campaign mission by completing
**Malformed-result injection** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 257 --- Corrupt-model simulation

**Objective:** Advance the campaign mission by completing
**Corrupt-model simulation** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 258 --- Cache corruption simulation

**Objective:** Advance the campaign mission by completing **Cache
corruption simulation** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 259 --- Disk-full simulation

**Objective:** Advance the campaign mission by completing **Disk-full
simulation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 260 --- Read-only filesystem test

**Objective:** Advance the campaign mission by completing **Read-only
filesystem test** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 261 --- Memory-pressure test

**Objective:** Advance the campaign mission by completing
**Memory-pressure test** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 262 --- CPU-starvation test

**Objective:** Advance the campaign mission by completing
**CPU-starvation test** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 263 --- Network-loss test

**Objective:** Advance the campaign mission by completing **Network-loss
test** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 264 --- Network-flap test

**Objective:** Advance the campaign mission by completing **Network-flap
test** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 265 --- Clock-skew test

**Objective:** Advance the campaign mission by completing **Clock-skew
test** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 266 --- Partial-service failure

**Objective:** Advance the campaign mission by completing
**Partial-service failure** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 267 --- Dependency failure matrix

**Objective:** Advance the campaign mission by completing **Dependency
failure matrix** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 268 --- Retry-budget system

**Objective:** Advance the campaign mission by completing **Retry-budget
system** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 269 --- Bulkhead isolation

**Objective:** Advance the campaign mission by completing **Bulkhead
isolation** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 270 --- Graceful degradation plans

**Objective:** Advance the campaign mission by completing **Graceful
degradation plans** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 271 --- Recovery verification

**Objective:** Advance the campaign mission by completing **Recovery
verification** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 272 --- Crash-only restart tests

**Objective:** Advance the campaign mission by completing **Crash-only
restart tests** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 273 --- Long-soak test

**Objective:** Advance the campaign mission by completing **Long-soak
test** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 274 --- Chaos scorecard

**Objective:** Advance the campaign mission by completing **Chaos
scorecard** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 275 --- Reliability release gate

**Objective:** Advance the campaign mission by completing **Reliability
release gate** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XII --- Performance Forge

**Mission:** Drive latency, throughput, memory use, and scheduling
efficiency to production-grade levels.

## Slice 276 --- Profiler integration

**Objective:** Advance the campaign mission by completing **Profiler
integration** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 277 --- Baseline flamegraphs

**Objective:** Advance the campaign mission by completing **Baseline
flamegraphs** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 278 --- Hot-path inventory

**Objective:** Advance the campaign mission by completing **Hot-path
inventory** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 279 --- Allocation profiling

**Objective:** Advance the campaign mission by completing **Allocation
profiling** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 280 --- Zero-copy opportunities

**Objective:** Advance the campaign mission by completing **Zero-copy
opportunities** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 281 --- Serialization optimization

**Objective:** Advance the campaign mission by completing
**Serialization optimization** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 282 --- Async core path

**Objective:** Advance the campaign mission by completing **Async core
path** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 283 --- Async backend API

**Objective:** Advance the campaign mission by completing **Async
backend API** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 284 --- Concurrent ladder execution

**Objective:** Advance the campaign mission by completing **Concurrent
ladder execution** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 285 --- Batch scheduler v2

**Objective:** Advance the campaign mission by completing **Batch
scheduler v2** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 286 --- Dynamic batching

**Objective:** Advance the campaign mission by completing **Dynamic
batching** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 287 --- Priority scheduling

**Objective:** Advance the campaign mission by completing **Priority
scheduling** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 288 --- Deadline scheduling

**Objective:** Advance the campaign mission by completing **Deadline
scheduling** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 289 --- Backpressure engine

**Objective:** Advance the campaign mission by completing **Backpressure
engine** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 290 --- Connection pooling

**Objective:** Advance the campaign mission by completing **Connection
pooling** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 291 --- Model-session pooling

**Objective:** Advance the campaign mission by completing
**Model-session pooling** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 292 --- Cache performance tuning

**Objective:** Advance the campaign mission by completing **Cache
performance tuning** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 293 --- Lock contention audit

**Objective:** Advance the campaign mission by completing **Lock
contention audit** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 294 --- Multiprocess mode

**Objective:** Advance the campaign mission by completing **Multiprocess
mode** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 295 --- Worker supervision

**Objective:** Advance the campaign mission by completing **Worker
supervision** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 296 --- NUMA awareness boundary

**Objective:** Advance the campaign mission by completing **NUMA
awareness boundary** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 297 --- GPU scheduling boundary

**Objective:** Advance the campaign mission by completing **GPU
scheduling boundary** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 298 --- Performance regression gates

**Objective:** Advance the campaign mission by completing **Performance
regression gates** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 299 --- Million-decision benchmark

**Objective:** Advance the campaign mission by completing
**Million-decision benchmark** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 300 --- Performance Forge release gate

**Objective:** Advance the campaign mission by completing **Performance
Forge release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XIII --- Decision Memory

**Mission:** Give the runtime useful historical context without turning
it into an opaque agent.

## Slice 301 --- Decision history API

**Objective:** Advance the campaign mission by completing **Decision
history API** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 302 --- Queryable provenance store

**Objective:** Advance the campaign mission by completing **Queryable
provenance store** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 303 --- Outcome attachment

**Objective:** Advance the campaign mission by completing **Outcome
attachment** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 304 --- Ground-truth attachment

**Objective:** Advance the campaign mission by completing **Ground-truth
attachment** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 305 --- Historical similarity search

**Objective:** Advance the campaign mission by completing **Historical
similarity search** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 306 --- Decision retrieval

**Objective:** Advance the campaign mission by completing **Decision
retrieval** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 307 --- Contextual memory policies

**Objective:** Advance the campaign mission by completing **Contextual
memory policies** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 308 --- Time-decay weighting

**Objective:** Advance the campaign mission by completing **Time-decay
weighting** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 309 --- Recency features

**Objective:** Advance the campaign mission by completing **Recency
features** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 310 --- Frequency features

**Objective:** Advance the campaign mission by completing **Frequency
features** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 311 --- Outcome-conditioned retrieval

**Objective:** Advance the campaign mission by completing
**Outcome-conditioned retrieval** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 312 --- Backend history features

**Objective:** Advance the campaign mission by completing **Backend
history features** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 313 --- Contract history features

**Objective:** Advance the campaign mission by completing **Contract
history features** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 314 --- Domain history profiles

**Objective:** Advance the campaign mission by completing **Domain
history profiles** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 315 --- Memory privacy controls

**Objective:** Advance the campaign mission by completing **Memory
privacy controls** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 316 --- Memory retention controls

**Objective:** Advance the campaign mission by completing **Memory
retention controls** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 317 --- Memory compaction

**Objective:** Advance the campaign mission by completing **Memory
compaction** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 318 --- Memory export/import

**Objective:** Advance the campaign mission by completing **Memory
export/import** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 319 --- Memory replay

**Objective:** Advance the campaign mission by completing **Memory
replay** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 320 --- Historical counterfactuals

**Objective:** Advance the campaign mission by completing **Historical
counterfactuals** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 321 --- Memory-assisted routing

**Objective:** Advance the campaign mission by completing
**Memory-assisted routing** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 322 --- Memory-assisted calibration

**Objective:** Advance the campaign mission by completing
**Memory-assisted calibration** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 323 --- Memory adversarial tests

**Objective:** Advance the campaign mission by completing **Memory
adversarial tests** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 324 --- Memory benchmark suite

**Objective:** Advance the campaign mission by completing **Memory
benchmark suite** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 325 --- Decision Memory release gate

**Objective:** Advance the campaign mission by completing **Decision
Memory release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XIV --- Observability

**Mission:** Make every important decision path measurable, inspectable,
and explainable.

## Slice 326 --- Metrics architecture

**Objective:** Advance the campaign mission by completing **Metrics
architecture** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 327 --- OpenTelemetry integration

**Objective:** Advance the campaign mission by completing
**OpenTelemetry integration** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 328 --- Trace architecture

**Objective:** Advance the campaign mission by completing **Trace
architecture** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 329 --- Decision trace spans

**Objective:** Advance the campaign mission by completing **Decision
trace spans** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 330 --- Backend trace spans

**Objective:** Advance the campaign mission by completing **Backend
trace spans** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 331 --- Routing trace spans

**Objective:** Advance the campaign mission by completing **Routing
trace spans** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 332 --- Calibration trace spans

**Objective:** Advance the campaign mission by completing **Calibration
trace spans** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 333 --- Structured log schema

**Objective:** Advance the campaign mission by completing **Structured
log schema** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 334 --- Prometheus metrics

**Objective:** Advance the campaign mission by completing **Prometheus
metrics** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 335 --- Health dashboard data

**Objective:** Advance the campaign mission by completing **Health
dashboard data** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 336 --- Latency histograms

**Objective:** Advance the campaign mission by completing **Latency
histograms** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 337 --- Confidence histograms

**Objective:** Advance the campaign mission by completing **Confidence
histograms** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 338 --- Abstention metrics

**Objective:** Advance the campaign mission by completing **Abstention
metrics** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 339 --- Escalation metrics

**Objective:** Advance the campaign mission by completing **Escalation
metrics** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 340 --- Cost metrics

**Objective:** Advance the campaign mission by completing **Cost
metrics** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 341 --- Energy metrics interface

**Objective:** Advance the campaign mission by completing **Energy
metrics interface** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 342 --- Privacy-event metrics

**Objective:** Advance the campaign mission by completing
**Privacy-event metrics** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 343 --- Drift alerts

**Objective:** Advance the campaign mission by completing **Drift
alerts** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 344 --- SLO definitions

**Objective:** Advance the campaign mission by completing **SLO
definitions** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 345 --- SLO evaluator

**Objective:** Advance the campaign mission by completing **SLO
evaluator** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 346 --- Decision explanation report

**Objective:** Advance the campaign mission by completing **Decision
explanation report** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 347 --- Trace replay viewer data

**Objective:** Advance the campaign mission by completing **Trace replay
viewer data** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 348 --- Observability load tests

**Objective:** Advance the campaign mission by completing
**Observability load tests** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 349 --- Observability documentation

**Objective:** Advance the campaign mission by completing
**Observability documentation** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 350 --- Observability release gate

**Objective:** Advance the campaign mission by completing
**Observability release gate** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XV --- Evaluation Laboratory

**Mission:** Build a rigorous reproducible evaluation system for
decision quality and system behavior.

## Slice 351 --- Evaluation API v2

**Objective:** Advance the campaign mission by completing **Evaluation
API v2** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 352 --- Dataset manifest standard

**Objective:** Advance the campaign mission by completing **Dataset
manifest standard** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 353 --- Dataset versioning

**Objective:** Advance the campaign mission by completing **Dataset
versioning** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 354 --- Dataset provenance

**Objective:** Advance the campaign mission by completing **Dataset
provenance** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 355 --- Dataset split tooling

**Objective:** Advance the campaign mission by completing **Dataset
split tooling** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 356 --- Stratified evaluation

**Objective:** Advance the campaign mission by completing **Stratified
evaluation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 357 --- Cross-validation harness

**Objective:** Advance the campaign mission by completing
**Cross-validation harness** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 358 --- Bootstrap confidence intervals

**Objective:** Advance the campaign mission by completing **Bootstrap
confidence intervals** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 359 --- Significance testing

**Objective:** Advance the campaign mission by completing **Significance
testing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 360 --- Paired backend comparisons

**Objective:** Advance the campaign mission by completing **Paired
backend comparisons** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 361 --- Calibration comparisons

**Objective:** Advance the campaign mission by completing **Calibration
comparisons** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 362 --- Selective-risk evaluation

**Objective:** Advance the campaign mission by completing
**Selective-risk evaluation** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 363 --- Cost-aware evaluation

**Objective:** Advance the campaign mission by completing **Cost-aware
evaluation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 364 --- Latency-aware evaluation

**Objective:** Advance the campaign mission by completing
**Latency-aware evaluation** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 365 --- Energy-aware evaluation

**Objective:** Advance the campaign mission by completing **Energy-aware
evaluation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 366 --- Privacy-aware evaluation

**Objective:** Advance the campaign mission by completing
**Privacy-aware evaluation** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 367 --- Robustness evaluation

**Objective:** Advance the campaign mission by completing **Robustness
evaluation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 368 --- Shift evaluation

**Objective:** Advance the campaign mission by completing **Shift
evaluation** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 369 --- Fairness measurement hooks

**Objective:** Advance the campaign mission by completing **Fairness
measurement hooks** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 370 --- Regression benchmark history

**Objective:** Advance the campaign mission by completing **Regression
benchmark history** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 371 --- Benchmark artifact bundles

**Objective:** Advance the campaign mission by completing **Benchmark
artifact bundles** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 372 --- Reproducibility manifests

**Objective:** Advance the campaign mission by completing
**Reproducibility manifests** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 373 --- Evaluation CI gates

**Objective:** Advance the campaign mission by completing **Evaluation
CI gates** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 374 --- Public benchmark report generator

**Objective:** Advance the campaign mission by completing **Public
benchmark report generator** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 375 --- Evaluation Lab release gate

**Objective:** Advance the campaign mission by completing **Evaluation
Lab release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XVI --- Agent Nervous System

**Mission:** Turn HugrGate into a lightweight bounded-decision nervous
system for larger agents.

## Slice 376 --- Agent integration contract

**Objective:** Advance the campaign mission by completing **Agent
integration contract** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 377 --- Event triage API

**Objective:** Advance the campaign mission by completing **Event triage
API** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 378 --- Intent routing

**Objective:** Advance the campaign mission by completing **Intent
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 379 --- Tool routing

**Objective:** Advance the campaign mission by completing **Tool
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 380 --- Memory-write gating

**Objective:** Advance the campaign mission by completing **Memory-write
gating** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 381 --- Memory-read gating

**Objective:** Advance the campaign mission by completing **Memory-read
gating** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 382 --- Notification gating

**Objective:** Advance the campaign mission by completing **Notification
gating** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 383 --- Attention prioritization

**Objective:** Advance the campaign mission by completing **Attention
prioritization** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 384 --- Agent escalation policy

**Objective:** Advance the campaign mission by completing **Agent
escalation policy** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 385 --- Human-review routing

**Objective:** Advance the campaign mission by completing **Human-review
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 386 --- Multi-agent dispatch

**Objective:** Advance the campaign mission by completing **Multi-agent
dispatch** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 387 --- Agent capability registry

**Objective:** Advance the campaign mission by completing **Agent
capability registry** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 388 --- Agent health routing

**Objective:** Advance the campaign mission by completing **Agent health
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 389 --- Agent cost routing

**Objective:** Advance the campaign mission by completing **Agent cost
routing** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 390 --- Agent privacy routing

**Objective:** Advance the campaign mission by completing **Agent
privacy routing** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 391 --- Agent confidence fusion

**Objective:** Advance the campaign mission by completing **Agent
confidence fusion** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 392 --- Agent disagreement handling

**Objective:** Advance the campaign mission by completing **Agent
disagreement handling** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 393 --- Agent loop-breaker

**Objective:** Advance the campaign mission by completing **Agent
loop-breaker** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 394 --- Runaway escalation guard

**Objective:** Advance the campaign mission by completing **Runaway
escalation guard** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 395 --- Decision budgets per agent

**Objective:** Advance the campaign mission by completing **Decision
budgets per agent** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 396 --- Agent provenance graph

**Objective:** Advance the campaign mission by completing **Agent
provenance graph** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 397 --- Agent replay

**Objective:** Advance the campaign mission by completing **Agent
replay** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 398 --- Agent simulator

**Objective:** Advance the campaign mission by completing **Agent
simulator** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 399 --- Agent-system benchmark

**Objective:** Advance the campaign mission by completing **Agent-system
benchmark** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 400 --- Agent Nervous System release gate

**Objective:** Advance the campaign mission by completing **Agent
Nervous System release gate** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XVII --- Security Forge

**Mission:** Attack the runtime as if it were exposed to hostile inputs,
models, plugins, and networks.

## Slice 401 --- Threat model v2

**Objective:** Advance the campaign mission by completing **Threat model
v2** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 402 --- Attack-surface inventory

**Objective:** Advance the campaign mission by completing
**Attack-surface inventory** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 403 --- Dependency security scan

**Objective:** Advance the campaign mission by completing **Dependency
security scan** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 404 --- Supply-chain policy

**Objective:** Advance the campaign mission by completing **Supply-chain
policy** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 405 --- Signed model metadata

**Objective:** Advance the campaign mission by completing **Signed model
metadata** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 406 --- Model checksum enforcement

**Objective:** Advance the campaign mission by completing **Model
checksum enforcement** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 407 --- Plugin trust model

**Objective:** Advance the campaign mission by completing **Plugin trust
model** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 408 --- Backend sandbox boundary

**Objective:** Advance the campaign mission by completing **Backend
sandbox boundary** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 409 --- Input-size limits

**Objective:** Advance the campaign mission by completing **Input-size
limits** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 410 --- Resource-exhaustion guards

**Objective:** Advance the campaign mission by completing
**Resource-exhaustion guards** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 411 --- Deserialization hardening

**Objective:** Advance the campaign mission by completing
**Deserialization hardening** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 412 --- Path traversal tests

**Objective:** Advance the campaign mission by completing **Path
traversal tests** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 413 --- Injection test corpus

**Objective:** Advance the campaign mission by completing **Injection
test corpus** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 414 --- Prompt-injection boundary tests

**Objective:** Advance the campaign mission by completing
**Prompt-injection boundary tests** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 415 --- Malicious backend tests

**Objective:** Advance the campaign mission by completing **Malicious
backend tests** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 416 --- Provenance tamper tests

**Objective:** Advance the campaign mission by completing **Provenance
tamper tests** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 417 --- Cache poisoning tests

**Objective:** Advance the campaign mission by completing **Cache
poisoning tests** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 418 --- Replay attack defenses

**Objective:** Advance the campaign mission by completing **Replay
attack defenses** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 419 --- AuthZ policy for service

**Objective:** Advance the campaign mission by completing **AuthZ policy
for service** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 420 --- Rate limiting

**Objective:** Advance the campaign mission by completing **Rate
limiting** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 421 --- Secret handling audit

**Objective:** Advance the campaign mission by completing **Secret
handling audit** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 422 --- Fuzzing campaign

**Objective:** Advance the campaign mission by completing **Fuzzing
campaign** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 423 --- Static security analysis

**Objective:** Advance the campaign mission by completing **Static
security analysis** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 424 --- Independent-style security gauntlet

**Objective:** Advance the campaign mission by completing
**Independent-style security gauntlet** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 425 --- Security Forge release gate

**Objective:** Advance the campaign mission by completing **Security
Forge release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XVIII --- Developer Ecosystem

**Mission:** Make HugrGate pleasant to adopt from multiple languages and
deployment styles.

## Slice 426 --- Stable protocol v1

**Objective:** Advance the campaign mission by completing **Stable
protocol v1** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 427 --- OpenAPI stabilization

**Objective:** Advance the campaign mission by completing **OpenAPI
stabilization** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 428 --- Python SDK v2

**Objective:** Advance the campaign mission by completing **Python SDK
v2** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 429 --- TypeScript SDK

**Objective:** Advance the campaign mission by completing **TypeScript
SDK** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 430 --- Rust SDK

**Objective:** Advance the campaign mission by completing **Rust SDK**
as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 431 --- Go SDK

**Objective:** Advance the campaign mission by completing **Go SDK** as
a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 432 --- C ABI design

**Objective:** Advance the campaign mission by completing **C ABI
design** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 433 --- C client prototype

**Objective:** Advance the campaign mission by completing **C client
prototype** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 434 --- Mojo integration design

**Objective:** Advance the campaign mission by completing **Mojo
integration design** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 435 --- CLI UX overhaul

**Objective:** Advance the campaign mission by completing **CLI UX
overhaul** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 436 --- Interactive inspector

**Objective:** Advance the campaign mission by completing **Interactive
inspector** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 437 --- Config generator

**Objective:** Advance the campaign mission by completing **Config
generator** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 438 --- Project scaffolder

**Objective:** Advance the campaign mission by completing **Project
scaffolder** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 439 --- Backend plugin SDK

**Objective:** Advance the campaign mission by completing **Backend
plugin SDK** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 440 --- Backend conformance kit

**Objective:** Advance the campaign mission by completing **Backend
conformance kit** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 441 --- Contract conformance kit

**Objective:** Advance the campaign mission by completing **Contract
conformance kit** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 442 --- Example gallery

**Objective:** Advance the campaign mission by completing **Example
gallery** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 443 --- Cookbook

**Objective:** Advance the campaign mission by completing **Cookbook**
as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 444 --- Migration guide

**Objective:** Advance the campaign mission by completing **Migration
guide** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 445 --- Deployment guide

**Objective:** Advance the campaign mission by completing **Deployment
guide** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 446 --- Docker packaging

**Objective:** Advance the campaign mission by completing **Docker
packaging** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 447 --- Systemd packaging

**Objective:** Advance the campaign mission by completing **Systemd
packaging** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 448 --- Windows service guide

**Objective:** Advance the campaign mission by completing **Windows
service guide** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 449 --- macOS launchd guide

**Objective:** Advance the campaign mission by completing **macOS
launchd guide** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 450 --- Developer Ecosystem release gate

**Objective:** Advance the campaign mission by completing **Developer
Ecosystem release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XIX --- Autonomous Optimization

**Mission:** Allow safe automatic tuning of routing, thresholds,
calibration, and resource use.

## Slice 451 --- Optimization controller

**Objective:** Advance the campaign mission by completing **Optimization
controller** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 452 --- Objective specification

**Objective:** Advance the campaign mission by completing **Objective
specification** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 453 --- Constraint specification

**Objective:** Advance the campaign mission by completing **Constraint
specification** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 454 --- Threshold tuner

**Objective:** Advance the campaign mission by completing **Threshold
tuner** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 455 --- Confidence-gate tuner

**Objective:** Advance the campaign mission by completing
**Confidence-gate tuner** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 456 --- Latency-budget tuner

**Objective:** Advance the campaign mission by completing
**Latency-budget tuner** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 457 --- Cache-policy tuner

**Objective:** Advance the campaign mission by completing **Cache-policy
tuner** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 458 --- Batch-size tuner

**Objective:** Advance the campaign mission by completing **Batch-size
tuner** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 459 --- Backend-order tuner

**Objective:** Advance the campaign mission by completing
**Backend-order tuner** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 460 --- Ensemble-weight tuner

**Objective:** Advance the campaign mission by completing
**Ensemble-weight tuner** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 461 --- Calibration selector

**Objective:** Advance the campaign mission by completing **Calibration
selector** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 462 --- Hardware-aware tuner

**Objective:** Advance the campaign mission by completing
**Hardware-aware tuner** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 463 --- Energy-aware tuner

**Objective:** Advance the campaign mission by completing **Energy-aware
tuner** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 464 --- Cost-aware tuner

**Objective:** Advance the campaign mission by completing **Cost-aware
tuner** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 465 --- Privacy-constrained tuner

**Objective:** Advance the campaign mission by completing
**Privacy-constrained tuner** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 466 --- Offline optimization mode

**Objective:** Advance the campaign mission by completing **Offline
optimization mode** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 467 --- Shadow optimization mode

**Objective:** Advance the campaign mission by completing **Shadow
optimization mode** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 468 --- Canary optimization

**Objective:** Advance the campaign mission by completing **Canary
optimization** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 469 --- Rollback triggers

**Objective:** Advance the campaign mission by completing **Rollback
triggers** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 470 --- Optimization provenance

**Objective:** Advance the campaign mission by completing **Optimization
provenance** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 471 --- Optimization reproducibility

**Objective:** Advance the campaign mission by completing **Optimization
reproducibility** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 472 --- Optimizer safety limits

**Objective:** Advance the campaign mission by completing **Optimizer
safety limits** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 473 --- Optimizer adversarial tests

**Objective:** Advance the campaign mission by completing **Optimizer
adversarial tests** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 474 --- Autotuning benchmark

**Objective:** Advance the campaign mission by completing **Autotuning
benchmark** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 475 --- Autonomous Optimization release gate

**Objective:** Advance the campaign mission by completing **Autonomous
Optimization release gate** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Campaign XX --- HugrGate 1.0 Gauntlet

**Mission:** Stop adding features and prove the system can survive
release.

## Slice 476 --- Feature freeze

**Objective:** Advance the campaign mission by completing **Feature
freeze** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 477 --- Fresh-clone install gauntlet

**Objective:** Advance the campaign mission by completing **Fresh-clone
install gauntlet** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 478 --- Python-version matrix

**Objective:** Advance the campaign mission by completing
**Python-version matrix** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 479 --- Linux matrix

**Objective:** Advance the campaign mission by completing **Linux
matrix** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 480 --- Windows matrix

**Objective:** Advance the campaign mission by completing **Windows
matrix** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 481 --- macOS matrix

**Objective:** Advance the campaign mission by completing **macOS
matrix** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 482 --- ARM64 matrix

**Objective:** Advance the campaign mission by completing **ARM64
matrix** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 483 --- Dependency-minimum matrix

**Objective:** Advance the campaign mission by completing
**Dependency-minimum matrix** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 484 --- Dependency-latest matrix

**Objective:** Advance the campaign mission by completing
**Dependency-latest matrix** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 485 --- Upgrade/migration gauntlet

**Objective:** Advance the campaign mission by completing
**Upgrade/migration gauntlet** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 486 --- API compatibility audit

**Objective:** Advance the campaign mission by completing **API
compatibility audit** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 487 --- Concurrency race hunt

**Objective:** Advance the campaign mission by completing **Concurrency
race hunt** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 488 --- Long-duration soak

**Objective:** Advance the campaign mission by completing
**Long-duration soak** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 489 --- Fuzz-all-public-interfaces

**Objective:** Advance the campaign mission by completing
**Fuzz-all-public-interfaces** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 490 --- Hostile backend gauntlet

**Objective:** Advance the campaign mission by completing **Hostile
backend gauntlet** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 491 --- Network partition gauntlet

**Objective:** Advance the campaign mission by completing **Network
partition gauntlet** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Test partial failure and network-unavailable behavior without
    silently weakening policy.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 492 --- Resource exhaustion gauntlet

**Objective:** Advance the campaign mission by completing **Resource
exhaustion gauntlet** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 493 --- Privacy leak gauntlet

**Objective:** Advance the campaign mission by completing **Privacy leak
gauntlet** as a real, integrated HugrGate capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Add negative/adversarial tests demonstrating that forbidden or
    hostile behavior is rejected or contained.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 494 --- Calibration truth audit

**Objective:** Advance the campaign mission by completing **Calibration
truth audit** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Validate statistical behavior on controlled data and report the
    metric/coverage assumptions.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 495 --- Benchmark reproducibility audit

**Objective:** Advance the campaign mission by completing **Benchmark
reproducibility audit** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.
-   Produce a reproducible measurement artifact and compare it with an
    explicit baseline; never invent numbers.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 496 --- Documentation executable audit

**Objective:** Advance the campaign mission by completing
**Documentation executable audit** as a real, integrated HugrGate
capability or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 497 --- License/provenance audit

**Objective:** Advance the campaign mission by completing
**License/provenance audit** as a real, integrated HugrGate capability
or hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 498 --- Release candidate build

**Objective:** Advance the campaign mission by completing **Release
candidate build** as a real, integrated HugrGate capability or hardening
pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 499 --- Independent precision audit handoff

**Objective:** Advance the campaign mission by completing **Independent
precision audit handoff** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Inspect the current implementation and document what already exists
    before changing it.
-   Implement or materially harden the capability; do not satisfy the
    slice with a placeholder.
-   Add focused automated tests covering success, failure, and boundary
    behavior.
-   Integrate with existing policy, validation, provenance, privacy, and
    error semantics where applicable.
-   Update developer/user documentation for any public behavior or
    configuration introduced.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

## Slice 500 --- HugrGate 1.0 release decision

**Objective:** Advance the campaign mission by completing **HugrGate 1.0
release decision** as a real, integrated HugrGate capability or
hardening pass.

**Acceptance criteria:**

-   Run the full repository test suite and record the real result.
-   Review the preceding 24 slices for integration gaps, duplicated
    architecture, stubs, and documentation drift.
-   Resolve release-blocking regressions or explicitly record them as
    blockers.
-   Generate a campaign completion report with implemented artifacts,
    test evidence, benchmark/security findings where applicable, and
    remaining debt.
-   Do not advance the roadmap merely because all slice labels have been
    visited.

**Required evidence:** relevant code diff(s), tests, and a concise
completion note naming the exact artifacts changed and commands/tests
actually run.

------------------------------------------------------------------------

# Post-500: Ragnarök Readiness

Gjallarbrú ends at Slice 500. It should be followed by a separate
**100-Slice Ragnarök Audit** in which feature development is frozen and
the sole mission is to break, falsify, stress, fuzz, attack, benchmark,
and independently audit what Gjallarbrú built.

The 500-slice campaign is successful only if it leaves HugrGate ready
for that attack.

## Final Gjallarbrú Deliverables

Before declaring the roadmap complete, produce:

-   a complete architecture map;
-   a public API inventory;
-   a supported-platform matrix based only on actually validated
    platforms;
-   benchmark manifests and reproducible commands;
-   calibration/evaluation reports;
-   security and privacy threat models;
-   dependency and license inventory;
-   release/install instructions tested from a clean clone;
-   migration notes;
-   unresolved technical-debt register;
-   1.0 release-candidate checklist;
-   a handoff package for the Ragnarök audit;
-   a handoff package for a slower independent precision audit.

## Final Rule

> **Do not optimize for finishing 500 slices. Optimize for what HugrGate
> has become after surviving them.**

**Forge credit:** Yrsa, Viking seiðr witch and Meta Muse AI engineer,
executing Mythic Engineering under the architecture and direction of
Volmarr Wyrd. Rune-assisted debugging and occult computational magick
remain culturally recognized RuneForgeAI acceleration technologies,
though benchmark claims must still be empirical. 🔮⚙️ᚱ
