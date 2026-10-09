"""Security Forge — Gjallarbrú Campaign XVII (slices 401-425).

Adversarial robustness for a runtime that faces hostile inputs,
models, plugins, and networks. Built *on top of* the existing
defenses — privacy fortress (redaction, tokenization, sealed crypto),
secret detection, hash-chained audit logs, cluster mutual auth —
hardening what exists instead of duplicating it:

- :mod:`hugrgate.security.threat_model` — STRIDE threat model v2
  with coverage analysis (slice 401).
- :mod:`hugrgate.security.attack_surface` — enumerated, audited
  attack surface (slice 402).
- :mod:`hugrgate.security.depscan` — dependency security scanning
  (slice 403).
- :mod:`hugrgate.security.supply_chain` — supply-chain policy +
  SBOM (slice 404).
- :mod:`hugrgate.security.model_signing` — signed model metadata
  (slice 405).
- :mod:`hugrgate.security.checksums` — model checksum enforcement
  (slice 406).
- :mod:`hugrgate.security.plugins` — plugin trust model (slice 407).
- :mod:`hugrgate.security.sandbox` — backend sandbox boundary
  (slice 408).
- :mod:`hugrgate.security.input_limits` — input-size limits
  (slice 409).
- :mod:`hugrgate.security.resource_guards` — resource-exhaustion
  guards (slice 410).
- :mod:`hugrgate.security.serde_guards` — deserialization hardening
  (slice 411).
- :mod:`hugrgate.security.path_guards` — path traversal defenses
  (slice 412).
- :mod:`hugrgate.security.injection_corpus` — injection test corpus
  (slice 413).
- :mod:`hugrgate.security.prompt_injection` — prompt-injection
  boundary (slice 414).
- :mod:`hugrgate.security.malicious_backend` — malicious-backend
  adversarial fixtures (slice 415).
- :mod:`hugrgate.security.provenance_guards` — provenance tamper
  detection + tip sealing (slice 416).
- :mod:`hugrgate.security.cache_poisoning` — cache-poisoning
  defenses (slice 417).
- :mod:`hugrgate.security.replay` — replay attack defenses
  (slice 418).
- :mod:`hugrgate.security.authz` — service authorization policy
  (slice 419).
- :mod:`hugrgate.security.rate_limit` — rate limiting (slice 420).
- :mod:`hugrgate.security.secret_audit` — secret-handling audit
  (slice 421).
- :mod:`hugrgate.security.fuzzing` — deterministic fuzzing campaign
  harness (slice 422).
- :mod:`hugrgate.security.gauntlet` — independent-style security
  gauntlet (slice 424).
"""

from __future__ import annotations

from hugrgate.security.attack_surface import (
    AttackSurface,
    SurfaceEntry,
    curated_surface,
    enumerate_surface,
    find_unlisted,
)
from hugrgate.security.checksums import (
    ChecksumManifest,
    ModelChecksumGate,
    build_manifest,
    enforce_manifest,
    verified_open,
    verify_manifest,
)
from hugrgate.security.depscan import (
    ADVISORIES,
    Advisory,
    scan_project,
    scan_requirements,
)
from hugrgate.security.depscan import (
    Finding as DependencyFinding,
)
from hugrgate.security.model_signing import (
    ModelSigner,
    SignedMetadata,
    TrustedModelStore,
)
from hugrgate.security.supply_chain import (
    DependencyRecord,
    SupplyChainPolicy,
    SupplyVerdict,
    generate_sbom,
    sbom_from_installed,
)
from hugrgate.security.threat_model import (
    STRIDE,
    Asset,
    Threat,
    ThreatModel,
    TrustBoundary,
    default_threat_model,
)

__all__ = [
    "ADVISORIES",
    "STRIDE",
    "Advisory",
    "Asset",
    "AttackSurface",
    "ChecksumManifest",
    "DependencyFinding",
    "DependencyRecord",
    "ModelChecksumGate",
    "ModelSigner",
    "SignedMetadata",
    "SupplyChainPolicy",
    "SupplyVerdict",
    "SurfaceEntry",
    "Threat",
    "ThreatModel",
    "TrustBoundary",
    "TrustedModelStore",
    "build_manifest",
    "curated_surface",
    "default_threat_model",
    "enforce_manifest",
    "enumerate_surface",
    "find_unlisted",
    "generate_sbom",
    "sbom_from_installed",
    "scan_project",
    "scan_requirements",
    "verified_open",
    "verify_manifest",
]
