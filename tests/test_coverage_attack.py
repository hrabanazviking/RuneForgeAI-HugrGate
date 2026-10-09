"""Slice 024 — coverage gap attack.

Targets genuinely untested branches found by the coverage audit:
``validate_result``'s numeric/multilabel/distribution-key paths,
spec validation branches, ``TimeoutBackend``'s delegate surface,
``ModelManifest``/``ModelStore`` failure paths, and the core
``decide``/``close`` branches.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.errors import BackendUnavailable, HugrGateError, SpecError
from hugrgate.models import ModelManifest, ModelStore
from hugrgate.result import DecisionResult
from hugrgate.timeout import TimeoutBackend
from hugrgate.validation import validate_result


class StubBackend(Backend):
    def __init__(self, name="stub", value="a", prob=1.0, remote=False):
        self.name = name
        self._value = value
        self._prob = prob
        self.is_remote = remote

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        options = spec.options or ["a", "b"]
        rest = (1.0 - self._prob) / max(len(options) - 1, 1)
        value = self._value if self._value in options else options[0]
        dist = {o: (self._prob if o == value else rest) for o in options}
        return DecisionResult(value=value, probability=self._prob,
                              distribution=dist)


CAT = DecisionSpec(type="categorical", options=["a", "b"])
NUM = DecisionSpec(type="numeric", minimum=0.0, maximum=10.0)
ML = DecisionSpec(type="multilabel", labels=["x", "y"])


def _res(value, prob=0.8, dist=None):
    return DecisionResult(
        value=value, probability=prob,
        distribution=dist if dist is not None else {"a": prob, "b": 1 - prob})


# --- validate_result ---------------------------------------------------------

def test_validate_result_numeric_ok():
    r = DecisionResult(value=5.0, probability=0.9)
    validate_result(r, NUM)


def test_validate_result_numeric_out_of_range():
    with pytest.raises(SpecError, match="outside"):
        validate_result(DecisionResult(value=50.0, probability=0.9), NUM)


def test_validate_result_numeric_rejects_non_number():
    with pytest.raises(SpecError, match="must be a number"):
        validate_result(DecisionResult(value="high", probability=0.9), NUM)


def test_validate_result_multilabel_ok():
    r = DecisionResult(value=["x"], probability=0.8,
                       distribution={"x": 0.8, "y": 0.2})
    validate_result(r, ML)


def test_validate_result_multilabel_rejects_non_list():
    with pytest.raises(SpecError, match="must be a list"):
        validate_result(_res("x"), ML)


def test_validate_result_multilabel_rejects_bad_label():
    r = DecisionResult(value=["zzz"], probability=0.8,
                       distribution={"zzz": 0.8, "y": 0.2})
    with pytest.raises(SpecError, match="outside spec"):
        validate_result(r, ML)


def test_validate_result_rejects_distribution_keys_outside_space():
    r = DecisionResult(value="a", probability=0.8,
                       distribution={"a": 0.8, "zzz": 0.2})
    with pytest.raises(SpecError, match="distribution keys outside spec"):
        validate_result(r, CAT)


def test_validate_result_abstention_always_legal():
    validate_result(DecisionResult(value=None, probability=0.0), CAT)


# --- spec validation branches -------------------------------------------------

def test_categorical_rejects_duplicate_options():
    with pytest.raises(SpecError, match="unique"):
        DecisionSpec(type="categorical", options=["a", "a"])


def test_categorical_rejects_non_string_options():
    with pytest.raises(SpecError, match="non-empty strings"):
        DecisionSpec(type="categorical", options=["a", ""])


def test_ordinal_rejects_duplicate_levels():
    with pytest.raises(SpecError, match="unique"):
        DecisionSpec(type="ordinal", levels=["low", "low"])


def test_numeric_rejects_inverted_bounds():
    with pytest.raises(SpecError, match="must be < maximum"):
        DecisionSpec(type="numeric", minimum=5.0, maximum=5.0)


def test_multilabel_rejects_duplicate_labels():
    with pytest.raises(SpecError, match="unique"):
        DecisionSpec(type="multilabel", labels=["x", "x"])


# --- TimeoutBackend delegate surface -------------------------------------------

def _timeout_backend(**kw):
    return TimeoutBackend(StubBackend(), **kw)


def test_timeout_deadline_explicit():
    tb = _timeout_backend(explicit_deadline_ms=250.0)
    assert tb.deadline_ms == 250.0
    assert tb.estimated_latency() == 250.0


def test_timeout_capabilities_and_health():
    tb = _timeout_backend(explicit_deadline_ms=250.0)
    caps = tb.capabilities()
    assert caps["timeout_guarded"] is True
    assert caps["deadline_ms"] == 250.0
    assert tb.health()["timeout_guarded"] is True
    assert tb.supports(CAT) is True
    assert tb.supports(NUM) is False


# --- models --------------------------------------------------------------------

def test_manifest_rejects_blank_name_and_version():
    with pytest.raises(HugrGateError, match="needs a name"):
        ModelManifest(name="", version="1", backend="logreg", spec_type="categorical", features=["f"], classes=["a", "b"])
    with pytest.raises(HugrGateError, match="needs a version"):
        ModelManifest(name="m", version="", backend="logreg", spec_type="categorical", features=["f"], classes=["a", "b"])


def test_manifest_rejects_duplicate_classes():
    with pytest.raises(HugrGateError, match="unique"):
        ModelManifest(name="m", version="1", backend="logreg",
                      spec_type="categorical", features=["f"],
                      classes=["a", "a"])


def test_manifest_verify_without_hash():
    m = ModelManifest(name="m", version="1", backend="logreg", spec_type="categorical", features=["f"], classes=["a", "b"])
    with pytest.raises(HugrGateError, match="no payload hash"):
        m.verify(b"data")


def test_store_rejects_duplicate_version(tmp_path):
    store = ModelStore(root=tmp_path)
    m = ModelManifest(name="m", version="1", backend="logreg", spec_type="categorical", features=["f"], classes=["a", "b"])
    store.put(m, b"payload")
    with pytest.raises(HugrGateError, match="already stored"):
        store.put(ModelManifest(name="m", version="1", backend="logreg", spec_type="categorical", features=["f"], classes=["a", "b"]), b"payload")


def test_store_load_and_delete_missing(tmp_path):
    store = ModelStore(root=tmp_path)
    with pytest.raises(HugrGateError, match="no stored model"):
        store.get("ghost", "1")
    with pytest.raises(HugrGateError, match="no stored model"):
        store.delete("ghost", "1")


# --- core decide/close branches -------------------------------------------------

def test_decide_unknown_backend_name():
    gate = HugrGate()
    gate.register(StubBackend())
    with pytest.raises(BackendUnavailable, match="unknown backend"):
        gate.decide({"x": 1}, CAT, backend_name="ghost")


def test_decide_backend_blocked_by_policy():
    gate = HugrGate()
    gate.register(StubBackend("far", remote=True))
    policy = DecisionPolicy(remote_inference=False)
    with pytest.raises(BackendUnavailable, match="blocked by policy"):
        gate.decide({"x": 1}, CAT, policy, backend_name="far")


def test_decide_no_supporting_backend():
    gate = HugrGate()
    with pytest.raises(BackendUnavailable, match="no backend supports"):
        gate.decide({"x": 1}, CAT)


def test_select_backend_prefers_preferred():
    gate = HugrGate()
    gate.register(StubBackend("first", value="a"))
    gate.register(StubBackend("second", value="b"))
    policy = DecisionPolicy(preferred_backends=["second"])
    r = gate.decide({"x": 1}, CAT, policy)
    assert r.backend == "second" and r.value == "b"


def test_gate_exit_closes_backends():
    closed = []

    class Closing(StubBackend):
        def close(self):
            closed.append(self.name)

    gate = HugrGate()
    gate.register(Closing("c1"))
    with gate:
        pass
    assert closed == ["c1"]
