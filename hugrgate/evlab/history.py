"""Regression history — run records over time. Slice 370.

The lab writes one :class:`RunRecord` per evaluation; this module
keeps them in an append-only JSONL store and answers the question
every lab eventually faces: *did we get worse?*

- :class:`HistoryStore` — append/query/prune a JSONL run history.
  Writes are atomic (temp file + rename); a corrupt line raises
  :class:`EvalError` naming the line instead of being silently
  skipped.
- :func:`detect_regression` — compares the latest value of a metric
  against the best (or median) of the trailing window and reports a
  :class:`RegressionFinding` when the drop exceeds ``min_drop``.
  Only flags *strict* worsening; improvement and noise return None.
- :func:`series_summary` — first/last/min/max/delta for report
  tables (slice 374 consumes this).
"""

from __future__ import annotations

import json
import os
import statistics
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hugrgate.errors import EvalError
from hugrgate.evlab.api import RunRecord

__all__ = [
    "HistoryStore",
    "RegressionFinding",
    "detect_regression",
    "series_summary",
]


@dataclass
class RegressionFinding:
    """A detected metric regression (slice 370)."""

    dataset: str
    backend: str
    metric: str
    current: float
    baseline: float
    drop: float
    current_run_id: str
    baseline_run_id: str
    current_sha: str | None
    baseline_sha: str | None
    current_at: str
    baseline_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "backend": self.backend,
            "metric": self.metric,
            "current": self.current,
            "baseline": self.baseline,
            "drop": self.drop,
            "current_run_id": self.current_run_id,
            "baseline_run_id": self.baseline_run_id,
            "current_sha": self.current_sha,
            "baseline_sha": self.baseline_sha,
            "current_at": self.current_at,
            "baseline_at": self.baseline_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RegressionFinding:
        return cls(
            dataset=data["dataset"],
            backend=data["backend"],
            metric=data["metric"],
            current=data["current"],
            baseline=data["baseline"],
            drop=data["drop"],
            current_run_id=data["current_run_id"],
            baseline_run_id=data["baseline_run_id"],
            current_sha=data.get("current_sha"),
            baseline_sha=data.get("baseline_sha"),
            current_at=data["current_at"],
            baseline_at=data["baseline_at"],
        )


class HistoryStore:
    """Append-only JSONL store of :class:`RunRecord` entries."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: RunRecord) -> None:
        if not isinstance(record, RunRecord):
            raise EvalError(
                f"HistoryStore.append needs a RunRecord, got "
                f"{type(record).__name__}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), sort_keys=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _read_all(self) -> list[RunRecord]:
        if not self.path.exists():
            return []
        records = []
        with open(self.path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    raise EvalError(
                        f"corrupt history line {lineno} in "
                        f"{self.path}: {e}") from e
                try:
                    records.append(RunRecord.from_dict(data))
                except (KeyError, TypeError) as e:
                    raise EvalError(
                        f"invalid RunRecord on history line {lineno} "
                        f"in {self.path}: {e}") from e
        return records

    def records(
        self,
        dataset: str | None = None,
        backend: str | None = None,
        fingerprint: str | None = None,
    ) -> list[RunRecord]:
        """All records, oldest first, optionally filtered."""
        out = []
        for record in self._read_all():
            if dataset is not None and record.dataset_name != dataset:
                continue
            if backend is not None and backend not in record.backends:
                continue
            if (fingerprint is not None
                    and record.dataset_fingerprint != fingerprint):
                continue
            out.append(record)
        return out

    def latest(
        self, dataset: str, backend: str
    ) -> RunRecord | None:
        matches = self.records(dataset=dataset, backend=backend)
        return matches[-1] if matches else None

    def series(
        self, dataset: str, backend: str, metric: str
    ) -> list[tuple[str, float]]:
        """(finished_at, value) pairs for the metric, oldest first."""
        points = []
        for record in self.records(dataset=dataset, backend=backend):
            value = record.backends.get(backend, {}).get(metric)
            if isinstance(value, (int, float)):
                points.append((record.finished_at, float(value)))
        return points

    def prune(self, keep_last: int) -> int:
        """Keep the newest ``keep_last`` records per dataset/backend.

        Returns the number of records removed.
        """
        if keep_last < 1:
            raise EvalError(
                f"keep_last must be >= 1, got {keep_last}")
        records = self._read_all()
        newest: dict[tuple[str, str], list[RunRecord]] = {}
        for record in records:
            for backend in record.backends:
                key = (record.dataset_name, backend)
                newest.setdefault(key, []).append(record)
        keep_ids = set()
        for series in newest.values():
            for record in series[-keep_last:]:
                keep_ids.add(record.run_id)
        kept = [r for r in records if r.run_id in keep_ids]
        removed = len(records) - len(kept)
        if removed:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", delete=False,
                dir=str(self.path.parent), suffix=".jsonl")
            try:
                with tmp:
                    for record in kept:
                        tmp.write(json.dumps(record.to_dict(),
                                             sort_keys=True) + "\n")
                os.replace(tmp.name, self.path)
            except BaseException:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
                raise
        return removed


def detect_regression(
    store: HistoryStore,
    dataset: str,
    backend: str,
    metric: str,
    min_drop: float = 0.02,
    higher_better: bool = True,
    baseline: str = "best",
    window: int = 5,
    current: RunRecord | None = None,
) -> RegressionFinding | None:
    """Flag a regression of ``metric`` in the latest run.

    Compares the latest value against the ``baseline`` ("best" or
    "median") of the trailing ``window`` prior runs.  Returns a
    :class:`RegressionFinding` when the drop strictly exceeds
    ``min_drop``; None otherwise (including when there is no prior
    history).

    ``current`` optionally supplies the run under evaluation when it
    has not been appended to the store yet (the release gate's case):
    it is treated as the latest entry without mutating the store.
    """
    if baseline not in ("best", "median"):
        raise EvalError(
            f"baseline must be 'best' or 'median', got {baseline!r}")
    if window < 1:
        raise EvalError(f"window must be >= 1, got {window}")
    if min_drop < 0:
        raise EvalError(f"min_drop must be >= 0, got {min_drop}")
    records = store.records(dataset=dataset, backend=backend)
    scored = [
        r for r in records
        if isinstance(r.backends.get(backend, {}).get(metric),
                      (int, float))
    ]
    if current is not None:
        if not isinstance(current, RunRecord):
            raise EvalError(
                f"detect_regression current must be a RunRecord, got "
                f"{type(current).__name__}")
        if not isinstance(current.backends.get(backend, {}).get(metric),
                          (int, float)):
            return None  # unscored current: nothing to compare
        scored = [*scored, current]
    if len(scored) < 2:
        return None
    current = scored[-1]
    prior = scored[-1 - window:-1] or scored[:-1]
    prior_values = [float(r.backends[backend][metric]) for r in prior]
    current_value = float(current.backends[backend][metric])
    if baseline == "best":
        pick = max if higher_better else min
        base_value = pick(prior_values)
        base_record = prior[prior_values.index(base_value)]
    else:
        base_value = float(statistics.median(prior_values))
        base_record = min(
            prior,
            key=lambda r: abs(float(r.backends[backend][metric])
                              - base_value),
        )
    drop = (base_value - current_value) if higher_better \
        else (current_value - base_value)
    if drop <= min_drop:
        return None
    return RegressionFinding(
        dataset=dataset,
        backend=backend,
        metric=metric,
        current=current_value,
        baseline=base_value,
        drop=drop,
        current_run_id=current.run_id,
        baseline_run_id=base_record.run_id,
        current_sha=current.git_sha,
        baseline_sha=base_record.git_sha,
        current_at=current.finished_at,
        baseline_at=base_record.finished_at,
    )


def series_summary(
    store: HistoryStore,
    dataset: str,
    backend: str,
    metric: str,
) -> dict[str, Any]:
    """first/last/min/max/delta/n for a metric series (report tables)."""
    points = store.series(dataset, backend, metric)
    values = [v for _, v in points]
    if not values:
        return {"n": 0, "first": None, "last": None, "min": None,
                "max": None, "delta": None}
    return {
        "n": len(values),
        "first": values[0],
        "last": values[-1],
        "min": min(values),
        "max": max(values),
        "delta": values[-1] - values[0],
    }
