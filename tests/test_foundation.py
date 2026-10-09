"""Tests for Batch A (Slices 1-10): foundation contracts."""

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendRegistry,
    BackendUnavailable,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
    HugrGate,
    SpecError,
)
from hugrgate.provenance import ProvenanceStore
from hugrgate.validation import validate_result, validate_state


class StubBackend(Backend):
    name = "stub"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        dist = {o: (0.9 if o == spec.options[0] else 0.1 / (len(spec.options) - 1))
                for o in spec.options}
        return DecisionResult(value=spec.options[0], probability=0.9,
                              distribution=dist, backend=self.name)


# --- Spec ---

def test_categorical_valid():
    s = DecisionSpec(type="categorical", options=["a", "b", "c"])
    assert s.value_space() == ["a", "b", "c"]

def test_categorical_rejects_duplicates():
    with pytest.raises(SpecError):
        DecisionSpec(type="categorical", options=["a", "a"])

def test_categorical_rejects_single():
    with pytest.raises(SpecError):
        DecisionSpec(type="categorical", options=["a"])

def test_binary_valid():
    s = DecisionSpec(type="binary", statement="Is it urgent?")
    assert s.value_space() == ["true", "false"]

def test_ordinal_valid():
    s = DecisionSpec(type="ordinal", levels=["low", "high"])
    assert s.value_space() == ["low", "high"]

def test_numeric_valid():
    DecisionSpec(type="numeric", minimum=0.0, maximum=100.0)

def test_numeric_rejects_inverted():
    with pytest.raises(SpecError):
        DecisionSpec(type="numeric", minimum=100.0, maximum=0.0)

def test_multilabel_valid():
    DecisionSpec(type="multilabel", labels=["a", "b"])

def test_spec_roundtrip():
    s = DecisionSpec(type="categorical", options=["x", "y"])
    assert DecisionSpec.from_dict(s.to_dict()).options == ["x", "y"]

def test_unknown_type():
    with pytest.raises(SpecError):
        DecisionSpec(type="quantum")

# --- Result ---

def test_result_valid():
    r = DecisionResult(value="a", probability=0.9,
                       distribution={"a": 0.9, "b": 0.1})
    assert r.probability == 0.9

def test_result_rejects_bad_probability():
    with pytest.raises(SpecError):
        DecisionResult(value="a", probability=1.5)

def test_result_rejects_bad_distribution():
    with pytest.raises(SpecError):
        DecisionResult(value="a", probability=0.9,
                       distribution={"a": 0.5, "b": 0.1})

# --- Policy ---

def test_policy_accept():
    p = DecisionPolicy(minimum_probability=0.8)
    r = DecisionResult(value="a", probability=0.9)
    assert p.evaluate(r) == "accept"

def test_policy_abstain():
    p = DecisionPolicy(minimum_probability=0.95)
    r = DecisionResult(value="a", probability=0.9)
    assert p.evaluate(r) == "abstain"

def test_policy_review_band():
    p = DecisionPolicy(minimum_probability=0.5, review_band=(0.7, 0.95))
    r = DecisionResult(value="a", probability=0.8)
    assert p.evaluate(r) == "review"

def test_policy_blocks_remote():
    p = DecisionPolicy(remote_inference=False)
    assert not p.backend_allowed("cloud", is_remote=True)
    assert p.backend_allowed("local", is_remote=False)

# --- Backend registry ---

def test_registry():
    reg = BackendRegistry()
    reg.register(StubBackend())
    assert "stub" in reg.list()
    s = DecisionSpec(type="categorical", options=["a", "b"])
    assert len(reg.supporting(s)) == 1

# --- Validation ---

def test_validate_state_rejects_non_mapping():
    with pytest.raises(SpecError):
        validate_state("not a dict")

def test_validate_result_rejects_out_of_space():
    s = DecisionSpec(type="categorical", options=["a", "b"])
    r = DecisionResult(value="z", probability=0.9)
    with pytest.raises(SpecError):
        validate_result(r, s)

def test_validate_result_accepts_abstention():
    s = DecisionSpec(type="categorical", options=["a", "b"])
    r = DecisionResult(value=None, probability=0.0)
    validate_result(r, s)  # no raise

# --- Core ---

def test_decide_end_to_end():
    gate = HugrGate()
    gate.register(StubBackend())
    s = DecisionSpec(type="categorical", options=["ignore", "escalate"])
    r = gate.decide({"event": "test"}, s)
    assert r.value == "ignore"
    assert r.accepted

def test_decide_abstains_below_threshold():
    gate = HugrGate()
    gate.register(StubBackend())
    s = DecisionSpec(type="categorical", options=["ignore", "escalate"])
    p = DecisionPolicy(minimum_probability=0.99)
    with pytest.raises(Abstention):
        gate.decide({"event": "test"}, s, p)

def test_decide_no_backend():
    gate = HugrGate()
    s = DecisionSpec(type="categorical", options=["a", "b"])
    with pytest.raises(BackendUnavailable):
        gate.decide({}, s)

def test_provenance_recorded():
    gate = HugrGate()
    gate.register(StubBackend())
    s = DecisionSpec(type="categorical", options=["a", "b"])
    gate.decide({"x": 1}, s)
    assert gate.provenance.count() == 1

def test_provenance_store():
    store = ProvenanceStore()
    assert store.count() == 0
    assert store.by_hash("nope") is None
