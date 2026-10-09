"""Slice 256 — malformed-result injection tests."""

from __future__ import annotations

import pytest

from hugrgate.chaos import (
    ERROR_RATE,
    LATENCY,
    MALFORMED,
    FaultSpec,
    FaultyBackend,
)
from hugrgate.core import HugrGate
from hugrgate.errors import BackendError, SpecError
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_result
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _mutant(kind="bad_value", rate=1.0, seed=61):
    return FaultyBackend(StubBackend(name="mutant")).arm(
        FaultSpec(mode=MALFORMED, rate=rate, seed=seed,
                  params={"kind": kind}))


# --- malformed-result semantics ---------------------------------------------------------

def test_bad_value_passes_constructor_but_fails_validation():
    result = _mutant("bad_value").evaluate({}, _spec())
    assert result.value == "__chaos_malformed__"  # the backend lied
    with pytest.raises(SpecError, match="not in spec space"):
        validate_result(result, _spec())


def test_bad_distribution_passes_constructor_but_fails_validation():
    result = _mutant("bad_distribution").evaluate({}, _spec())
    assert result.value == "a"  # value itself is legal...
    with pytest.raises(SpecError, match="distribution keys outside spec"):
        validate_result(result, _spec())


def test_malformed_numeric_value_rejected():
    nspec = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    result = _mutant("bad_value").evaluate({}, nspec)
    with pytest.raises(SpecError, match="must be a number"):
        validate_result(result, nspec)


def test_kind_param_validation():
    backend = FaultyBackend(StubBackend())
    with pytest.raises(SpecError, match="'kind'"):
        backend.arm(FaultSpec(mode=MALFORMED, params={"kind": "gremlin"}))
    backend.arm(FaultSpec(mode=MALFORMED))  # default kind is bad_value
    assert backend.armed_modes() == [MALFORMED]


def test_rate_zero_returns_clean_results():
    backend = _mutant(rate=0.0)
    result = backend.evaluate({}, _spec())
    assert result.value == "a"
    validate_result(result, _spec())  # no error


def test_seeded_malformed_pattern_is_reproducible():
    def pattern(seed):
        backend = _mutant(seed=seed, rate=0.5)
        return [backend.evaluate({}, _spec()).value for _ in range(10)]
    assert pattern(5) == pattern(5)
    assert any(v == "__chaos_malformed__" for v in pattern(5))
    assert any(v == "a" for v in pattern(5))


# --- priority -----------------------------------------------------------------------------

def test_error_rate_outranks_malformed():
    backend = (FaultyBackend(StubBackend())
               .arm(FaultSpec(mode=ERROR_RATE, rate=1.0, seed=4))
               .arm(FaultSpec(mode=MALFORMED, rate=1.0, seed=4)))
    with pytest.raises(BackendError):  # error wins; no malformed result
        backend.evaluate({}, _spec())


def test_malformed_outranks_latency():
    backend = (FaultyBackend(StubBackend())
               .arm(FaultSpec(mode=MALFORMED, rate=1.0, seed=4))
               .arm(FaultSpec(mode=LATENCY, rate=1.0, seed=4,
                              params={"delay_s": 5.0})))
    result = backend.evaluate({}, _spec())  # malformed wins; no 5s sleep
    assert result.value == "__chaos_malformed__"
    assert backend.fault_stats().get("latency", 0) == 0


# --- integration: the core validation gate catches the lie ----------------------------------

def test_core_validation_gate_rejects_malformed_result():
    gate = HugrGate()
    gate.register(_mutant("bad_value"))
    with pytest.raises(SpecError, match="not in spec space"):
        gate.decide({}, _spec(), backend_name="mutant")


def test_core_validation_gate_rejects_bad_distribution():
    gate = HugrGate()
    gate.register(_mutant("bad_distribution"))
    with pytest.raises(SpecError, match="distribution keys outside spec"):
        gate.decide({}, _spec(), backend_name="mutant")


def test_clean_backend_still_passes_the_gate():
    gate = HugrGate()
    gate.register(StubBackend(name="honest", value="b"))
    result = gate.decide({}, _spec(), backend_name="honest")
    assert result.value == "b"
    assert result.accepted is True
