"""Slice 173 — local runtime conformance tests.

Runs the conformance suite (``hugrgate.runtimes.conformance``)
against every adapter as part of the normal test run, so contract
drift fails CI. No engines, models, or network required.
"""

from __future__ import annotations

from hugrgate.runtimes import RuntimeRegistry
from hugrgate.runtimes.conformance import (
    ADAPTER_CLASSES,
    check_adapter,
    conformance_summary,
    register_all_adapters,
    run_conformance,
)


def test_all_adapters_conform():
    reports = run_conformance()
    assert len(reports) == len(ADAPTER_CLASSES) == 8
    summary = conformance_summary(reports)
    assert summary["adapters_passed"] == 8, summary["failed"]
    assert summary["checks_failed"] == 0, summary["failed"]


def test_each_adapter_has_contract_checks():
    for cls in ADAPTER_CLASSES:
        report = check_adapter(cls)
        names = {c.name for c in report.checks}
        assert {"available-bool", "info-wellformed", "health-safe",
                "hooks-safe", "errors-honest", "privacy-local",
                } <= names, cls.__name__


def test_conformance_report_shape():
    reports = run_conformance()
    for report in reports:
        assert report.passed is True
        assert report.failed == []
        d = report.to_dict()
        assert d["adapter"] == report.adapter
        assert d["passed"] is True
        assert len(d["checks"]) == len(report.checks)


def test_summary_counts():
    reports = run_conformance()
    summary = conformance_summary(reports)
    assert summary["adapters"] == 8
    assert summary["checks"] == summary["checks_passed"]
    assert summary["failed"] == []


def test_register_all_adapters():
    registry = register_all_adapters()
    assert isinstance(registry, RuntimeRegistry)
    names = registry.list()
    assert len(names) == 8
    assert len(set(names)) == 8  # unique


def test_no_adapter_available_in_ci():
    # In this environment no engines are installed; the conformance
    # run documents that. If an engine IS installed, the suite still
    # passes — availability is informational, not an assertion.
    reports = run_conformance()
    for report in reports:
        assert isinstance(report.available, bool)
