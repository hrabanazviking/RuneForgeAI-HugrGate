"""Memory adversarial tests. Slice 323.

Memory is only as trustworthy as its inputs. A compromised outcome
reporter, a replayed request stream, or a skewed clock can poison
everything downstream (routing, calibration, counterfactuals). This
module scans a history for the classic attacks and reports
:class:`Finding` objects with severity — detection, not
auto-remediation: the operator decides whether to quarantine, purge,
or investigate.

Detectors:

- ``outcome_flooding`` — more than ``threshold`` outcomes attached
  inside ``window_seconds`` (mass-labeling by a rogue reporter);
  critical.
- ``chronology_violation`` — an outcome ``observed_at`` before the
  episode's ``recorded_at`` (causally impossible); critical.
- ``duplicate_flood`` — one ``request_hash`` appearing more than
  ``threshold`` times (replay attack on the recorder); warn.
- ``timestamp_anomaly`` — ``recorded_at`` in the future (beyond
  tolerance) or before 2020-01-01 (clock skew / fabrication); warn.
- ``label_conflict`` — ground truth contradicting the attached
  outcome (mass contradictions suggest label flipping); warn, with
  the conflicting episode ids.

Thresholds are parameters, not magic: tune them to the deployment's
traffic shape.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from hugrgate.memory.groundtruth import outcome_agrees
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import HistoryLike

__all__ = [
    "AdversarialReport",
    "Finding",
    "scan",
]

#: record timestamps before this are treated as fabricated/skewed.
_MIN_SANE_EPOCH = 1577836800.0  # 2020-01-01T00:00:00Z


@dataclass(frozen=True)
class Finding:
    """One detected adversarial pattern."""

    detector: str
    severity: str  # "info" | "warn" | "critical"
    detail: str
    episode_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "severity": self.severity,
            "detail": self.detail,
            "episode_ids": list(self.episode_ids),
        }


@dataclass
class AdversarialReport:
    """Result of :func:`scan`."""

    findings: list[Finding] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        """True when any finding is critical."""
        return any(f.severity == "critical" for f in self.findings)

    def by_detector(self, detector: str) -> list[Finding]:
        """Findings from one detector."""
        return [f for f in self.findings if f.detector == detector]

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "has_critical": self.has_critical,
        }


def scan(history: HistoryLike, *,
         outcome_flood_window_seconds: float = 60.0,
         outcome_flood_threshold: int = 100,
         duplicate_threshold: int = 20,
         future_tolerance_seconds: float = 3600.0,
         now: float | None = None) -> AdversarialReport:
    """Run every adversarial detector over ``history``."""
    if outcome_flood_window_seconds <= 0:
        raise ValueError("outcome_flood_window_seconds must be > 0")
    if outcome_flood_threshold < 1:
        raise ValueError("outcome_flood_threshold must be >= 1")
    if duplicate_threshold < 1:
        raise ValueError("duplicate_threshold must be >= 1")
    if future_tolerance_seconds < 0:
        raise ValueError("future_tolerance_seconds must be >= 0")
    current = time.time() if now is None else now
    episodes = history.find(MemoryQuery())
    report = AdversarialReport()

    # 1. Outcome flooding: bursts of attached outcomes in a short window.
    observed = sorted(e.outcome.observed_at for e in episodes
                      if e.outcome is not None)
    for i, start in enumerate(observed):
        j = i
        while j < len(observed) \
                and observed[j] - start <= outcome_flood_window_seconds:
            j += 1
        if j - i > outcome_flood_threshold:
            culprits = tuple(
                e.episode_id for e in episodes
                if e.outcome is not None
                and start <= e.outcome.observed_at
                <= start + outcome_flood_window_seconds)
            report.findings.append(Finding(
                detector="outcome_flooding",
                severity="critical",
                detail=(f"{j - i} outcomes attached within "
                        f"{outcome_flood_window_seconds:g}s"),
                episode_ids=culprits[:50],
            ))
            break

    # 2. Chronology violations: outcome observed before the decision.
    impossible = tuple(
        e.episode_id for e in episodes
        if e.outcome is not None
        and e.outcome.observed_at < e.recorded_at - 1.0)
    if impossible:
        report.findings.append(Finding(
            detector="chronology_violation",
            severity="critical",
            detail=(f"{len(impossible)} outcome(s) observed before the "
                    f"decision was recorded"),
            episode_ids=impossible[:50],
        ))

    # 3. Duplicate floods: one request hash dominating the store.
    hash_counts = Counter(e.record.request_hash for e in episodes)
    for request_hash, count in hash_counts.most_common():
        if count <= duplicate_threshold:
            break
        report.findings.append(Finding(
            detector="duplicate_flood",
            severity="warn",
            detail=(f"request_hash {request_hash[:12]}... appears "
                    f"{count}x"),
            episode_ids=tuple(
                e.episode_id for e in episodes
                if e.record.request_hash == request_hash)[:50],
        ))

    # 4. Timestamp anomalies: future-dated or impossibly old episodes.
    future = tuple(
        e.episode_id for e in episodes
        if e.recorded_at > current + future_tolerance_seconds)
    ancient = tuple(
        e.episode_id for e in episodes if e.recorded_at < _MIN_SANE_EPOCH)
    if future:
        report.findings.append(Finding(
            detector="timestamp_anomaly",
            severity="warn",
            detail=f"{len(future)} episode(s) dated in the future",
            episode_ids=future[:50],
        ))
    if ancient:
        report.findings.append(Finding(
            detector="timestamp_anomaly",
            severity="warn",
            detail=f"{len(ancient)} episode(s) dated before 2020",
            episode_ids=ancient[:50],
        ))

    # 5. Label conflicts: ground truth vs attached outcome.
    conflicts = []
    for episode in episodes:
        outcome = episode.outcome
        truth = episode.ground_truth
        if outcome is not None and truth is not None \
                and outcome_agrees(truth, outcome) is False:
            conflicts.append(episode.episode_id)
    if conflicts:
        report.findings.append(Finding(
            detector="label_conflict",
            severity="warn",
            detail=(f"{len(conflicts)} episode(s) where ground truth "
                    f"contradicts the attached outcome"),
            episode_ids=tuple(conflicts[:50]),
        ))

    return report
