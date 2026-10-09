"""Slice 250 — Privacy Fortress release gate.

Meta-test for Campaign X (slices 226-250): asserts every slice's
artifacts exist and cohere — modules import, docs exist,
taxonomy rows list the test modules, the CHANGELOG covers all
25 slices, the six campaign errors are registered, and the
fortress still holds end to end (exfil suite, audit chain,
sealed round-trip, dry-run).
"""

from __future__ import annotations

import importlib
import json
import re
import secrets
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parent.parent
DOCS_X = ROOT / "docs" / "campaign-x"

#: slice -> importable module (247 is tests-only, 249 is benchmarks).
SLICE_MODULES = {
    226: "hugrgate.privacy",
    227: "hugrgate.privacy_labels",
    228: "hugrgate.privacy_flow",
    229: "hugrgate.privacy_trust",
    230: "hugrgate.privacy_jurisdiction",
    231: "hugrgate.privacy_localonly",
    232: "hugrgate.privacy_redact",
    233: "hugrgate.privacy_tokens",
    234: "hugrgate.privacy_secrets",
    235: "hugrgate.privacy_pii",
    236: "hugrgate.privacy_minimize",
    237: "hugrgate.privacy_payload",
    238: "hugrgate.privacy_provenance",
    239: "hugrgate.privacy_retention",
    240: "hugrgate.privacy_deletion",
    241: "hugrgate.privacy_crypto",
    242: "hugrgate.privacy_provenance",  # SealedProvenanceStore lives here
    243: "hugrgate.privacy_keys",
    244: "hugrgate.privacy_audit",
    245: "hugrgate.privacy_dryrun",
    246: "hugrgate.privacy_explain",
    248: "hugrgate.privacy_exfil",
}

EXPECTED_ERRORS = {
    "DataFlowDenied": "data_flow_denied",
    "JurisdictionViolation": "jurisdiction_violation",
    "LocalOnlyViolation": "local_only_violation",
    "SecretDetected": "secret_detected",
    "SealError": "seal_error",
    "KeyProviderError": "key_provider_error",
}

TEST_MODULES = [
    "test_privacy_audit", "test_privacy_bench_249",
    "test_privacy_classification", "test_privacy_crypto",
    "test_privacy_deletion", "test_privacy_dryrun", "test_privacy_exfil",
    "test_privacy_explain", "test_privacy_flow", "test_privacy_fuzz",
    "test_privacy_jurisdiction", "test_privacy_keys", "test_privacy_labels",
    "test_privacy_localonly", "test_privacy_minimize", "test_privacy_payload",
    "test_privacy_pii", "test_privacy_provenance", "test_privacy_redact",
    "test_privacy_retention", "test_privacy_sealed", "test_privacy_secrets",
    "test_privacy_tokens", "test_privacy_trust",
    "test_privacy_fortress_gate",
]


def test_all_slice_modules_import():
    for _slice_no, module in SLICE_MODULES.items():
        importlib.import_module(module)  # raises on failure
    assert len(SLICE_MODULES) == 22


def test_slice_242_sealed_store_exists():
    from hugrgate.privacy_provenance import SealedProvenanceStore
    assert SealedProvenanceStore is not None


def test_slice_226_classification_ladder():
    from hugrgate.policy import DecisionPolicy
    from hugrgate.privacy import semantics_for
    assert "forbidden" in DecisionPolicy.PRIVACY_CLASSES
    assert semantics_for("forbidden")["remote_eligible"] is False
    assert semantics_for("strict")["cacheable"] is False


def test_all_slice_docs_exist():
    for slice_no in range(226, 251):
        matches = list(DOCS_X.glob(f"{slice_no}-*.md"))
        assert len(matches) == 1, \
            f"slice {slice_no}: expected 1 doc, found {len(matches)}"


def test_fuzz_and_bench_artifacts_exist():
    assert (ROOT / "tests" / "test_privacy_fuzz.py").exists()
    assert (ROOT / "benchmarks" / "privacy_bench_249.py").exists()
    artifact = json.loads(
        (ROOT / "benchmarks" / "privacy_bench_249.json").read_text())
    assert artifact["name"] == "privacy_bench_249"
    assert len(artifact["results"]) == 10


def test_taxonomy_lists_all_test_modules():
    doc = (ROOT / "docs" / "campaign-i"
           / "023-test-taxonomy-rebuild.md").read_text()
    for module in TEST_MODULES:
        assert module in doc, f"taxonomy missing {module}"


def test_changelog_covers_all_slices():
    changelog = (ROOT / "CHANGELOG.md").read_text()
    for slice_no in range(226, 251):
        assert re.search(rf"slice {slice_no}\b", changelog), \
            f"CHANGELOG missing slice {slice_no}"


def test_error_taxonomy_registered():
    import hugrgate.errors as errors
    for name, code in EXPECTED_ERRORS.items():
        cls = getattr(errors, name)
        assert cls.code == code, f"{name} code"
        assert cls.recoverable is False, f"{name} recoverable"
        assert name in errors.__all__, f"{name} in __all__"


def test_exfil_suite_holds():
    from hugrgate.privacy_exfil import ExfilSimulator
    report = ExfilSimulator().run_suite()
    assert report.passed, \
        f"holes: {[o.name for o in report.failures]}"


def test_audit_chain_smoke():
    from hugrgate.privacy_audit import PrivacyAuditLog
    log = PrivacyAuditLog()
    log.record("backend_blocked", backend="x")
    assert log.verify() is True


def test_sealed_round_trip_smoke():
    from hugrgate.privacy_crypto import SealedBox
    key = secrets.token_bytes(32)
    assert SealedBox.open(key, SealedBox.seal(key, b"fortress")) \
        == b"fortress"


def test_dry_run_smoke():
    from hugrgate.policy import DecisionPolicy
    from hugrgate.privacy import PrivacyGuard
    from hugrgate.privacy_dryrun import PrivacyDryRun

    class _Local:
        name = "local"
        is_remote = False

    report = PrivacyDryRun(PrivacyGuard()).evaluate(
        {"q": "hi"}, backend=_Local(),
        policy=DecisionPolicy(privacy_class="standard"))
    assert report.allowed is True


def test_no_third_party_crypto():
    # The fortress is stdlib-only: no new third-party imports.
    import ast
    stdlib = {"__future__", "base64", "binascii", "hashlib", "hmac",
              "secrets", "os", "time", "json", "copy", "stat", "pickle",
              "warnings", "pathlib", "dataclasses", "abc", "typing",
              "collections", "enum", "math", "re"}
    for module in set(SLICE_MODULES.values()):
        path = (ROOT / module.replace(".", "/")).with_suffix(".py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                assert name in stdlib or name.startswith("hugrgate"), \
                    f"{module} imports non-stdlib {name}"
