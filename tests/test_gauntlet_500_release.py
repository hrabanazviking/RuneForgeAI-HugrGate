"""Slice 500 — HugrGate 1.0 release decision checklist.

The release decision as executable gates: version is 1.0
everywhere, every Campaign XX slice left its doc, the taxonomy
covers the new test modules, and the precision-audit handoff
verifies complete. The full suite (run separately) is the final
gate.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import hugrgate

REPO = Path(__file__).resolve().parent.parent
SLICES = list(range(476, 501))
NEW_TEST_MODULES = [
    "test_gauntlet_492_exhaustion",
    "test_gauntlet_493_leakscan",
    "test_gauntlet_494_calibration_audit",
    "test_gauntlet_495_repro",
    "test_gauntlet_496_docsaudit",
    "test_gauntlet_497_license",
    "test_gauntlet_498_rcbuild",
    "test_gauntlet_499_handoff",
    "test_gauntlet_500_release",
]


def test_version_is_1_0():
    assert hugrgate.__version__ == "1.0.0"
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert match is not None
    assert match.group(1) == "1.0.0"
    assert match.group(1) == hugrgate.__version__


def test_slice_docs_complete():
    docs = REPO / "docs" / "gauntlet"
    missing = [n for n in SLICES
               if not list(docs.glob(f"{n}-*.md"))]
    assert not missing, f"missing slice docs: {missing}"


def test_taxonomy_covers_new_modules():
    taxonomy = (REPO / "docs" / "campaign-i"
                / "023-test-taxonomy-rebuild.md").read_text(encoding="utf-8")
    missing = [m for m in NEW_TEST_MODULES if m not in taxonomy]
    assert not missing, f"not in taxonomy: {missing}"


def test_handoff_complete():
    spec = importlib.util.spec_from_file_location(
        "precision_handoff_check",
        REPO / "tools" / "precision_handoff_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["precision_handoff_check"] = module
    spec.loader.exec_module(module)
    report = module.check_handoff(
        REPO / "docs/gauntlet/499-audit-handoff.json", REPO)
    assert report.complete, report.problems


def test_api_inventory_doc_exists_and_current():
    doc = REPO / "docs/campaign-i/003-public-api-inventory.md"
    assert doc.exists()
    # Freshness itself is gated by test_inventory_doc_is_fresh in the
    # full suite; here we assert the campaign's additions landed.
    text = doc.read_text(encoding="utf-8")
    for module in ("hugrgate.gauntlet.exhaustion",
                   "hugrgate.gauntlet.leakscan",
                   "hugrgate.gauntlet.calibration_audit",
                   "hugrgate.gauntlet.repro",
                   "hugrgate.gauntlet.license_audit"):
        assert module in text, f"{module} missing from inventory"
