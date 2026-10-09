"""Slice 234 — Secret detection hooks.

Tests curated patterns, the entropy heuristic (opt-in), state
scanning with dotted paths, assert_no_secrets raising, guard hook
integration, and adversarial cases (obfuscated assignments,
previews that don't leak the secret).
"""

from __future__ import annotations

import pytest

from hugrgate.errors import (
    HugrGateError,
    PrivacyViolation,
    SecretDetected,
)
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_secrets import (
    SecretFinding,
    SecretScanner,
    assert_no_secrets,
)


@pytest.fixture
def scanner():
    return SecretScanner()


def test_aws_access_key(scanner):
    findings = scanner.scan_text("key=AKIAIOSFODNN7EXAMPLE")
    assert any(f.pattern == "aws_access_key" for f in findings)
    assert findings[0].confidence == "high"


def test_github_token(scanner):
    findings = scanner.scan_text("token ghp_" + "a" * 36)
    assert any(f.pattern == "github_token" for f in findings)


def test_slack_token(scanner):
    findings = scanner.scan_text("xoxb-123456789012-abcdefghij")
    assert any(f.pattern == "slack_token" for f in findings)


def test_openai_key(scanner):
    # Regression: slice 247 fuzzing found sk- keys were missed.
    findings = scanner.scan_text("key=sk-" + "a" * 32)
    assert any(f.pattern == "openai_key" for f in findings)


def test_pem_private_key(scanner):
    findings = scanner.scan_text("-----BEGIN RSA PRIVATE KEY-----\nMII...")
    assert any(f.pattern == "pem_private_key" for f in findings)


def test_credential_assignment(scanner):
    findings = scanner.scan_text('api_key = "supersecretvalue123"')
    assert any(f.pattern == "credential_assignment" for f in findings)


def test_bearer_token(scanner):
    findings = scanner.scan_text(
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234")
    assert any(f.pattern == "bearer_token" for f in findings)


def test_clean_text_no_findings(scanner):
    assert scanner.scan_text("the raven flies at midnight") == []
    assert scanner.scan_text("user count: 42") == []


def test_preview_never_leaks_secret(scanner):
    secret = "AKIAIOSFODNN7EXAMPLE"
    findings = scanner.scan_text(f"leaked {secret} here")
    assert findings
    for finding in findings:
        assert secret not in finding.preview


def test_scan_state_dotted_paths(scanner):
    state = {"user": {"token": "ghp_" + "b" * 36}, "name": "n"}
    findings = scanner.scan_state(state)
    assert len(findings) == 1
    assert findings[0].field == "user.token"
    assert findings[0].pattern == "github_token"


def test_scan_state_walks_lists(scanner):
    state = {"keys": ["AKIAIOSFODNN7EXAMPLE", "clean"]}
    findings = scanner.scan_state(state)
    assert [f.field for f in findings] == ["keys[0]"]


def test_scan_state_dedupes(scanner):
    state = {"a": "AKIAIOSFODNN7EXAMPLE",
             "b": "AKIAIOSFODNN7EXAMPLE"}
    findings = scanner.scan_state(state)
    assert {(f.field, f.pattern) for f in findings} == \
        {("a", "aws_access_key"), ("b", "aws_access_key")}


def test_assert_no_secrets_raises(scanner):
    with pytest.raises(SecretDetected) as exc:
        scanner.assert_no_secrets({"k": "AKIAIOSFODNN7EXAMPLE"})
    assert "aws_access_key" in str(exc.value)
    assert exc.value.details["findings"]
    assert isinstance(exc.value, PrivacyViolation)


def test_assert_no_secrets_passes_clean(scanner):
    scanner.assert_no_secrets({"name": "Volmarr", "count": 3})


def test_one_shot_function():
    with pytest.raises(SecretDetected):
        assert_no_secrets({"t": "xoxb-123456789012-abcdefghij"})
    assert_no_secrets({"t": "nothing here"})


def test_guard_hook():
    guard = PrivacyGuard()
    guard.check_no_secrets({"name": "clean"})  # no raise
    with pytest.raises(SecretDetected):
        guard.check_no_secrets({"k": "AKIAIOSFODNN7EXAMPLE"})


def test_entropy_scan_opt_in():
    opaque = "dGhlIHF1aWNrIGJyb3duIGZveCBqdW1wcyBvdmVyIDEyMzQ1Njc4OTA="
    default = SecretScanner()
    assert default.scan_text(f"blob {opaque}") == []  # off by default
    aggressive = SecretScanner(entropy_scan=True)
    findings = aggressive.scan_text(f"blob {opaque}")
    assert any(f.pattern == "high_entropy_token" for f in findings)
    # Natural text still clean even with entropy scan on.
    assert aggressive.scan_text("the quick brown fox jumps") == []


def test_min_confidence_filter():
    scanner = SecretScanner(min_confidence="high")
    # bearer_token is medium -> filtered out.
    assert scanner.scan_text(
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234") == []
    # aws key is high -> kept.
    assert scanner.scan_text("AKIAIOSFODNN7EXAMPLE")


def test_extra_patterns():
    scanner = SecretScanner(
        extra_patterns=[("internal_key", r"INTERNAL-[0-9]{6}", "high")])
    findings = scanner.scan_text("key INTERNAL-123456")
    assert any(f.pattern == "internal_key" for f in findings)


def test_invalid_confidence_rejected():
    with pytest.raises(ValueError):
        SecretScanner(min_confidence="extreme")


def test_finding_to_dict():
    finding = SecretFinding(field="a", pattern="p", confidence="high",
                            preview="ab…")
    assert finding.to_dict() == {"field": "a", "pattern": "p",
                                 "confidence": "high", "preview": "ab…"}


def test_adversarial_obfuscated_assignment(scanner):
    # Attacker-adjacent accident: secret with varied spacing/quoting.
    for text in ['password: "hunter2hunter2"',
                 "SECRET='s3cr3tvalue!'",
                 "client_secret=hunter2hunter2"]:
        assert scanner.scan_text(text), text


def test_adversarial_secret_in_nested_state(scanner):
    state = {"config": {"auth": {"headers": {
        "Authorization": "Bearer abcdefghijklmnopqrstuvwxyz1234"}}}}
    findings = scanner.scan_state(state)
    assert findings
    assert findings[0].field == \
        "config.auth.headers.Authorization"


def test_violation_taxonomy_and_wire():
    err = SecretDetected("found", findings=[])
    assert err.code == "secret_detected"
    assert err.recoverable is False
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert type(rebuilt) is SecretDetected
