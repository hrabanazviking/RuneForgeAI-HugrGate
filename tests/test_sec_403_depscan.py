"""Slice 403 — dependency security scan.

The scanner checks requirement specifiers and installed versions
against a curated advisory DB (every entry verified against
NVD/GitHub advisories), and flags unpinned, unbounded, and
URL-based requirements.
"""

from __future__ import annotations

import pytest

from hugrgate.security.depscan import (
    matches_spec,
    parse_requirement,
    render_report,
    scan_project,
    scan_requirements,
)


def test_vulnerable_pin_flagged():
    findings = scan_requirements(["pyyaml==5.3"])
    cves = {f.cve for f in findings if f.kind == "advisory"}
    assert "CVE-2020-1747" in cves
    assert "CVE-2020-14343" in cves
    assert all(f.severity == "critical" for f in findings
               if f.kind == "advisory")


def test_fixed_pin_clean():
    findings = scan_requirements(["pyyaml==6.0.1"])
    assert [f for f in findings if f.kind == "advisory"] == []


def test_installed_version_used_as_ground_truth():
    # Spec admits a fixed floor, but the installed copy is old.
    findings = scan_requirements(
        ["pyyaml>=5.1"], installed={"pyyaml": "5.3"})
    assert any(f.cve == "CVE-2020-1747" for f in findings)


def test_starlette_range_flagged():
    findings = scan_requirements(["starlette==0.37.2"])
    assert any(f.cve == "CVE-2024-47874" for f in findings)


def test_requests_range_flagged():
    findings = scan_requirements(["requests==2.28.0"])
    assert any(f.cve == "CVE-2023-32681" for f in findings)
    fixed = scan_requirements(["requests==2.32.0"])
    assert [f for f in fixed if f.kind == "advisory"] == []


def test_unpinned_flagged():
    findings = scan_requirements(["numpy"])
    assert any(f.kind == "unpinned" and f.package == "numpy"
               for f in findings)


def test_no_upper_bound_flagged():
    findings = scan_requirements(["numpy>=1.24"])
    assert any(f.kind == "no_upper_bound" for f in findings)
    exact = scan_requirements(["numpy==1.26.4"])
    assert [f for f in exact if f.kind in ("no_upper_bound", "unpinned")] == []


def test_url_dependency_flagged():
    findings = scan_requirements(
        ["mypkg @ git+https://example.com/mypkg.git"])
    assert any(f.kind == "url_dependency" for f in findings)


def test_empty_input_no_findings():
    assert scan_requirements([]) == []
    assert scan_requirements(["# just a comment", ""]) == []


def test_matches_spec_operators():
    assert matches_spec("1.2.3", ">=1.0.0,<2.0.0")
    assert not matches_spec("2.0.0", ">=1.0.0,<2.0.0")
    assert matches_spec("1.26.17", "==1.26.17")
    assert not matches_spec("1.26.16", "==1.26.17")
    assert matches_spec("2.0.5", ">=2.0.0,<2.0.5") is False
    with pytest.raises(ValueError, match="unsupported"):
        matches_spec("1.0", "~~~1.0")


def test_parse_requirement_shapes():
    assert parse_requirement("numpy>=1.24")["name"] == "numpy"
    assert parse_requirement("scikit_learn==1.3")["name"] == "scikit-learn"
    assert parse_requirement("  # comment") == {}
    assert parse_requirement("pkg @ https://x/y.tar.gz")["url"] != ""


def test_scan_own_project_runs():
    findings = scan_project(".")
    # Our own manifest: floors are modern; unbounded floors are noted.
    advisory = [f for f in findings if f.kind == "advisory"]
    assert advisory == [], [f.to_dict() for f in advisory]
    assert isinstance(render_report(findings), str)
    assert "Findings:" in render_report(findings)


def test_report_sorts_by_severity():
    findings = scan_requirements(["pyyaml==5.3", "numpy"])
    report = render_report(findings)
    assert report.index("critical") < report.index("unpinned")
