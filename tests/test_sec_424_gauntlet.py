"""Slice 424 — the security gauntlet.

Runs every Security Forge adversarial battery in one pass;
all twelve must hold.
"""

from __future__ import annotations

from hugrgate.security.gauntlet import (
    SecurityGauntletReport,
    run_security_gauntlet,
)


def test_security_gauntlet_all_batteries_hold():
    report = run_security_gauntlet()
    assert isinstance(report, SecurityGauntletReport)
    assert len(report.batteries) == 12
    assert report.failed == [], [
        (b.name, b.detail) for b in report.failed]
    assert report.passed


def test_gauntlet_report_summary_is_honest():
    report = run_security_gauntlet()
    text = report.summary()
    assert "12/12" in text
    assert "gauntlet PASSED" in text
    payload = report.to_dict()
    assert payload["passed"] is True
    assert len(payload["batteries"]) == 12
