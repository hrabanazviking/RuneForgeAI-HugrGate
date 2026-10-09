"""Slice 146 — adaptive policy versioning tests."""

from __future__ import annotations

import pytest

from hugrgate.adaptive.versioning import (
    AdaptivePolicyVersioning,
    PolicyVersion,
    digest_state,
)
from hugrgate.errors import SpecError


def versioning():
    return AdaptivePolicyVersioning()


# --- success ---------------------------------------------------------------

def test_create_and_activate():
    v = versioning()
    v1 = v.create_version({"weights": [1.0]}, note="first")
    assert isinstance(v1, PolicyVersion)
    assert v1.version_id == "v1" and v1.parent_id is None
    assert len(v1.state_digest) == 64  # sha256 hex
    assert v.active is None
    v.activate("v1")
    assert v.active.version_id == "v1"

def test_lineage_walks_parents():
    v = versioning()
    v.create_version({"g": 1}, note="gen1")
    v.create_version({"g": 2}, parent_id="v1", note="gen2")
    v.create_version({"g": 3}, parent_id="v2", note="gen3")
    lineage = v.lineage("v3")
    assert [x.version_id for x in lineage] == ["v3", "v2", "v1"]
    assert lineage[-1].parent_id is None

def test_digest_is_content_addressed():
    v = versioning()
    state = {"weights": [1.0, 2.0], "alpha": 0.5}
    v1 = v.create_version(state)
    assert v1.state_digest == digest_state(state)
    assert v.verify("v1", state) is True
    assert v.verify("v1", {"weights": [9.0]}) is False
    # Key order does not matter: canonical JSON.
    assert v.verify("v1", {"alpha": 0.5, "weights": [1.0, 2.0]}) is True

def test_state_round_trips():
    v = versioning()
    v.create_version({"nested": {"x": [1, 2]}})
    state = v.state_for("v1")
    state["nested"]["x"].append(3)  # caller cannot mutate the archive
    assert v.state_for("v1") == {"nested": {"x": [1, 2]}}

def test_activation_history():
    v = versioning()
    v.create_version({"g": 1})
    v.create_version({"g": 2}, parent_id="v1")
    v.activate("v1")
    v.activate("v2")
    actions = [(e["action"], e["version_id"]) for e in v.history()]
    assert actions == [("create", "v1"), ("create", "v2"),
                       ("activate", "v1"), ("activate", "v2")]
    assert v.history()[3]["previous"] == "v1"

def test_contains_and_len():
    v = versioning()
    v.create_version({"g": 1})
    assert "v1" in v and "v9" not in v and len(v) == 1
    assert v.get("v1").version_id == "v1"
    assert v.get("v9") is None

def test_to_dict_schema():
    v = versioning()
    v.create_version({"g": 1})
    d = v.to_dict()
    assert d["schema"] == "adaptive-policy-versions/v1"
    assert d["versions"]["v1"]["note"] == ""

# --- failure ---------------------------------------------------------------

def test_unknown_parent_rejected():
    v = versioning()
    with pytest.raises(SpecError):
        v.create_version({"g": 1}, parent_id="v99")

def test_activate_unknown_rejected():
    with pytest.raises(SpecError):
        versioning().activate("v99")

def test_lineage_unknown_rejected():
    with pytest.raises(SpecError):
        versioning().lineage("v99")

def test_state_for_unknown_rejected():
    with pytest.raises(SpecError):
        versioning().state_for("v99")

def test_verify_unknown_rejected():
    with pytest.raises(SpecError):
        versioning().verify("v99", {})

def test_non_serializable_state_rejected():
    with pytest.raises(SpecError):
        digest_state({"fn": object()})
