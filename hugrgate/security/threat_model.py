"""STRIDE threat model v2. Slice 401.

HugrGate already had scattered defenses (hash-chained provenance,
secret detection, sealed caches, cluster mutual auth) but no single
statement of *what is being defended against*. This module is that
statement, as executable data rather than a prose document that can
drift from the code:

- :class:`ThreatModel` — assets, trust boundaries, and threats with
  STRIDE categories, likelihood/impact scores, mitigations that name
  real capabilities, and residual-risk dispositions.
- :func:`default_threat_model` — the v2 model of this codebase.
- Coverage analysis (:meth:`ThreatModel.coverage_report`) — every
  threat must name at least one mitigation, one covering test
  module, or carry an explicit accepted-risk rationale; ``validate()``
  enforces that invariant, so the model cannot silently rot.

Risk is likelihood x impact on a 1-5 scale each (1-25). Residual
dispositions: ``"mitigated"`` (defense in place and tested),
``"partial"`` (defense reduces but does not eliminate),
``"accepted"`` (conscious risk acceptance with rationale — never
the default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "STRIDE",
    "Asset",
    "Threat",
    "ThreatModel",
    "TrustBoundary",
    "default_threat_model",
]

#: STRIDE threat categories.
STRIDE: tuple[str, ...] = (
    "spoofing",
    "tampering",
    "repudiation",
    "information_disclosure",
    "denial_of_service",
    "elevation_of_privilege",
)

_RESIDUALS = ("mitigated", "partial", "accepted")


@dataclass(frozen=True)
class Asset:
    """Something worth defending."""

    name: str
    description: str
    trust_boundary: str


@dataclass(frozen=True)
class TrustBoundary:
    """A line an attacker must cross."""

    name: str
    description: str
    enforced_by: str


@dataclass
class Threat:
    """One adversarial scenario, scored and dispositioned."""

    id: str
    title: str
    stride: str
    asset: str
    description: str
    likelihood: int  # 1..5
    impact: int  # 1..5
    mitigations: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    residual: str = "partial"
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.stride not in STRIDE:
            raise ValueError(f"unknown STRIDE category: {self.stride!r}")
        for attr in ("likelihood", "impact"):
            value = getattr(self, attr)
            if not isinstance(value, int) or not 1 <= value <= 5:
                raise ValueError(f"{attr} must be an int in 1..5, got {value!r}")
        if self.residual not in _RESIDUALS:
            raise ValueError(f"residual must be one of {_RESIDUALS}")

    @property
    def risk(self) -> int:
        """Likelihood x impact, 1..25."""
        return self.likelihood * self.impact

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "stride": self.stride,
            "asset": self.asset,
            "description": self.description,
            "likelihood": self.likelihood,
            "impact": self.impact,
            "risk": self.risk,
            "mitigations": list(self.mitigations),
            "tests": list(self.tests),
            "residual": self.residual,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Threat:
        payload = dict(data)
        payload.pop("risk", None)  # derived, not stored
        return cls(**payload)


@dataclass
class ThreatModel:
    """Assets, boundaries, and threats for one system version."""

    version: str
    assets: list[Asset] = field(default_factory=list)
    boundaries: list[TrustBoundary] = field(default_factory=list)
    threats: list[Threat] = field(default_factory=list)

    # -- analysis ------------------------------------------------------

    def unmitigated(self) -> list[Threat]:
        """Threats with no mitigation and no accepted-risk rationale."""
        return [
            t for t in self.threats
            if not t.mitigations and t.residual != "accepted"
        ]

    def accepted_risks(self) -> list[Threat]:
        return [t for t in self.threats if t.residual == "accepted"]

    def by_stride(self) -> dict[str, list[Threat]]:
        grouped: dict[str, list[Threat]] = {s: [] for s in STRIDE}
        for threat in self.threats:
            grouped[threat.stride].append(threat)
        return grouped

    def top_risks(self, n: int = 5) -> list[Threat]:
        return sorted(self.threats, key=lambda t: (-t.risk, t.id))[:n]

    def coverage_report(self) -> dict[str, Any]:
        by_stride = self.by_stride()
        return {
            "version": self.version,
            "threats": len(self.threats),
            "assets": len(self.assets),
            "boundaries": len(self.boundaries),
            "unmitigated": [t.id for t in self.unmitigated()],
            "accepted": [t.id for t in self.accepted_risks()],
            "by_stride": {s: len(ts) for s, ts in by_stride.items()},
            "max_residual_risk": max(
                (t.risk for t in self.threats
                 if t.residual != "mitigated"), default=0),
            "top_risks": [
                {"id": t.id, "title": t.title, "risk": t.risk,
                 "residual": t.residual}
                for t in self.top_risks()
            ],
        }

    def validate(self) -> None:
        """Enforce model hygiene; raises ValueError on drift."""
        problems: list[str] = []
        asset_names = {a.name for a in self.assets}
        boundary_names = {b.name for b in self.boundaries}
        seen: set[str] = set()
        for threat in self.threats:
            if threat.id in seen:
                problems.append(f"duplicate threat id {threat.id}")
            seen.add(threat.id)
            if threat.asset not in asset_names:
                problems.append(
                    f"{threat.id}: unknown asset {threat.asset!r}")
            if not threat.mitigations and threat.residual != "accepted":
                problems.append(
                    f"{threat.id}: no mitigations and residual "
                    f"is {threat.residual!r} (must be 'accepted' with rationale)")
            if threat.residual == "accepted" and not threat.rationale:
                problems.append(
                    f"{threat.id}: accepted risk needs a rationale")
            for mitigation in threat.mitigations:
                if not mitigation.strip():
                    problems.append(f"{threat.id}: empty mitigation string")
        for stride in STRIDE:
            if not self.by_stride()[stride]:
                problems.append(f"STRIDE category {stride!r} has no threats")
        for asset in self.assets:
            if asset.trust_boundary not in boundary_names:
                problems.append(
                    f"asset {asset.name}: unknown boundary "
                    f"{asset.trust_boundary!r}")
        if problems:
            raise ValueError(
                "threat model invalid:\n- " + "\n- ".join(problems))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "assets": [a.__dict__ for a in self.assets],
            "boundaries": [b.__dict__ for b in self.boundaries],
            "threats": [t.to_dict() for t in self.threats],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThreatModel:
        return cls(
            version=data["version"],
            assets=[Asset(**a) for a in data.get("assets", [])],
            boundaries=[TrustBoundary(**b)
                        for b in data.get("boundaries", [])],
            threats=[Threat.from_dict(t) for t in data.get("threats", [])],
        )


def default_threat_model() -> ThreatModel:
    """Threat model v2 for the HugrGate codebase as it stands.

    Every mitigation names a real, implemented capability (slice
    numbers where they exist); every ``tests`` entry names the test
    module that exercises the defense. Threats without a real
    defense carry an explicit accepted-risk rationale instead of a
    wish.
    """
    model = ThreatModel(version="v2")
    model.assets.extend([
        Asset("decision_inputs", "User-supplied decision state payloads",
              "process"),
        Asset("model_artifacts", "Model files, packs, and metadata loaded "
              "from disk or network", "model_ingest"),
        Asset("decision_cache", "Cached decisions, some sealed at rest",
              "process"),
        Asset("provenance_chain", "Hash-chained decision audit trail",
              "process"),
        Asset("secrets", "API keys, tokens, key material in memory and "
              "transit", "process"),
        Asset("cluster_traffic", "Inter-node RPC envelopes", "cluster_net"),
        Asset("service_api", "HTTP service endpoints and CLI", "service_edge"),
        Asset("plugin_code", "Third-party backend/plugin code loaded at "
              "runtime", "plugin_loader"),
    ])
    model.boundaries.extend([
        TrustBoundary("process", "OS process boundary",
                      "OS user separation; no HugrGate sandbox by default"),
        TrustBoundary("service_edge", "HTTP/CLI ingress",
                      "input validation, size limits, authn/authz"),
        TrustBoundary("cluster_net", "Inter-node network",
                      "mutual HMAC auth (slice 208), TLS via operator"),
        TrustBoundary("model_ingest", "Model file / metadata loading",
                      "checksum + signature enforcement (slices 405-406)"),
        TrustBoundary("plugin_loader", "Third-party code loading",
                      "plugin trust model (slice 407), sandbox (slice 408)"),
    ])
    t = model.threats.append
    t(Threat("T-01", "Malicious model file executes code on load",
             "elevation_of_privilege", "model_artifacts",
             "A crafted model/pack file triggers code execution via unsafe "
             "deserialization or parser bugs during load.",
             3, 5,
             mitigations=["deserialization hardening: SafeUnpickler + opcode "
                          "scanner (slice 411)",
                          "checksum enforcement on model files (slice 406)",
                          "signed model metadata (slice 405)"],
             tests=["test_sec_406_checksums", "test_sec_411_serde_guards"]))
    t(Threat("T-02", "Tampered model metadata misroutes decisions",
             "tampering", "model_artifacts",
             "Unsigned metadata edited to change model identity, version, "
             "or capability claims; the gate trusts stale/false claims.",
             3, 4,
             mitigations=["HMAC-signed model metadata, verify-before-trust "
                          "(slice 405)"],
             tests=["test_sec_405_model_signing"]))
    t(Threat("T-03", "Prompt injection steers an LLM backend",
             "elevation_of_privilege", "decision_inputs",
             "Untrusted tool output or state text contains instructions "
             "that an LLM backend obeys over the system prompt.",
             4, 4,
             mitigations=["instruction/data boundary: delimited untrusted "
                          "content (slice 414)",
                          "override-attempt detector on backend inputs "
                          "(slice 414)"],
             tests=["test_sec_414_prompt_injection"]))
    t(Threat("T-04", "Oversized input exhausts memory/CPU",
             "denial_of_service", "service_api",
             "Giant state payloads, deep nesting, or huge batches cause "
             "OOM or CPU starvation before validation completes.",
             4, 4,
             mitigations=["validate_state size/depth caps (slice 011)",
                          "InputLimits policy with per-key quotas "
                          "(slice 409)",
                          "resource budgets: RLIMIT_AS/CPU (slice 410)"],
             tests=["test_sec_409_input_limits",
                    "test_sec_410_resource_guards"]))
    t(Threat("T-05", "Cache poisoning serves attacker-chosen decisions",
             "tampering", "decision_cache",
             "Crafted state collides with a victim's cache key, or a "
             "stale entry survives a model update and is served as fresh.",
             3, 4,
             mitigations=["cache key binds spec+policy+model version "
                          "(slice 258 integrity snapshot)",
                          "tenant namespace isolation (slice 417)",
                          "model-version invalidation (slice 417)"],
             tests=["test_sec_417_cache_poisoning"]))
    t(Threat("T-06", "Provenance chain tampering hides an action",
             "repudiation", "provenance_chain",
             "An insider edits or truncates the hash-chained audit log to "
             "erase evidence of a decision.",
             2, 5,
             mitigations=["hash-chained records, verify_chain (slice 015)",
                          "signed chain tips detect truncation (slice 416)"],
             tests=["test_sec_416_provenance_tamper"]))
    t(Threat("T-07", "Secrets leak into logs, errors, or telemetry",
             "information_disclosure", "secrets",
             "API keys or tokens embedded in state end up in log lines, "
             "error details, or exported telemetry.",
             4, 5,
             mitigations=["secret detection on outbound data (slice 234)",
                          "redaction pipeline (privacy fortress)",
                          "secret-handling audit gate (slice 421)"],
             tests=["test_sec_421_secret_audit"]))
    t(Threat("T-08", "Replayed cluster RPC re-executes a decision",
             "spoofing", "cluster_traffic",
             "A captured authenticated envelope is re-fired to repeat a "
             "privileged cluster operation.",
             2, 4,
             mitigations=["per-sender sequence window rejects replays "
                          "(slice 208)",
                          "nonce+timestamp replay guard (slice 418)"],
             tests=["test_sec_418_replay"]))
    t(Threat("T-09", "Dependency confusion / compromised package",
             "tampering", "model_artifacts",
             "A malicious or typosquatted package enters via an "
             "unconstrained index or unpinned requirement.",
             2, 5,
             mitigations=["supply-chain policy: pinned deps, allowed "
                          "indexes, license allowlist (slice 404)",
                          "dependency CVE scan (slice 403)"],
             tests=["test_sec_403_depscan", "test_sec_404_supply_chain"]))
    t(Threat("T-10", "Path traversal in pack/model file loading",
             "tampering", "model_artifacts",
             "A crafted pack manifest or model path escapes the intended "
             "directory and reads/writes arbitrary files.",
             3, 4,
             mitigations=["safe_join: resolve + jail all user paths "
                          "(slice 412)"],
             tests=["test_sec_412_path_guards"]))
    t(Threat("T-11", "Malicious backend exfiltrates or hangs",
             "elevation_of_privilege", "plugin_code",
             "A registered backend opens sockets, writes files, or blocks "
             "forever during evaluate().",
             3, 4,
             mitigations=["sandbox boundary: audit-hook denies subprocess/"
                          "socket (slice 408)",
                          "timeout + bulkhead isolation (slices 021/chaos)",
                          "malicious-backend gauntlet fixtures (slice 415)"],
             tests=["test_sec_408_sandbox", "test_sec_415_malicious_backend"]))
    t(Threat("T-12", "Unauthenticated service access",
             "spoofing", "service_api",
             "The HTTP service exposes decide/configure endpoints without "
             "authentication or authorization checks.",
             3, 4,
             mitigations=["service AuthZ policy: roles + capabilities "
                          "(slice 419)",
                          "cluster mutual auth for node traffic (slice 208)"],
             tests=["test_sec_419_authz"],
             residual="partial",
             rationale="AuthZ policy ships deny-by-default; deployment "
                       "wiring (TLS termination, key distribution) remains "
                       "operator responsibility."))
    t(Threat("T-13", "Credential-less rate exhaustion (DoS)",
             "denial_of_service", "service_api",
             "An unauthenticated client floods /decide and starves "
             "legitimate users.",
             4, 3,
             mitigations=["per-key token-bucket rate limiting (slice 420)",
                          "backpressure + bulkheads (slices 289/chaos)"],
             tests=["test_sec_420_rate_limit"]))
    t(Threat("T-14", "Log injection forges audit entries",
             "spoofing", "provenance_chain",
             "Newlines/control characters in user input create fake log "
             "lines that mimic system entries.",
             3, 3,
             mitigations=["log sanitizer: strip control chars (slice 413)",
                          "structured JSON logging (slice 009)"],
             tests=["test_sec_413_injection_corpus"]))
    t(Threat("T-15", "Untrusted plugin runs with full privileges",
             "elevation_of_privilege", "plugin_code",
             "Any importable module can be registered as a backend with "
             "no trust distinction.",
             3, 4,
             mitigations=["plugin trust levels + manifest signatures "
                          "(slice 407)"],
             tests=["test_sec_407_plugins"]))
    t(Threat("T-16", "Fuzz-found crash in parsers/validators",
             "denial_of_service", "decision_inputs",
             "Malformed JSON/compact encodings crash serde or validation "
             "instead of raising taxonomy errors.",
             3, 3,
             mitigations=["deterministic fuzz campaign over entry points "
                          "(slice 422)",
                          "taxonomy-only raise discipline (slice 007)"],
             tests=["test_sec_422_fuzzing"]))
    t(Threat("T-17", "Stale/vulnerable transitive dependency",
             "tampering", "model_artifacts",
             "A pinned-but-vulnerable transitive dep ships a known CVE.",
             3, 4,
             mitigations=["advisory DB scan in CI (slice 403)"],
             tests=["test_sec_403_depscan"],
             residual="partial",
             rationale="Curated advisory DB covers direct deps; transitive "
                       "closure auditing needs lockfile hashes, a later "
                       "hardening pass."))
    t(Threat("T-18", "Side-channel: timing reveals cache hits",
             "information_disclosure", "decision_cache",
             "Cache-hit vs miss timing lets an attacker probe whether a "
             "decision was recently made.",
             2, 2,
             mitigations=[],
             tests=[],
             residual="accepted",
             rationale="Local-first single-tenant threat model: attacker "
                       "with timing access already has process access. "
                       "Documented, not defended."))
    return model
