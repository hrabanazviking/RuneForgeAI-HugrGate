"""Slice 235 — PII detector interface."""

from __future__ import annotations

import pytest

from hugrgate.privacy_pii import (
    CompositePIIDetector,
    PIIDetector,
    PIIFinding,
    PIIScrubber,
    RegexPIIDetector,
)


@pytest.fixture
def detector():
    return RegexPIIDetector()


def test_email_high_confidence(detector):
    findings = detector.scan_text("mail volmarr@example.com now")
    assert [(f.kind, f.confidence) for f in findings] == \
        [("email", "high")]
    assert "volmarr@example.com" not in findings[0].preview


def test_phone_medium_confidence(detector):
    findings = detector.scan_text("call +1 (555) 123-4567")
    assert any(f.kind == "phone" for f in findings)


def test_ssn_validated(detector):
    findings = detector.scan_text("ssn 123-45-6789")
    assert any(f.kind == "ssn" and f.confidence == "high"
               for f in findings)


def test_ssn_invalid_area_rejected(detector):
    # 000 and 666 areas are never valid SSNs — no false positive.
    assert not detector.scan_text("id 000-12-3456")
    assert not detector.scan_text("id 666-12-3456")


def test_credit_card_luhn_validated(detector):
    # 4111111111111111 passes Luhn; 1234567890123456 does not.
    valid = detector.scan_text("card 4111 1111 1111 1111")
    assert any(f.kind == "credit_card" for f in valid)
    assert not detector.scan_text("order 1234-5678-9012-3456")


def test_ipv4(detector):
    findings = detector.scan_text("host 192.168.1.10 down")
    assert any(f.kind == "ipv4" for f in findings)
    # 999.999.999.999 is not an IPv4 address.
    assert not detector.scan_text("code 999.999.999.999")


def test_clean_text(detector):
    assert detector.scan_text("the raven flies at midnight") == []
    assert detector.scan_text(42) == []


def test_kind_subset():
    detector = RegexPIIDetector(kinds=["email"])
    assert detector.scan_text("a@b.io 123-45-6789")
    assert all(f.kind == "email"
               for f in detector.scan_text("a@b.io 123-45-6789"))
    with pytest.raises(ValueError):
        RegexPIIDetector(kinds=["dna"])


def test_scan_state_nested(detector):
    state = {"user": {"email": "a@b.io"}, "note": "clean"}
    findings = detector.scan_state(state)
    assert [(f.field, f.kind) for f in findings] == \
        [("user.email", "email")]


def test_custom_detector_interface():
    class EmployeeIdDetector(PIIDetector):
        def scan_text(self, text, *, field="<text>"):
            import re
            return [PIIFinding(field, "employee_id", "high", "em…")
                    for _ in re.finditer(r"EMP-\d{6}", text)]

    composite = CompositePIIDetector(
        [RegexPIIDetector(), EmployeeIdDetector()])
    findings = composite.scan_text("EMP-123456 mailed a@b.io")
    kinds = {f.kind for f in findings}
    assert kinds == {"employee_id", "email"}


def test_composite_rejects_non_detectors():
    with pytest.raises(TypeError):
        CompositePIIDetector([object()])
    with pytest.raises(ValueError):
        CompositePIIDetector([])


def test_scrubber_mask(detector):
    scrubber = PIIScrubber(detector, action="mask")
    state = {"email": "a@b.io", "name": "Volmarr",
             "nested": {"ssn": "123-45-6789"}}
    scrubbed, findings = scrubber.scrub_state(state)
    assert scrubbed["email"] == "[PII:email]"
    assert scrubbed["name"] == "Volmarr"
    assert scrubbed["nested"]["ssn"] == "[PII:ssn]"
    assert len(findings) == 2


def test_scrubber_drop(detector):
    scrubber = PIIScrubber(detector, action="drop")
    state = {"email": "a@b.io", "name": "Volmarr"}
    scrubbed, findings = scrubber.scrub_state(state)
    assert scrubbed == {"name": "Volmarr"}
    assert len(findings) == 1


def test_scrubber_invalid_action(detector):
    with pytest.raises(ValueError):
        PIIScrubber(detector, action="encrypt")


def test_scrubber_clean_state_untouched(detector):
    scrubber = PIIScrubber(detector)
    state = {"name": "n", "count": 3}
    scrubbed, findings = scrubber.scrub_state(state)
    assert scrubbed == state and findings == []


def test_scrubber_multiple_kinds_one_field(detector):
    scrubber = PIIScrubber(detector)
    scrubbed, _ = scrubber.scrub_state(
        {"contact": "a@b.io / 123-45-6789"})
    assert scrubbed["contact"] == "[PII:email,ssn]"


def test_finding_to_dict(detector):
    finding = detector.scan_text("a@b.io")[0]
    d = finding.to_dict()
    assert d["kind"] == "email" and d["field"] == "<text>"


def test_adversarial_ssn_like_but_invalid(detector):
    # 900-series areas are never issued: no finding, no noise.
    assert not detector.scan_text("900-12-3456")


def test_adversarial_luhn_decoy(detector):
    # 13 digits that fail Luhn must not become a credit-card finding.
    assert not detector.scan_text("ref 1234567890123")
