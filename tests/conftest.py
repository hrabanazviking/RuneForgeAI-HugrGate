"""Shared fixtures for the HugrGate test suite (slice 023).

Taxonomy (see docs/campaign-i/023-test-taxonomy-rebuild.md):
- unit (default): fast, single-component, no I/O — no marker needed.
- integration: exercises several components together — ``pytestmark =
  pytest.mark.integration``.
- slow: spawns servers/threads or sleeps — ``pytest.mark.slow``.
- gate: meta-tests that shell out to tools (mypy, ruff, generators)
  — ``pytest.mark.gate``.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.result import DecisionResult


@pytest.fixture
def cat_spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["a", "b", "c"])


@pytest.fixture
def binary_spec() -> DecisionSpec:
    return DecisionSpec(type="binary", statement="escalate?")


@pytest.fixture
def policy() -> DecisionPolicy:
    return DecisionPolicy(minimum_probability=0.0)


@pytest.fixture
def strict_policy() -> DecisionPolicy:
    return DecisionPolicy(minimum_probability=0.9, privacy_class="strict")


class StubBackend(Backend):
    """Minimal deterministic backend for tests."""

    def __init__(self, name: str = "stub", value: str = "a",
                 probability: float = 1.0, delay: float = 0.0):
        self.name = name
        self.value = value
        self.probability = probability
        self.delay = delay

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        if self.delay:
            import time
            time.sleep(self.delay)
        options = spec.options or ["a"]
        value = self.value if self.value in options else options[0]
        rest = (1.0 - self.probability) / max(len(options) - 1, 1)
        dist = {o: (self.probability if o == value else rest)
                for o in options}
        return DecisionResult(value=value,
                              probability=self.probability,
                              distribution=dist)


@pytest.fixture
def stub_backend() -> StubBackend:
    return StubBackend()


@pytest.fixture
def gate_with_stub(stub_backend: StubBackend) -> HugrGate:
    gate = HugrGate()
    gate.register(stub_backend)
    return gate
