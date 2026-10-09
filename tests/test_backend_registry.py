"""Slice 014 — backend registry hardening.

The registry is the trust boundary between configuration and
execution: it must refuse non-backends, nameless backends, and silent
overwrites.
"""

from __future__ import annotations

import pytest

from hugrgate.backend import Backend, BackendRegistry
from hugrgate.errors import BackendUnavailable, SpecError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


class StubBackend(Backend):
    def __init__(self, name="stub"):
        self.name = name

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0})


def test_register_and_get():
    reg = BackendRegistry()
    b = StubBackend("one")
    reg.register(b)
    assert reg.get("one") is b
    assert "one" in reg and len(reg) == 1
    assert reg.list() == ["one"]


def test_register_rejects_non_backend():
    reg = BackendRegistry()
    with pytest.raises(TypeError):
        reg.register(object())
    with pytest.raises(TypeError):
        reg.register("stub")
    assert len(reg) == 0


def test_register_rejects_blank_name():
    reg = BackendRegistry()
    with pytest.raises(SpecError, match="non-empty string"):
        reg.register(StubBackend(""))
    with pytest.raises(SpecError, match="non-empty string"):
        reg.register(StubBackend("   "))


def test_duplicate_registration_rejected():
    reg = BackendRegistry()
    reg.register(StubBackend("dup"))
    with pytest.raises(SpecError, match="already registered"):
        reg.register(StubBackend("dup"))
    assert len(reg) == 1  # original kept


def test_replace_true_overwrites():
    reg = BackendRegistry()
    old, new = StubBackend("x"), StubBackend("x")
    reg.register(old)
    reg.register(new, replace=True)
    assert reg.get("x") is new


def test_get_or_raise():
    reg = BackendRegistry()
    b = StubBackend("real")
    reg.register(b)
    assert reg.get_or_raise("real") is b
    with pytest.raises(BackendUnavailable, match="unknown backend"):
        reg.get_or_raise("ghost")


def test_unregister():
    reg = BackendRegistry()
    reg.register(StubBackend("temp"))
    assert reg.unregister("temp") is True
    assert reg.unregister("temp") is False
    assert "temp" not in reg


def test_supporting_filters_by_spec():
    reg = BackendRegistry()
    reg.register(StubBackend("cat"))
    cat = DecisionSpec(type="categorical", options=["a", "b"])
    num = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    assert [b.name for b in reg.supporting(cat)] == ["cat"]
    assert reg.supporting(num) == []


def test_gate_register_passes_replace_through():
    from hugrgate import HugrGate
    gate = HugrGate()
    gate.register(StubBackend("g"))
    with pytest.raises(SpecError, match="already registered"):
        gate.register(StubBackend("g"))
    gate.register(StubBackend("g"), replace=True)
    assert gate.registry.get("g") is not None
