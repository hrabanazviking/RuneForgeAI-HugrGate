"""Slice 404 — supply-chain policy.

Policy (*what is allowed*) on top of the scanner (slice 403: *known
bad*): index allowlisting, hash requirements, license allowlisting,
and a blocklist, with CycloneDX-style SBOM generation.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import HugrGateError, SupplyChainViolation
from hugrgate.security.supply_chain import (
    STRICT_POLICY,
    DependencyRecord,
    SupplyChainPolicy,
    generate_sbom,
    sbom_from_installed,
)


def _rec(**kw):
    base = {"name": "numpy", "version": "1.26.4"}
    base.update(kw)
    return DependencyRecord(**base)


def test_clean_record_allowed():
    policy = SupplyChainPolicy()
    verdict = policy.evaluate(_rec())
    assert verdict.allowed
    assert verdict.reasons == ()
    assert bool(verdict)


def test_blocklisted_package_denied():
    policy = SupplyChainPolicy(blocked_packages=frozenset({"evilpkg"}))
    verdict = policy.evaluate(_rec(name="evilpkg", version="1.0"))
    assert not verdict.allowed
    assert any("blocklist" in r for r in verdict.reasons)


def test_unknown_index_denied():
    policy = SupplyChainPolicy()
    verdict = policy.evaluate(
        _rec(index_url="https://evil.example.com/simple"))
    assert not verdict.allowed
    assert any("not an approved index" in r for r in verdict.reasons)


def test_missing_hashes_denied_when_required():
    policy = SupplyChainPolicy(require_hashes=True)
    assert not policy.evaluate(_rec()).allowed
    ok = policy.evaluate(_rec(hashes=("sha256:abc123",)))
    assert ok.allowed


def test_disallowed_license_denied():
    policy = SupplyChainPolicy(allowed_licenses=frozenset({"MIT"}))
    assert not policy.evaluate(_rec(license="GPL-3.0")).allowed
    assert policy.evaluate(_rec(license="MIT")).allowed


def test_enforce_raises_taxonomy_error():
    policy = SupplyChainPolicy(blocked_packages=frozenset({"evilpkg"}))
    with pytest.raises(SupplyChainViolation) as exc:
        policy.enforce(_rec(name="evilpkg", version="1.0"))
    assert exc.value.code == "supply_chain_violation"
    assert exc.value.recoverable is False
    assert exc.value.details["package"] == "evilpkg"


def test_enforce_passes_clean_record():
    SupplyChainPolicy().enforce(_rec())  # no raise


def test_audit_reports_all_denied():
    policy = SupplyChainPolicy(blocked_packages=frozenset({"evilpkg"}))
    report = policy.audit([_rec(), _rec(name="evilpkg", version="1.0")])
    assert report["allowed"] is False
    assert report["denied"] == ["evilpkg"]
    assert report["records"] == 2
    assert "evilpkg" in report["reasons"]


def test_sbom_structure():
    policy = SupplyChainPolicy(require_hashes=True)
    sbom = generate_sbom(
        [_rec(hashes=("sha256:abc123",)), _rec(name="pyyaml",
                                               version="6.0.1")],
        policy)
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert len(sbom["components"]) == 2
    hashed = sbom["components"][0]
    assert hashed["hashes"] == [{"alg": "SHA256", "content": "abc123"}]
    assert hashed["policyVerdict"]["allowed"] is True
    unhashed = sbom["components"][1]
    assert unhashed["policyVerdict"]["allowed"] is False


def test_sbom_from_installed_is_real():
    sbom = sbom_from_installed()
    names = {c["name"].lower().replace("_", "-")
             for c in sbom["components"]}
    assert "pyyaml" in names  # base dependency, really installed
    assert all(c["version"] for c in sbom["components"])


def test_strict_policy_blocks_unhashed():
    assert not STRICT_POLICY.evaluate(_rec()).allowed


def test_error_round_trips_wire_format():
    err = SupplyChainViolation("denied", package="x")
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert isinstance(rebuilt, SupplyChainViolation)
    assert rebuilt.code == "supply_chain_violation"
