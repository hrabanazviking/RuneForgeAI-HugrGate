"""Tests for slice 203 — node capability advertisement."""

from __future__ import annotations

import pytest

from hugrgate.backend import BackendRegistry
from hugrgate.cluster.capabilities import NodeCapabilities
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.protocol import PROTOCOL_VERSION
from hugrgate.errors import SpecError
from hugrgate.server import build_gate
from hugrgate.spec import DecisionSpec


def _ident(name="n1"):
    return NodeIdentity.generate(name)


def _caps(name="n1"):
    return NodeCapabilities.from_gate(build_gate(), _ident(name))


# --- success ---------------------------------------------------------------

def test_from_gate_advertises_builtin_backends():
    caps = _caps()
    assert set(caps.backend_names()) >= {"uniform", "keyword"}
    assert "categorical" in caps.spec_types()
    assert "numeric" in caps.spec_types()  # uniform covers numeric


def test_advertisement_carries_serving_facts():
    caps = _caps()
    uniform = next(b for b in caps.backends if b["name"] == "uniform")
    assert isinstance(uniform["estimated_latency_ms"], float)
    assert isinstance(uniform["estimated_cost"], float)
    assert uniform["is_remote"] is False
    assert caps.protocol_version == PROTOCOL_VERSION
    assert caps.hardware["cpu_count"] >= 1


def test_matches_spec_type():
    caps = _caps()
    assert caps.matches(DecisionSpec(type="categorical",
                                     options=["a", "b"]))
    assert caps.matches(DecisionSpec(type="numeric", minimum=0.0,
                                     maximum=1.0))
    empty = NodeCapabilities.from_registry(BackendRegistry(), _ident())
    assert not empty.matches(DecisionSpec(type="categorical",
                                          options=["a", "b"]))


def test_supports_backend():
    caps = _caps()
    assert caps.supports_backend("keyword")
    assert not caps.supports_backend("nope")


def test_round_trip():
    caps = _caps("skald")
    back = NodeCapabilities.from_dict(caps.to_dict())
    assert back.to_dict() == caps.to_dict()
    assert back.node_id == caps.node_id


def test_empty_registry_advertises_nothing_but_stays_valid():
    caps = NodeCapabilities.from_registry(BackendRegistry(), _ident())
    assert caps.backends == []
    assert caps.spec_types() == []
    assert not caps.matches(DecisionSpec(type="categorical",
                                        options=["a", "b"]))


def test_describe_is_human_readable():
    text = _caps("skald").describe()
    assert "skald" in text and "uniform" in text and "categorical" in text


def test_models_and_features_round_trip():
    caps = NodeCapabilities.from_gate(
        build_gate(), _ident(),
        models=[{"name": "m-1", "version": "2"}],
        features=["tls", "batching"])
    back = NodeCapabilities.from_dict(caps.to_dict())
    assert back.models == [{"name": "m-1", "version": "2"}]
    assert back.features == ["tls", "batching"]


# --- failure -----------------------------------------------------------------

def test_rejects_empty_node_id():
    with pytest.raises(SpecError, match="node_id"):
        NodeCapabilities(node_id="")


def test_rejects_backend_without_name():
    with pytest.raises(SpecError, match="backend"):
        NodeCapabilities(node_id="x", backends=[{"spec_types": []}])


def test_rejects_wrong_protocol_version():
    d = _caps().to_dict()
    d["protocol_version"] = PROTOCOL_VERSION + 1
    with pytest.raises(SpecError, match="protocol version"):
        NodeCapabilities.from_dict(d)


def test_rejects_missing_node_id():
    d = _caps().to_dict()
    del d["node_id"]
    with pytest.raises(SpecError, match="node_id"):
        NodeCapabilities.from_dict(d)


def test_rejects_non_dict():
    with pytest.raises(SpecError):
        NodeCapabilities.from_dict(["not", "a", "dict"])


# --- boundary ----------------------------------------------------------------

def test_from_dict_defaults_missing_optionals():
    d = {"node_id": "abc123"}
    caps = NodeCapabilities.from_dict(d)
    assert caps.backends == [] and caps.features == []
    assert caps.display_name == ""


def test_advertisement_reflects_registry_changes():
    gate = build_gate()
    before = NodeCapabilities.from_gate(gate, _ident()).backend_names()
    gate.register(_extra_backend())
    after = NodeCapabilities.from_gate(gate, _ident()).backend_names()
    assert set(after) == set(before) | {"extra"}


def _extra_backend():
    from hugrgate.backend import Backend
    from hugrgate.result import DecisionResult

    class Extra(Backend):
        name = "extra"

        def capabilities(self):
            return {"spec_types": ["binary"]}

        def supports(self, spec):
            return spec.type == "binary"

        def evaluate(self, state, spec, context=None):
            return DecisionResult(value=True, probability=1.0,
                                  distribution={"true": 1.0},
                                  uncertainty=0.0, backend=self.name,
                                  model="extra-1")

    return Extra()
