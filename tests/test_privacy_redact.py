"""Slice 232 — Redaction pipeline v2.

Tests each redactor strategy, per-field and per-level pipelines,
deep metadata scrubbing (the slice-40 hardening), and adversarial
cases (nested state smuggling, secrets embedded in longer strings,
non-string values).
"""

from __future__ import annotations

import pytest

from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_labels import FieldLabels, Sensitivity
from hugrgate.privacy_redact import (
    DROP,
    DropRedactor,
    HashRedactor,
    MaskRedactor,
    PatternRedactor,
    RedactionPipeline,
    TokenRedactor,
    redact_metadata,
    redact_record_deep,
)
from hugrgate.provenance import DecisionRecord


def test_mask_redactor():
    r = MaskRedactor()
    assert r.redact("secret", field="ssn") == "[REDACTED]"
    assert r.redact(12345, field="n") == "[REDACTED]"
    assert r.name == "mask"


def test_mask_redactor_partial():
    r = MaskRedactor(keep_last=4)
    assert r.redact("4242424242424242", field="cc") == "[REDACTED]…4242"
    assert r.redact("abc", field="s") == "[REDACTED]"  # too short: full mask


def test_pattern_redactor_scrubs_strings():
    r = PatternRedactor([("email", r"[\w.]+@[\w.]+")])
    assert r.redact("contact me at a@b.io please", field="note") == \
        "contact me at [REDACTED:email] please"


def test_pattern_redactor_walks_nested():
    r = PatternRedactor([("email", r"[\w.]+@[\w.]+")])
    value = {"user": {"email": "a@b.io"}, "tags": ["x", "c@d.io"]}
    assert r.scrub(value) == {"user": {"email": "[REDACTED:email]"},
                              "tags": ["x", "[REDACTED:email]"]}


def test_pattern_redactor_leaves_non_strings():
    r = PatternRedactor([("x", r"a")])
    assert r.scrub(42) == 42
    assert r.scrub(None) is None


def test_hash_redactor_deterministic():
    r = HashRedactor(salt="s1")
    a = r.redact("same", field="f")
    assert a == r.redact("same", field="f")
    assert a.startswith("hash:")
    # Different field -> different hash (no cross-field joins).
    assert a != r.redact("same", field="g")
    # Different salt -> different hash.
    assert a != HashRedactor(salt="s2").redact("same", field="f")


def test_hash_redactor_requires_salt():
    with pytest.raises(ValueError):
        HashRedactor(salt="")


def test_drop_redactor():
    assert DropRedactor().redact("x", field="f") is DROP
    assert not DROP  # falsy sentinel


def test_token_redactor_duck_typed():
    class Vault:
        def tokenize(self, value):
            return f"tok:{value}"

    r = TokenRedactor(Vault())
    assert r.redact("secret", field="f") == "tok:secret"
    with pytest.raises(TypeError):
        TokenRedactor(object())


def test_pipeline_per_field():
    pipeline = RedactionPipeline(
        field_redactors={"ssn": MaskRedactor(),
                         "cc": DropRedactor(),
                         "user_id": HashRedactor(salt="s")})
    state = {"ssn": "123", "cc": "4111", "user_id": "u1", "name": "n"}
    out, applied = pipeline.apply_to_state(state)
    assert out["ssn"] == "[REDACTED]"
    assert "cc" not in out
    assert out["user_id"].startswith("hash:")
    assert out["name"] == "n"
    assert ("ssn", "mask") in applied
    assert ("cc", "drop") in applied
    assert ("user_id", "hash") in applied
    assert len(applied) == 3  # untouched fields not reported


def test_pipeline_nested_dotted_paths():
    pipeline = RedactionPipeline(
        field_redactors={"user.ssn": MaskRedactor()})
    state = {"user": {"ssn": "123", "name": "n"}}
    out, applied = pipeline.apply_to_state(state)
    assert out == {"user": {"ssn": "[REDACTED]", "name": "n"}}
    assert applied == [("user.ssn", "mask")]


def test_pipeline_text_scrubbing():
    pipeline = RedactionPipeline(
        text_redactor=PatternRedactor([("email", r"[\w.]+@[\w.]+")]))
    out, applied = pipeline.apply_to_state({"note": "mail a@b.io"})
    assert out == {"note": "mail [REDACTED:email]"}
    assert applied == [("note", "pattern")]
    assert pipeline.apply_to_text("hi a@b.io") == "hi [REDACTED:email]"
    assert RedactionPipeline().apply_to_text("plain") == "plain"


def test_pipeline_apply_with_labels():
    labels = FieldLabels({"ssn": "secret", "email": "confidential",
                          "name": "public"})
    pipeline = RedactionPipeline(
        level_redactors={Sensitivity.CONFIDENTIAL: MaskRedactor(),
                         Sensitivity.SECRET: DropRedactor()})
    state = {"ssn": "1", "email": "e@x.io", "name": "n"}
    out, applied = pipeline.apply_with_labels(state, labels)
    assert "ssn" not in out          # secret -> drop
    assert out["email"] == "[REDACTED]"  # confidential -> mask
    assert out["name"] == "n"
    assert ("ssn", "drop") in applied
    assert ("email", "mask") in applied


def test_pipeline_apply_with_labels_field_override_wins():
    labels = FieldLabels({"ssn": "secret"})
    pipeline = RedactionPipeline(
        field_redactors={"ssn": HashRedactor(salt="s")},
        level_redactors={Sensitivity.SECRET: DropRedactor()})
    out, _ = pipeline.apply_with_labels({"ssn": "1"}, labels)
    assert out["ssn"].startswith("hash:")


def test_redact_metadata_deep():
    metadata = {
        "note": "keep",
        "state_keys": ["ssn"],
        "nested": {"state": {"ssn": "123"}, "raw_state": "x",
                   "ok": True},
        "items": [{"state_keys": ["a"]}, {"b": 1}],
    }
    out = redact_metadata(metadata)
    assert out["note"] == "keep"
    assert "state_keys" not in out
    assert out["nested"] == {"ok": True}
    assert out["items"] == [{}, {"b": 1}]
    assert out["redacted"] is True


def test_redact_metadata_idempotent():
    once = redact_metadata({"state": {"a": 1}})
    assert redact_metadata(once) == once


def test_redact_metadata_pattern_scrub():
    redactor = PatternRedactor([("email", r"[\w.]+@[\w.]+")])
    out = redact_metadata({"note": "mail a@b.io"}, redactor)
    assert out["note"] == "mail [REDACTED:email]"


def test_guard_redact_record_is_deep_now():
    guard = PrivacyGuard()
    record = DecisionRecord(
        request_hash="abc", spec={}, backend="b", model="m",
        metadata={"state_keys": ["ssn"], "note": "keep",
                  "nested": {"raw_state": {"ssn": "1"}}})
    redacted = guard.redact_record(record)
    assert "state_keys" not in redacted.metadata
    assert redacted.metadata["note"] == "keep"
    assert redacted.metadata["nested"] == {}
    assert redacted.metadata["redacted"] is True
    # Original untouched (backward compat with slice-40 test).
    assert record.metadata["state_keys"] == ["ssn"]


def test_redact_record_deep_function():
    record = DecisionRecord(
        request_hash="abc", spec={}, backend="b", model="m",
        metadata={"state": {"x": 1}})
    out = redact_record_deep(record)
    assert "state" not in out.metadata
    assert out.metadata["redacted"] is True


def test_adversarial_state_smuggled_in_metadata():
    # Attack: backend stuffs raw state into a nested metadata dict
    # hoping the old top-level-only scrub misses it.
    guard = PrivacyGuard()
    record = DecisionRecord(
        request_hash="abc", spec={}, backend="b", model="m",
        metadata={"debug": {"context": {"state": {"ssn": "123-45"}}}})
    redacted = guard.redact_record(record)
    assert redacted.metadata["debug"] == {"context": {}}


def test_adversarial_secret_in_longer_string():
    pipeline = RedactionPipeline(
        text_redactor=PatternRedactor(
            [("api_key", r"sk-[A-Za-z0-9]{8,}")]))
    out, _ = pipeline.apply_to_state(
        {"log": "call failed with key sk-abcdefgh1234 retrying"})
    assert "sk-abcdefgh1234" not in out["log"]
    assert "[REDACTED:api_key]" in out["log"]
