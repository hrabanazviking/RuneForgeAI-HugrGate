"""Slice 025 — foundation release gate.

The campaign's Definition of Done, as executable checks: version
truth, changelog currency, per-slice evidence, and a benchmark smoke
proving the hardened core still decides correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib

pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "campaign-i"

EXPECTED_SLICE_DOCS = {
    "001-repository-truth-audit.md",
    "architecture-map.md",  # slice 002
    "003-public-api-inventory.md",
    "004-dependency-graph-audit.md",
    "005-dead-code-elimination.md",
    "006-type-system-hardening.md",
    "007-exception-taxonomy.md",
    "008-configuration-normalization.md",
    "009-logging-architecture.md",
    "010-determinism-audit.md",
    "011-state-validation-hardening.md",
    "012-result-invariant-hardening.md",
    "013-policy-invariant-hardening.md",
    "014-backend-registry-hardening.md",
    "015-provenance-integrity.md",
    "016-serialization-contracts.md",
    "017-thread-safety-baseline.md",
    "018-async-readiness-audit.md",
    "019-resource-lifecycle-management.md",
    "020-package-boundary-cleanup.md",
    "021-import-cycle-elimination.md",
    "022-static-analysis-gate.md",
    "023-test-taxonomy-rebuild.md",
    "024-coverage-gap-attack.md",
    "025-foundation-release-gate.md",
}


def test_package_version_matches_pyproject():
    import hugrgate
    with open(ROOT / "pyproject.toml", "rb") as fh:
        declared = tomllib.load(fh)["project"]["version"]
    assert hugrgate.__version__ == declared


def test_changelog_records_the_campaign():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Gjallarbrú Campaign I" in text
    assert "533 tests green" in text


def test_every_slice_has_its_evidence_doc():
    missing = sorted(
        name for name in EXPECTED_SLICE_DOCS if not (DOCS / name).exists())
    assert not missing, f"missing slice docs: {missing}"


def test_slice_docs_are_non_trivial():
    thin = [name for name in EXPECTED_SLICE_DOCS
            if len((DOCS / name).read_text(encoding="utf-8")) < 400]
    assert not thin, f"thin slice docs: {thin}"


def test_completion_report_exists():
    report = DOCS / "CAMPAIGN-I-COMPLETION-REPORT.md"
    assert report.exists(), "campaign completion report missing"
    text = report.read_text(encoding="utf-8")
    assert "533" in text


def test_benchmark_smoke_after_hardening():
    """The hardened core still benchmarks: accuracy sane, no crashes."""
    from hugrgate import DecisionPolicy, HugrGate
    from hugrgate.backends.rules import Rule, RuleBackend
    from hugrgate.bench import run_benchmark

    gate = HugrGate()
    gate.register(RuleBackend([
        Rule(condition={"field": "temperature", "gt": 90}, then="escalate",
             confidence=0.95, priority=10),
        Rule(condition=None, then="ignore", confidence=0.9),
    ], name="triage"))
    items = [
        {"id": f"hot-{i}", "state": {"temperature": 95 + (i % 5)},
         "expected": "escalate"}
        for i in range(50)
    ] + [
        {"id": f"cold-{i}", "state": {"temperature": 50 + (i % 5)},
         "expected": "ignore"}
        for i in range(50)
    ]
    dataset = {
        "name": "smoke", "version": "test",
        "spec": {"type": "categorical",
                 "options": ["ignore", "watch", "escalate"]},
        "items": items,
    }
    report = run_benchmark(dataset, gate, backends=["triage"],
                           policy=DecisionPolicy(minimum_probability=0.0))
    backend_report = report["backends"]["triage"]
    assert report["n_items"] == 100
    assert backend_report["accuracy"] >= 0.9, backend_report
