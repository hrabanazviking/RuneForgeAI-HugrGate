"""Slice 244 — Policy violation audit log."""

from __future__ import annotations

import pytest

from hugrgate.errors import (
    JurisdictionViolation,
    LocalOnlyViolation,
    PrivacyViolation,
    SecretDetected,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_audit import FileAuditSink, PrivacyAuditEvent, PrivacyAuditLog
from hugrgate.privacy_labels import FieldLabels


class _Remote:
    name = "cloud-x"
    is_remote = True


class _Local:
    name = "local"
    is_remote = False


def test_record_and_verify():
    log = PrivacyAuditLog()
    log.record("backend_blocked", backend="x", reason="forbidden")
    log.record("flow_denied", field="secret")
    assert log.count() == 2
    assert log.verify() is True


def test_chain_links_events():
    log = PrivacyAuditLog()
    first = log.record("a")
    second = log.record("b")
    assert second.prev_hash == first.event_hash
    assert first.prev_hash == ""


def test_tamper_detected():
    log = PrivacyAuditLog()
    log.record("a", x=1)
    log._events[0].details["x"] = 999
    assert log.verify() is False


def test_tamper_deletion_detected():
    log = PrivacyAuditLog()
    log.record("a")
    log.record("b")
    del log._events[0]
    assert log.verify() is False


def test_events_filtered_and_copied():
    log = PrivacyAuditLog()
    log.record("a", v=1)
    got = log.events("a")
    got[0].details["v"] = 999  # mutate the copy
    assert log.events("a")[0].details["v"] == 1
    assert log.events("missing") == []


def test_file_sink_round_trip(tmp_path):
    sink = FileAuditSink(tmp_path / "audit.jsonl")
    log = PrivacyAuditLog(sink=sink)
    log.record("backend_blocked", backend="x")
    lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    import json
    event = json.loads(lines[0])
    assert event["event"] == "backend_blocked"
    assert event["event_hash"]  # hash persisted


def test_broken_sink_does_not_break_operations():
    def bad_sink(event):
        raise OSError("disk full")

    log = PrivacyAuditLog(sink=bad_sink)
    entry = log.record("a")  # no raise
    assert entry.event == "a"
    assert log.verify() is True


def test_serialization_round_trip():
    log = PrivacyAuditLog()
    log.record("a", x=1)
    rebuilt = PrivacyAuditLog.from_dict(log.to_dict())
    assert rebuilt.count() == 1
    assert rebuilt.verify() is True


def test_guard_denials_are_audited():
    log = PrivacyAuditLog()
    guard = PrivacyGuard(remote_inference="forbidden", audit_log=log)
    policy = DecisionPolicy(privacy_class="standard")
    with pytest.raises(PrivacyViolation):
        guard.check_backend(_Remote(), policy)
    events = log.events("backend_blocked")
    assert len(events) == 1
    assert events[0].details["backend"] == "cloud-x"


def test_guard_allows_are_not_audited():
    log = PrivacyAuditLog()
    guard = PrivacyGuard(audit_log=log)
    policy = DecisionPolicy(privacy_class="standard")
    guard.check_backend(_Local(), policy)
    assert log.count() == 0


def test_guard_secret_detection_audited():
    log = PrivacyAuditLog()
    guard = PrivacyGuard(audit_log=log)
    with pytest.raises(SecretDetected):
        guard.check_no_secrets({"api_key": "ghp_" + "a" * 36})
    events = log.events("secret_detected")
    assert len(events) == 1
    assert events[0].details["findings"] >= 1


def test_guard_local_only_strict_audited():
    log = PrivacyAuditLog()
    guard = PrivacyGuard(audit_log=log)
    labels = FieldLabels(local_only=["ssn"])
    with pytest.raises(LocalOnlyViolation):
        guard.enforce_local_only({"ssn": "1"}, labels, _Remote(),
                                 strict=True)
    assert len(log.events("local_only_violation")) == 1


def test_guard_jurisdiction_denial_audited():
    log = PrivacyAuditLog()
    guard = PrivacyGuard(audit_log=log,
                         jurisdictions_allowed=frozenset({"EU"}))
    policy = DecisionPolicy(privacy_class="standard")
    with pytest.raises(JurisdictionViolation):
        guard.check_backend(_Remote(), policy)  # "unknown" not in EU
    assert len(log.events("jurisdiction_violation")) == 1


def test_guard_without_audit_log_unchanged():
    guard = PrivacyGuard(remote_inference="forbidden")
    with pytest.raises(PrivacyViolation):
        guard.check_backend(_Remote(),
                            DecisionPolicy(privacy_class="standard"))


def test_adversarial_event_names_accepted():
    log = PrivacyAuditLog()
    entry = log.record("operator-note", note="reviewed")
    assert entry.event == "operator-note"
    assert log.verify() is True
    # Event dict round trip preserves custom names.
    rebuilt = PrivacyAuditEvent.from_dict(entry.to_dict())
    assert rebuilt.event == "operator-note"
