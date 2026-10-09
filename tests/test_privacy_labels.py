"""Slice 227 — Field-level sensitivity labels."""

from __future__ import annotations

import pytest

from hugrgate.privacy_labels import (
    FieldLabels,
    Sensitivity,
    filter_by_clearance,
)


@pytest.fixture
def labels():
    return FieldLabels(
        {"ssn": "secret",
         "user.email": Sensitivity.CONFIDENTIAL,
         "user": "internal",
         "session_id": Sensitivity.PUBLIC},
        default="public",
        local_only={"api_key", "user.ssn"})


def test_label_exact_and_default(labels):
    assert labels.label("ssn") is Sensitivity.SECRET
    assert labels.label("unknown_field") is Sensitivity.PUBLIC
    assert labels.label("session_id") is Sensitivity.PUBLIC


def test_label_dotted_specificity(labels):
    # Exact dotted label beats the parent label.
    assert labels.label("user.email") is Sensitivity.CONFIDENTIAL
    # Parent label covers unlabeled children.
    assert labels.label("user.name") is Sensitivity.INTERNAL
    # Parent label covers deeper nesting too.
    assert labels.label("user.address.zip") is Sensitivity.INTERNAL


def test_label_invalid_rejected():
    with pytest.raises(ValueError):
        FieldLabels({"x": "topsecret"})
    with pytest.raises(ValueError):
        FieldLabels(default="whatever")


def test_label_state_walks_nested():
    labels = FieldLabels({"user.ssn": "secret"})
    state = {"user": {"name": "Volmarr", "ssn": "123"}, "x": 1}
    labeled = labels.label_state(state)
    assert labeled == {"user.name": Sensitivity.PUBLIC,
                       "user.ssn": Sensitivity.SECRET,
                       "x": Sensitivity.PUBLIC}


def test_fields_at_or_above(labels):
    state = {"ssn": "1", "user": {"email": "e", "name": "n"}, "x": 1}
    assert labels.fields_at_or_above("secret", state) == ["ssn"]
    assert labels.fields_at_or_above(Sensitivity.CONFIDENTIAL, state) == \
        ["ssn", "user.email"]
    # Without state: explicitly labeled paths only.
    assert "ssn" in labels.fields_at_or_above("secret")


def test_is_local_only(labels):
    assert labels.is_local_only("api_key")
    assert labels.is_local_only("user.ssn")
    assert not labels.is_local_only("user.email")
    assert not labels.is_local_only("ssn")


def test_filter_by_clearance_drops_above():
    labels = FieldLabels({"ssn": "secret", "email": "confidential"},
                         default="public")
    state = {"ssn": "1", "email": "e@x.io", "name": "n"}
    assert filter_by_clearance(state, labels, "confidential") == \
        {"email": "e@x.io", "name": "n"}
    assert filter_by_clearance(state, labels, "public") == {"name": "n"}
    assert filter_by_clearance(state, labels, "secret") == state


def test_filter_by_clearance_drops_local_only_for_remote():
    labels = FieldLabels({"api_key": "internal"}, local_only={"api_key"})
    state = {"api_key": "k", "name": "n"}
    assert filter_by_clearance(state, labels, "secret") == {"name": "n"}
    # In-process consumers may keep local-only fields explicitly.
    assert filter_by_clearance(state, labels, "secret",
                               drop_local_only=False) == state


def test_filter_by_clearance_nested_pruning():
    labels = FieldLabels({"user.ssn": "secret", "user": "internal"})
    state = {"user": {"ssn": "1", "name": "n"}, "x": 1}
    out = filter_by_clearance(state, labels, "internal")
    assert out == {"user": {"name": "n"}, "x": 1}
    out = filter_by_clearance(state, labels, "public")
    assert out == {"x": 1}  # emptied "user" mapping pruned


def test_filter_does_not_mutate_input():
    labels = FieldLabels({"ssn": "secret"})
    state = {"ssn": "1", "nested": {"a": 1}}
    snapshot = {"ssn": "1", "nested": {"a": 1}}
    filter_by_clearance(state, labels, "public")
    assert state == snapshot


def test_round_trip_dict(labels):
    rebuilt = FieldLabels.from_dict(labels.to_dict())
    assert rebuilt.to_dict() == labels.to_dict()
    assert rebuilt.label("user.email") is Sensitivity.CONFIDENTIAL
    assert rebuilt.is_local_only("api_key")


def test_sensitivity_ordering():
    assert Sensitivity.PUBLIC < Sensitivity.INTERNAL < \
        Sensitivity.CONFIDENTIAL < Sensitivity.SECRET


def test_adversarial_smuggled_nested_secret():
    # Adversarial: attacker nests a secret-labeled field deeper hoping
    # the parent label ("internal") masks it — the exact dotted label
    # still wins and filtering removes it.
    labels = FieldLabels({"user": "internal", "user.ssn": "secret"})
    state = {"user": {"profile": {"ssn": "hidden"}}}
    # "user.profile.ssn" has no exact label; parent "user" -> internal.
    # This documents the boundary: label the exact path you protect.
    assert labels.label("user.profile.ssn") is Sensitivity.INTERNAL
    exact = FieldLabels({"user.profile.ssn": "secret"})
    out = filter_by_clearance(state, exact, "internal")
    assert out == {}
