"""Slice 497 — license/provenance audit tests.

Covers license classification (allow / review / unknown), compound
expressions, the runtime-closure resolver, and the report verdict.
"""

from __future__ import annotations

from hugrgate.gauntlet.license_audit import (
    LicenseReport,
    PackageLicense,
    audit_runtime,
    classify_license,
    runtime_closure,
)


def test_classify_permissive():
    assert classify_license("MIT") == "allow"
    assert classify_license("Apache-2.0") == "allow"
    assert classify_license("BSD-3-Clause") == "allow"
    assert classify_license("License :: OSI Approved :: MIT License") == "allow"
    assert classify_license("MPL-2.0") == "allow"


def test_classify_compound_expression():
    assert classify_license("BSD-3-Clause AND 0BSD AND MIT AND Zlib") == "allow"
    assert classify_license("MIT OR Apache-2.0") == "allow"


def test_classify_copyleft_needs_review():
    assert classify_license("GPL-3.0-only") == "review"
    assert classify_license("AGPL-3.0") == "review"
    assert classify_license("LGPL-2.1-or-later") == "review"
    # Copyleft beats permissive in a compound declaration.
    assert classify_license("MIT AND GPL-3.0") == "review"


def test_classify_unknown():
    assert classify_license(None) == "unknown"
    assert classify_license("") == "unknown"
    assert classify_license("Proprietary") == "unknown"
    assert classify_license("Some Custom License 1.0") == "unknown"


def test_report_clean_iff_all_allow():
    clean = LicenseReport(packages=[
        PackageLicense("a", "1.0", "MIT", "allow"),
        PackageLicense("b", "2.0", "Apache-2.0", "allow"),
    ])
    assert clean.clean
    assert clean.needs_review == []
    assert clean.by_status["allow"] and len(clean.by_status["allow"]) == 2

    dirty = LicenseReport(packages=[
        PackageLicense("a", "1.0", "MIT", "allow"),
        PackageLicense("c", "3.0", None, "unknown"),
    ])
    assert not dirty.clean
    assert [p.name for p in dirty.needs_review] == ["c"]


def test_report_to_dict_sorted():
    report = LicenseReport(packages=[
        PackageLicense("zebra", "1.0", "MIT", "allow"),
        PackageLicense("apple", "1.0", "MIT", "allow"),
    ])
    names = [p["name"] for p in report.to_dict()["packages"]]
    assert names == ["apple", "zebra"]


def test_runtime_closure_contains_pyyaml():
    closure = runtime_closure("pyproject.toml")
    assert "pyyaml" in closure
    # Dev-only tools are not in the runtime closure.
    assert "pytest" not in closure
    assert "ruff" not in closure


def test_audit_runtime_is_clean():
    report = audit_runtime("pyproject.toml")
    names = {p.name.lower() for p in report.packages}
    assert "hugrgate" in names
    assert "pyyaml" in names
    assert report.clean, (
        f"runtime closure needs review: {report.needs_review}")
