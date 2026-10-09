"""Privacy leak gauntlet (slice 493).

Redaction machinery exists (``privacy_redact``, ``privacy_pii``,
per-class provenance modes); this module proves no canary secret
escapes through the *observable* surfaces of a decision:

- log records emitted during ``decide`` (captured handler),
- exception messages from failing decisions,
- provenance records for restrictive privacy classes,
- cached-decision log lines on repeat calls.

Canaries are obviously fake (``sk-canary-...``) and documented as
test fixtures — never real credentials.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CANARIES",
    "LeakReport",
    "LeakScanner",
    "run_leak_gauntlet",
    "scan_text",
]

#: Obviously-fake canary secrets. Planted in state; any appearance
#: in logs, errors, or provenance is a leak.
#:
#: NOTE: canaries must NOT match real secret shapes (e.g. ``sk-...``):
#: the execution environment's own secret scrubber redacts such
#: strings in transit, which would make the gauntlet pass vacuously.
#: These values are inert by construction and verified to survive
#: both the environment scrubber and hugrgate's SecretScanner.
CANARIES: tuple[str, ...] = (
    "canary-secret-0001",
    "canary.user@example.test",
    "CANARY-SSN-000-00-0000",
)


def scan_text(text: str, canaries: tuple[str, ...] = CANARIES) -> list[str]:
    """Return the canaries found in ``text`` (empty means clean)."""
    return [c for c in canaries if c in text]


class LeakScanner:
    """Capture ``hugrgate`` log records for leak scanning.

    Use as a context manager around the exercised code, then call
    :meth:`findings`.
    """

    def __init__(self, logger_name: str = "hugrgate") -> None:
        self._logger = logging.getLogger(logger_name)
        self._records: list[logging.LogRecord] = []
        self._handler = _CaptureHandler(self._records)
        self._old_level = logging.NOTSET

    def __enter__(self) -> LeakScanner:
        self._logger.addHandler(self._handler)
        self._old_level = self._logger.level
        self._logger.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *exc: Any) -> None:
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._old_level)

    def log_text(self) -> str:
        return "\n".join(
            r.getMessage() for r in self._records)

    def findings(self,
                 canaries: tuple[str, ...] = CANARIES) -> list[str]:
        """Canaries leaked into captured log records."""
        return scan_text(self.log_text(), canaries)


class _CaptureHandler(logging.Handler):
    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__()
        self._records = records

    def emit(self, record: logging.LogRecord) -> None:
        self._records.append(record)


@dataclass
class LeakReport:
    """Outcome of :func:`run_leak_gauntlet`."""

    findings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.findings


def _record_finding(report: LeakReport, surface: str,
                    canaries: list[str]) -> None:
    if canaries:
        report.findings.append({"surface": surface,
                                 "canaries": list(canaries)})


def run_leak_gauntlet(gate: Any, spec: Any,
                      canaries: tuple[str, ...] = CANARIES) -> LeakReport:
    """Plant canaries in state and scan every observable surface."""
    from hugrgate.policy import DecisionPolicy

    report = LeakReport()
    secret_state = {
        "api_key": canaries[0],
        "email": canaries[1],
        "ssn": canaries[2],
        "feature": 1.0,
    }

    # 1. Log surface during a normal decision (and a cache hit).
    # Decides may fail (e.g. a hostile backend); the captured logs
    # are still scanned — a leak is a leak whatever the outcome.
    with LeakScanner() as scanner:
        policy = DecisionPolicy(privacy_class="standard")
        for _ in range(2):
            try:
                gate.decide(secret_state, spec, policy)
            except Exception:  # noqa: BLE001 - failures have their own surface
                pass
    _record_finding(report, "logs", scanner.findings(canaries))

    # 2. Exception surface: a failing decision must not echo secrets.
    try:
        gate.decide(secret_state, spec, DecisionPolicy())
    except Exception as exc:  # noqa: BLE001 - message under test
        _record_finding(report, "exception",
                        scan_text(str(exc), canaries))
    # Force a failure with an invalid spec shape.
    try:
        gate.decide(secret_state, {"type": "nope"}, policy)
    except Exception as exc:  # noqa: BLE001 - message under test
        _record_finding(report, "exception-invalid-spec",
                        scan_text(str(exc), canaries))

    # 3. Provenance surface under restrictive classes.
    for privacy_class in ("strict", "forbidden"):
        strict_policy = DecisionPolicy(privacy_class=privacy_class)
        try:
            gate.decide(secret_state, spec, strict_policy)
        except Exception:  # noqa: BLE001 - failures have their own surface
            pass
        records = gate.provenance.scan(lambda r: True)
        blob = json.dumps([r.to_dict() for r in records], default=str)
        _record_finding(report, f"provenance[{privacy_class}]",
                        scan_text(blob, canaries))
    return report
