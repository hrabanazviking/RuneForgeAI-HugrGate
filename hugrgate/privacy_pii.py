"""PII detector interface. Slice 235.

Pluggable personally-identifiable-information detection for outbound
data. :class:`PIIDetector` is the interface — implement
:meth:`PIIDetector.scan_text` and you get nested state scanning for
free. :class:`RegexPIIDetector` is the built-in default with
validated patterns (Luhn-checked credit cards, area-validated SSNs);
:class:`PIIScrubber` applies mask/drop actions to state.

Design notes:

- Detectors are *precision-first*: every pattern carries a
  confidence, and expensive validators (Luhn, SSN area rules) run
  before a finding is reported, so "order 1234" doesn't become a
  credit-card finding.
- Findings never carry the raw value — only a redacted preview.
- Custom detectors compose: :class:`CompositePIIDetector` unions any
  set of detectors.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CompositePIIDetector",
    "PIIDetector",
    "PIIFinding",
    "PIIScrubber",
    "RegexPIIDetector",
]


@dataclass
class PIIFinding:
    """One PII-shaped value found during a scan."""

    field: str  # dotted path, or "<text>"
    kind: str  # "email" | "phone" | "ssn" | "credit_card" | "ipv4" | custom
    confidence: str  # "high" | "medium" | "low"
    preview: str  # redacted preview — never the raw value

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "kind": self.kind,
                "confidence": self.confidence, "preview": self.preview}


def _preview(value: str) -> str:
    if len(value) <= 6:
        return value[:1] + "…" * (len(value) - 1)
    return value[:2] + "…" + value[-2:] + f"({len(value)})"


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _ssn_plausible(ssn: str) -> bool:
    area, group, _serial = ssn.split("-")
    if area in ("000", "666") or area.startswith("9"):
        return False
    return group != "00"


class PIIDetector(ABC):
    """Interface for PII detectors."""

    @abstractmethod
    def scan_text(self, text: str, *, field: str = "<text>") -> \
            list[PIIFinding]:
        """Scan free text; return findings (possibly empty)."""

    def scan_state(self, state: Mapping[str, Any]) -> list[PIIFinding]:
        """Scan every string leaf of a (possibly nested) state mapping."""
        findings: list[PIIFinding] = []

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
        return findings


class RegexPIIDetector(PIIDetector):
    """Built-in regex PII detector with validators.

    Parameters
    ----------
    kinds:
        Subset of ``{"email", "phone", "ssn", "credit_card", "ipv4"}``
        to enable, or None for all.
    """

    _EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    _PHONE = re.compile(
        r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")
    _SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
    _CC = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
    _IPV4 = re.compile(
        r"(?<!\d)(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
        r"(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}(?!\d)")

    KINDS = ("email", "phone", "ssn", "credit_card", "ipv4")

    def __init__(self, kinds: list[str] | tuple[str, ...] | None = None):
        selected = tuple(kinds) if kinds is not None else self.KINDS
        unknown = set(selected) - set(self.KINDS)
        if unknown:
            raise ValueError(f"unknown PII kinds: {sorted(unknown)}; "
                             f"expected subset of {list(self.KINDS)}")
        self.kinds = selected

    def scan_text(self, text: str, *, field: str = "<text>") -> \
            list[PIIFinding]:
        findings: list[PIIFinding] = []
        if not isinstance(text, str):
            return findings
        if "email" in self.kinds:
            for match in self._EMAIL.finditer(text):
                findings.append(PIIFinding(field, "email", "high",
                                           _preview(match.group(0))))
        if "phone" in self.kinds:
            for match in self._PHONE.finditer(text):
                findings.append(PIIFinding(field, "phone", "medium",
                                           _preview(match.group(0))))
        if "ssn" in self.kinds:
            for match in self._SSN.finditer(text):
                candidate = match.group(0)
                if _ssn_plausible(candidate):
                    findings.append(PIIFinding(field, "ssn", "high",
                                               _preview(candidate)))
        if "credit_card" in self.kinds:
            for match in self._CC.finditer(text):
                digits = re.sub(r"[ -]", "", match.group(0))
                if 13 <= len(digits) <= 19 and _luhn_ok(digits):
                    findings.append(PIIFinding(field, "credit_card",
                                               "high",
                                               _preview(match.group(0))))
        if "ipv4" in self.kinds:
            for match in self._IPV4.finditer(text):
                findings.append(PIIFinding(field, "ipv4", "medium",
                                           _preview(match.group(0))))
        return findings


class CompositePIIDetector(PIIDetector):
    """Union of several detectors (built-in + custom)."""

    def __init__(self, detectors: list[PIIDetector]):
        if not detectors:
            raise ValueError("need at least one detector")
        for detector in detectors:
            if not isinstance(detector, PIIDetector):
                raise TypeError(
                    f"not a PIIDetector: {detector!r}")
        self.detectors = list(detectors)

    def scan_text(self, text: str, *, field: str = "<text>") -> \
            list[PIIFinding]:
        findings: list[PIIFinding] = []
        for detector in self.detectors:
            findings.extend(detector.scan_text(text, field=field))
        return findings


class PIIScrubber:
    """Applies mask/drop actions to PII found in state.

    Parameters
    ----------
    detector:
        The :class:`PIIDetector` to use.
    action:
        ``"mask"`` replaces the whole string value with
        ``[PII:<kind>,…]``; ``"drop"`` removes the field.
    """

    def __init__(self, detector: PIIDetector | None = None,
                 action: str = "mask"):
        if action not in ("mask", "drop"):
            raise ValueError(
                f"action must be 'mask' or 'drop', got {action!r}")
        self.detector = detector or RegexPIIDetector()
        self.action = action

    def scrub_state(self, state: Mapping[str, Any]) -> \
            tuple[dict[str, Any], list[PIIFinding]]:
        """Return ``(scrubbed_state, findings)``.

        Mask mode replaces a *whole string value* when any PII is
        found in it (partial in-place masking would leave structure
        that aids re-identification); drop mode removes the field.
        Non-string values pass through untouched.
        """
        findings = self.detector.scan_state(state)
        by_field: dict[str, list[PIIFinding]] = {}
        for finding in findings:
            by_field.setdefault(finding.field, []).append(finding)
        if not by_field:
            return dict(state), []

        def scrub(node: Any, prefix: str) -> Any:
            if isinstance(node, Mapping):
                out = {}
                for key, value in node.items():
                    path = f"{prefix}.{key}" if prefix else str(key)
                    if path in by_field and self.action == "drop":
                        continue
                    out[key] = scrub(value, path)
                return out
            if isinstance(node, list):
                items = []
                for i, value in enumerate(node):
                    item_path = f"{prefix}[{i}]"
                    if item_path in by_field and self.action == "drop":
                        continue
                    items.append(scrub(value, item_path))
                return items
            if isinstance(node, str) and prefix in by_field:
                kinds = sorted({f.kind for f in by_field[prefix]})
                return f"[PII:{','.join(kinds)}]"
            return node

        scrubbed = scrub(dict(state), "")
        assert isinstance(scrubbed, dict)
        return scrubbed, findings
