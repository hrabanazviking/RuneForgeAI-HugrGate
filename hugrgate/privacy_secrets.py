"""Secret detection hooks. Slice 234.

Last line of defense before data leaves the process: scan outbound
state (or free text) for secret-shaped values — API keys, tokens,
private keys, credentials — and raise :class:`SecretDetected` instead
of transmitting them.

:class:`SecretScanner` combines:

- curated high-precision patterns (AWS keys, GitHub/Slack tokens,
  PEM private keys, bearer tokens, credential assignments);
- a conservative high-entropy heuristic for opaque tokens with no
  known prefix (off by default — see below).

Findings carry the dotted field path, the pattern name, a redacted
preview (never the full secret), and a confidence level. The scanner
is deliberately *not* a DLP oracle: it catches accidents, not
adversaries. High-entropy detection stays opt-in because natural
text (hashes in logs, base64 blobs) triggers it.

Hook points:

- :func:`assert_no_secrets` — one-shot check; raises on any finding;
- :meth:`PrivacyGuard.check_no_secrets <hugrgate.privacy.PrivacyGuard.check_no_secrets>` —
  guard-level convenience used by the remote payload compiler
  (slice 237).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from hugrgate.errors import SecretDetected

__all__ = [
    "SecretFinding",
    "SecretScanner",
    "assert_no_secrets",
]

#: (name, regex, confidence). Curated for precision over recall.
SECRET_PATTERNS: list[tuple[str, str, str]] = [
    ("aws_access_key", r"AKIA[0-9A-Z]{16}", "high"),
    ("aws_secret_key",
     r"(?i)(aws_secret_access_key|aws_secret)\s*[:=]\s*['\"]?"
     r"[A-Za-z0-9/+=]{40}['\"]?", "high"),
    ("github_token", r"(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}", "high"),
    ("github_pat", r"github_pat_[A-Za-z0-9_]{22,}", "high"),
    ("slack_token", r"xox[abpras]-[A-Za-z0-9-]{10,}", "high"),
    ("pem_private_key",
     r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "high"),
    ("bearer_token", r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}={0,2}", "medium"),
    ("credential_assignment",
     r"(?i)(api[_-]?key|secret|password|passwd|pwd|client_secret)"
     r"\s*[:=]\s*['\"]?[^\s'\"]{8,}['\"]?", "medium"),
]


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(text)
    return -sum((c / length) * math.log2(c / length)
                for c in counts.values())


def _looks_opaque(token: str) -> bool:
    """Conservative opaque-token heuristic: long, base64-ish, entropic."""
    if len(token) < 40:
        return False
    if not re.fullmatch(r"[A-Za-z0-9\-_+/=]+", token):
        return False
    return _shannon_entropy(token) >= 4.0


@dataclass
class SecretFinding:
    """One secret-shaped value found during a scan."""

    field: str  # dotted path, or "<text>" for free-text scans
    pattern: str
    confidence: str  # "high" | "medium" | "low"
    preview: str  # redacted preview — never the full secret

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "pattern": self.pattern,
                "confidence": self.confidence, "preview": self.preview}


def _preview(match: str) -> str:
    if len(match) <= 8:
        return match[:2] + "…" * max(0, len(match) - 2)
    return match[:4] + "…" + f"({len(match)} chars)"


class SecretScanner:
    """Scans text and state mappings for secret-shaped values.

    Parameters
    ----------
    extra_patterns:
        Additional ``(name, regex, confidence)`` triples.
    entropy_scan:
        Enable the conservative high-entropy heuristic (default off).
    min_confidence:
        Ignore findings below this confidence.
    """

    _CONFIDENCE_RANK: ClassVar[dict[str, int]] = \
        {"low": 0, "medium": 1, "high": 2}

    def __init__(self,
                 extra_patterns: list[tuple[str, str, str]] | None = None,
                 entropy_scan: bool = False,
                 min_confidence: str = "low"):
        patterns = list(SECRET_PATTERNS) + list(extra_patterns or [])
        self._patterns = [(name, re.compile(rx), conf)
                          for name, rx, conf in patterns]
        self.entropy_scan = entropy_scan
        if min_confidence not in self._CONFIDENCE_RANK:
            raise ValueError(
                f"unknown confidence: {min_confidence!r}")
        self.min_confidence = min_confidence

    def _keep(self, confidence: str) -> bool:
        return self._CONFIDENCE_RANK[confidence] >= \
            self._CONFIDENCE_RANK[self.min_confidence]

    def scan_text(self, text: str, field: str = "<text>") -> \
            list[SecretFinding]:
        """Scan free text; returns findings (possibly empty)."""
        findings: list[SecretFinding] = []
        if not isinstance(text, str):
            return findings
        for name, rx, confidence in self._patterns:
            if not self._keep(confidence):
                continue
            for match in rx.finditer(text):
                findings.append(SecretFinding(
                    field=field, pattern=name, confidence=confidence,
                    preview=_preview(match.group(0))))
        if self.entropy_scan:
            for token in re.findall(r"[A-Za-z0-9\-_+/=]{40,}", text):
                if _looks_opaque(token) and self._keep("low"):
                    findings.append(SecretFinding(
                        field=field, pattern="high_entropy_token",
                        confidence="low", preview=_preview(token)))
        return findings

    def scan_state(self, state: Mapping[str, Any]) -> list[SecretFinding]:
        """Scan every string leaf of a (possibly nested) state mapping."""
        findings: list[SecretFinding] = []

        def walk(node: Any, prefix: str) -> None:
            if isinstance(node, Mapping):
                for key, value in node.items():
                    path = f"{prefix}.{key}" if prefix else str(key)
                    walk(value, path)
            elif isinstance(node, (list, tuple)):
                for i, value in enumerate(node):
                    walk(value, f"{prefix}[{i}]")
            elif isinstance(node, str):
                findings.extend(self.scan_text(node, field=prefix))

        walk(state, "")
        # De-duplicate identical (field, pattern) hits.
        seen: set[tuple[str, str]] = set()
        unique: list[SecretFinding] = []
        for finding in findings:
            key = (finding.field, finding.pattern)
            if key not in seen:
                seen.add(key)
                unique.append(finding)
        return unique

    def assert_no_secrets(self, state: Mapping[str, Any]) -> None:
        """Raise :class:`SecretDetected` when any secret is found."""
        findings = self.scan_state(state)
        if findings:
            raise SecretDetected(
                f"{len(findings)} secret-shaped value(s) in outbound "
                f"data: " + ", ".join(
                    f"{f.field} ({f.pattern}, {f.confidence})"
                    for f in findings[:5]),
                findings=[f.to_dict() for f in findings])


def assert_no_secrets(state: Mapping[str, Any],
                      scanner: SecretScanner | None = None) -> None:
    """One-shot secret check with the default scanner."""
    (scanner or SecretScanner()).assert_no_secrets(state)
