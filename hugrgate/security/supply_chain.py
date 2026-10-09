"""Supply-chain policy. Slice 404.

Complements the dependency scanner (slice 403: *known* bad) with
*policy* (what is *allowed* at all):

- :class:`SupplyChainPolicy` — approved package indexes, hash
  requirements, license allowlist, package blocklist.
- :meth:`SupplyChainPolicy.evaluate` — per-dependency verdict with
  reasons; :meth:`SupplyChainPolicy.enforce` raises
  :class:`SupplyChainViolation` on denial.
- :func:`generate_sbom` — CycloneDX-style software bill of
  materials for a set of dependency records.
- :func:`sbom_from_installed` — a real SBOM of the current
  environment via :mod:`importlib.metadata`.

The policy is deny-by-default on the dimensions it constrains:
unknown index, missing hashes (when required), disallowed license,
or blocklisted package each deny independently with a named reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Any

from hugrgate.errors import SupplyChainViolation

__all__ = [
    "DependencyRecord",
    "SupplyChainPolicy",
    "SupplyVerdict",
    "generate_sbom",
    "sbom_from_installed",
]

#: Default trusted index.
PYPI_SIMPLE = "https://pypi.org/simple"


@dataclass(frozen=True)
class DependencyRecord:
    """One resolved dependency awaiting a policy verdict."""

    name: str
    version: str
    index_url: str = PYPI_SIMPLE
    license: str = "UNKNOWN"
    hashes: tuple[str, ...] = ()
    origin: str = "direct"  # direct | transitive


@dataclass(frozen=True)
class SupplyVerdict:
    allowed: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class SupplyChainPolicy:
    """What the supply chain is allowed to look like."""

    allowed_indexes: tuple[str, ...] = (PYPI_SIMPLE,)
    require_hashes: bool = False
    allowed_licenses: frozenset[str] | None = None
    blocked_packages: frozenset[str] = frozenset()

    def evaluate(self, record: DependencyRecord) -> SupplyVerdict:
        reasons: list[str] = []
        name = record.name.lower().replace("_", "-")
        if name in {b.lower().replace("_", "-")
                    for b in self.blocked_packages}:
            reasons.append(f"package {record.name} is blocklisted")
        if not any(record.index_url.startswith(prefix)
                   for prefix in self.allowed_indexes):
            reasons.append(
                f"index {record.index_url} is not an approved index")
        if self.require_hashes and not record.hashes:
            reasons.append(
                f"{record.name}=={record.version} carries no hashes; "
                "hash-pinned installs required")
        if self.allowed_licenses is not None and \
                record.license not in self.allowed_licenses:
            reasons.append(
                f"license {record.license!r} is not allowlisted for "
                f"{record.name}")
        return SupplyVerdict(allowed=not reasons, reasons=tuple(reasons))

    def enforce(self, record: DependencyRecord) -> None:
        """Raise :class:`SupplyChainViolation` unless allowed."""
        verdict = self.evaluate(record)
        if not verdict:
            raise SupplyChainViolation(
                f"supply-chain policy denies {record.name}=={record.version}",
                package=record.name, version=record.version,
                reasons=list(verdict.reasons))

    def audit(self, records: list[DependencyRecord]) -> dict[str, Any]:
        """Verdict for a whole resolved set, with per-package detail."""
        detail = {r.name: self.evaluate(r) for r in records}
        denied = sorted(n for n, v in detail.items() if not v)
        return {
            "allowed": not denied,
            "denied": denied,
            "records": len(records),
            "reasons": {n: list(detail[n].reasons) for n in denied},
        }


def generate_sbom(records: list[DependencyRecord],
                  policy: SupplyChainPolicy | None = None) -> dict[str, Any]:
    """CycloneDX-style SBOM for the given dependency records."""
    components = []
    for record in records:
        component: dict[str, Any] = {
            "type": "library",
            "name": record.name,
            "version": record.version,
            "scope": "required" if record.origin == "direct"
            else "optional",
            "licenses": [{"license": {"id": record.license}}],
            "externalReferences": [{
                "type": "distribution",
                "url": record.index_url,
            }],
        }
        if record.hashes:
            component["hashes"] = [
                {"alg": h.split(":")[0].upper(), "content": h.split(":", 1)[1]}
                if ":" in h else {"alg": "SHA-256", "content": h}
                for h in record.hashes
            ]
        if policy is not None:
            verdict = policy.evaluate(record)
            component["policyVerdict"] = {
                "allowed": verdict.allowed,
                "reasons": list(verdict.reasons),
            }
        components.append(component)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "hugrgate"},
        },
        "components": components,
    }


def sbom_from_installed(
    policy: SupplyChainPolicy | None = None,
) -> dict[str, Any]:
    """Build an SBOM from actually-installed distributions."""
    records = []
    for dist in metadata.distributions():
        name = dist.metadata["Name"] or "unknown"
        license_id = (dist.metadata["License"] or "UNKNOWN").strip() or "UNKNOWN"
        records.append(DependencyRecord(
            name=name, version=dist.version, license=license_id,
            origin="direct"))
    records.sort(key=lambda r: r.name.lower())
    return generate_sbom(records, policy)


#: A strict default: hashes required, permissive licenses only.
STRICT_POLICY = SupplyChainPolicy(
    require_hashes=True,
    allowed_licenses=frozenset({
        "MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC",
        "PSF-2.0", "Python-2.0",
    }),
)
