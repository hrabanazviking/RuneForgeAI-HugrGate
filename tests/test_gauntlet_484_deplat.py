"""Slice 484 — dependency-latest matrix.

The minimum matrix (slice 483) pins the floor; this slice records
the *validated-latest* set — the actually installed versions that
the 1.0 release notes name — and scans the tree for
deprecated/removed dependency APIs (``yaml.load`` without a Loader,
``datetime.utcnow``, dead numpy aliases, ...). The tree is clean.
"""

from __future__ import annotations

import json
from pathlib import Path

from hugrgate.gauntlet.deps import (
    latest_audit,
    scan_deprecated_api,
)

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "gauntlet" / "484-dependency-latest-manifest.json"


def test_no_deprecated_api_in_tree():
    findings = scan_deprecated_api(ROOT / "hugrgate")
    assert findings == (), findings
    assert scan_deprecated_api(ROOT / "tools") == ()


def test_synthetic_yaml_load_flagged(tmp_path):
    (tmp_path / "x.py").write_text(
        "import yaml\nyaml.load(open('f'))\n", encoding="utf-8"
    )
    findings = scan_deprecated_api(tmp_path)
    assert len(findings) == 1
    assert "yaml.load" in findings[0][2]


def test_synthetic_utcnow_flagged(tmp_path):
    (tmp_path / "x.py").write_text(
        "import datetime\ndatetime.datetime.utcnow()\n", encoding="utf-8"
    )
    findings = scan_deprecated_api(tmp_path)
    assert len(findings) == 1
    assert "utcnow" in findings[0][2] or "deprecated" in findings[0][2]


def test_string_constant_patterns_not_flagged(tmp_path):
    # A detection corpus naming the API is not a use of the API.
    (tmp_path / "x.py").write_text(
        'PATTERNS = (r"\\byaml\\.load\\s*\\(", "dangerous")\n',
        encoding="utf-8",
    )
    assert scan_deprecated_api(tmp_path) == ()


def test_latest_audit_reports_real_versions():
    audit = latest_audit()
    assert "pyyaml" in audit
    info = audit["pyyaml"]
    assert info["installed"] is not None
    assert info["meets_floor"] is True


def test_manifest_matches_live_audit():
    assert MANIFEST.is_file()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["dependencies"] == latest_audit()
    assert manifest["deprecated_api_findings"] == []
