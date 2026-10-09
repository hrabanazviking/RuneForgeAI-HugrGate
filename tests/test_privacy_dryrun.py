"""Slice 245 — Privacy dry-run mode."""

from __future__ import annotations

from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_dryrun import PrivacyDryRun
from hugrgate.privacy_labels import FieldLabels
from hugrgate.privacy_payload import RemotePayloadCompiler


class _Remote:
    name = "cloud-x"
    is_remote = True


class _Local:
    name = "local"
    is_remote = False


def _policy(**kw):
    kw.setdefault("remote_inference", True)
    return DecisionPolicy(privacy_class="standard", **kw)


def test_dry_run_allow():
    guard = PrivacyGuard()
    report = PrivacyDryRun(guard).evaluate({"q": "hi"}, backend=_Local(),
                                           policy=_policy())
    assert report.allowed is True
    assert report.denied_reason is None
    assert report.stages[0].stage == "attempt_gate"
    assert "allowed=True" in report.summary()


def test_dry_run_deny_at_gate():
    guard = PrivacyGuard(remote_inference="forbidden")
    report = PrivacyDryRun(guard).evaluate({"q": "hi"}, backend=_Remote(),
                                           policy=_policy())
    assert report.allowed is False
    assert report.denied_reason is not None
    assert "blocked" in report.denied_reason
    assert report.stages[0].action == "deny"


def test_dry_run_local_only_strip_reported():
    guard = PrivacyGuard()
    labels = FieldLabels(local_only=["ssn"])
    report = PrivacyDryRun(guard).evaluate(
        {"ssn": "123-45-6789", "q": "hi"}, backend=_Remote(),
        policy=_policy(), labels=labels)
    assert report.allowed is True
    assert report.stripped_fields == ["ssn"]
    strip = next(s for s in report.stages if s.stage == "local_only")
    assert strip.action == "strip"


def test_dry_run_secret_deny_without_compiler():
    guard = PrivacyGuard()
    report = PrivacyDryRun(guard).evaluate(
        {"api_key": "ghp_" + "a" * 36}, backend=_Remote(),
        policy=_policy())
    assert report.allowed is False
    assert report.stages[-1].stage == "secret_scan"
    assert "secret" in report.denied_reason


def test_dry_run_with_compiler_allow():
    guard = PrivacyGuard()
    guard.payload_compiler = RemotePayloadCompiler(guard=guard)
    report = PrivacyDryRun(guard).evaluate({"q": "hi"}, backend=_Remote(),
                                           policy=_policy())
    assert report.allowed is True
    compile_stage = next(s for s in report.stages
                           if s.stage == "payload_compile")
    assert compile_stage.action == "allow"
    assert compile_stage.detail["stages"]


def test_dry_run_with_compiler_deny():
    guard = PrivacyGuard()
    guard.payload_compiler = RemotePayloadCompiler(guard=guard)
    report = PrivacyDryRun(guard).evaluate(
        {"api_key": "ghp_" + "a" * 36}, backend=_Remote(),
        policy=_policy())
    assert report.allowed is False
    assert "secret_detected" in report.denied_reason


def test_dry_run_strict_local_only_deny():
    guard = PrivacyGuard()
    guard.payload_compiler = RemotePayloadCompiler(guard=guard,
                                                   local_only_strict=True)
    labels = FieldLabels(local_only=["ssn"])
    report = PrivacyDryRun(guard).evaluate(
        {"ssn": "x"}, backend=_Remote(), policy=_policy(), labels=labels)
    assert report.allowed is False
    assert "local_only" in report.denied_reason


def test_dry_run_does_not_mutate_state():
    guard = PrivacyGuard()
    guard.payload_compiler = RemotePayloadCompiler(guard=guard)
    labels = FieldLabels(local_only=["ssn"])
    state = {"ssn": "123-45-6789", "nested": {"a": [1, 2]}}
    PrivacyDryRun(guard).evaluate(state, backend=_Remote(),
                                  policy=_policy(), labels=labels)
    assert state == {"ssn": "123-45-6789", "nested": {"a": [1, 2]}}


def test_dry_run_report_serializes():
    guard = PrivacyGuard()
    report = PrivacyDryRun(guard).evaluate({"q": "hi"}, backend=_Local(),
                                           policy=_policy())
    data = report.to_dict()
    assert data["allowed"] is True
    assert data["stages"][0]["action"] == "allow"


def test_dry_run_forbidden_class_deny():
    guard = PrivacyGuard()
    report = PrivacyDryRun(guard).evaluate(
        {"q": "hi"}, backend=_Remote(),
        policy=DecisionPolicy(privacy_class="forbidden"))
    assert report.allowed is False
