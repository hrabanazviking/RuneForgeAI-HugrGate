"""Slice 246 — Privacy explanation reports."""

from __future__ import annotations

from hugrgate.errors import (
    DataFlowDenied,
    HugrGateError,
    JurisdictionViolation,
    LocalOnlyViolation,
    PrivacyViolation,
    SealError,
    SecretDetected,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_dryrun import PrivacyDryRun
from hugrgate.privacy_explain import PrivacyExplainer, explain_denial
from hugrgate.privacy_provenance import PrivacyAwareProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def test_explain_privacy_violation():
    err = PrivacyViolation("remote blocked",
                           backend="cloud-x", privacy_class="strict")
    text = PrivacyExplainer().explain_denial(err)
    assert "privacy_violation" in text
    assert "What happened" in text
    assert "Why this exists" in text
    assert "What you can do" in text
    assert "cloud-x" in text


def test_explain_each_known_code():
    errors = [
        DataFlowDenied("flow blocked", rule="class-eligibility"),
        JurisdictionViolation("jurisdiction", jurisdiction="unknown"),
        LocalOnlyViolation("local-only", field="ssn"),
        SecretDetected("secret", findings=[{"pattern": "github-token"}]),
        SealError("bad tag"),
        PrivacyViolation("guard blocked"),
    ]
    for err in errors:
        text = PrivacyExplainer().explain_denial(err)
        assert err.code in text
        assert "What you can do" in text
        assert "no message" not in text  # every test error has a message


def test_explain_unknown_code_falls_back():
    err = HugrGateError("mystery")
    text = PrivacyExplainer().explain_denial(err)
    assert "hugrgate_error" in text
    assert "No specific remediation" in text


def test_explain_missing_placeholder_is_literal():
    # Template references {d[trust_level]}; details lack it.
    err = PrivacyViolation("blocked")
    text = PrivacyExplainer().explain_denial(err)
    assert "(unknown)" in text


def test_explain_with_context():
    err = PrivacyViolation("blocked")
    text = PrivacyExplainer().explain_denial(
        err, context={"trust_level": "basic"})
    assert "'basic'" in text


def test_one_shot_helper():
    text = explain_denial(SecretDetected("secret found"))
    assert "secret_detected" in text
    assert "Rotate the exposed secret" in text


def test_explain_dry_run_denied():
    guard = PrivacyGuard(remote_inference="forbidden")

    class _Remote:
        name = "cloud-x"
        is_remote = True

    report = PrivacyDryRun(guard).evaluate(
        {"q": "hi"}, backend=_Remote(),
        policy=DecisionPolicy(privacy_class="standard"))
    text = PrivacyExplainer().explain_dry_run(report)
    assert "DENIED" in text
    assert "attempt_gate" in text
    assert "not the guard" in text


def test_explain_dry_run_allowed():
    guard = PrivacyGuard()

    class _Local:
        name = "local"
        is_remote = False

    report = PrivacyDryRun(guard).evaluate(
        {"q": "hi"}, backend=_Local(),
        policy=DecisionPolicy(privacy_class="standard"))
    text = PrivacyExplainer().explain_dry_run(report)
    assert "ALLOWED" in text
    assert "Denial reason" not in text


def test_explain_record_masked():
    store = PrivacyAwareProvenanceStore()
    record = store.append_decision(
        {"secret": "x"}, _spec(),
        DecisionResult(value="a", probability=1.0,
                       distribution={"a": 1.0}),
        DecisionPolicy(privacy_class="strict"))
    text = PrivacyExplainer().explain_record(record)
    assert "redacted" in text
    assert "forbids keeping them" in text
    assert "x" not in text  # explanation never leaks the value


def test_explain_record_public():
    store = PrivacyAwareProvenanceStore()
    record = store.append_decision(
        {"q": "hi"}, _spec(),
        DecisionResult(value="a", probability=1.0,
                       distribution={"a": 1.0}),
        DecisionPolicy(privacy_class="public"))
    text = PrivacyExplainer().explain_record(record)
    assert "public" in text


def test_adversarial_never_leaks_secret_in_explanation():
    secret = "ghp_" + "z" * 36
    err = SecretDetected("secret in field api_key",
                         findings=[{"pattern": "github-token"}])
    # details carry only the pattern, never the value
    text = PrivacyExplainer().explain_denial(err)
    assert secret not in text
    assert "github-token" in text
