"""Shift evaluation — quality under distribution shift. Slice 368.

Deploys drift: the data moves, the backend doesn't.  This module
partitions a dataset by a shift variable (time period, domain, data
source) into source/target cohorts and reports, per backend, the
metric *degradation* (target minus source) alongside a pure-Python PSI
(population stability index) on the *label* distributions — how far
the data moved, next to how much the quality moved.  (The numpy
sibling with density-ratio weights lives in
:mod:`hugrgate.calibration.shift`; this is the base-install lab
version.)

Both cohorts run through the v1 bench engine
(:func:`hugrgate.bench.run_benchmark`), so the numbers are directly
comparable with single-shot runs.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.bench import run_benchmark
from hugrgate.core import HugrGate
from hugrgate.errors import EvalError
from hugrgate.evlab.api import MetricSet
from hugrgate.policy import DecisionPolicy

__all__ = [
    "ShiftReport",
    "label_psi",
    "shift_evaluate",
]

_EPS = 1e-6


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def label_psi(
    source_labels: Sequence[Any],
    target_labels: Sequence[Any],
    bins: int = 10,
) -> float:
    """PSI between source/target label distributions (pure Python).

    Categorical labels compare category proportions; anything else is
    binned by source quantiles.  Epsilon-smoothed; 0 means identical.
    """
    src = list(source_labels)
    tgt = list(target_labels)
    if not src or not tgt:
        raise EvalError("PSI needs non-empty source and target labels")
    if bins < 2:
        raise EvalError(f"bins must be >= 2, got {bins}")
    if all(isinstance(v, str) for v in src + tgt):
        categories = sorted(set(src) | set(tgt))
        src_p = [sum(1 for v in src if v == c) / len(src)
                 for c in categories]
        tgt_p = [sum(1 for v in tgt if v == c) / len(tgt)
                 for c in categories]
    else:
        try:
            src_f = sorted(float(v) for v in src)
            tgt_f = [float(v) for v in tgt]
        except (TypeError, ValueError):
            raise EvalError(
                "label_psi needs categorical (str) or numeric labels"
            ) from None
        edges = [src_f[min(int(q * (len(src_f) - 1)), len(src_f) - 1)]
                 for q in (i / bins for i in range(bins + 1))]

        def bin_of(v: float) -> int:
            for i in range(bins):
                if v <= edges[i + 1] or i == bins - 1:
                    return i
            return bins - 1  # pragma: no cover

        src_p = [0.0] * bins
        tgt_p = [0.0] * bins
        for v in src_f:
            src_p[bin_of(v)] += 1.0 / len(src_f)
        for v in tgt_f:
            tgt_p[bin_of(v)] += 1.0 / len(tgt_f)
    psi = 0.0
    for s, t in zip(src_p, tgt_p, strict=True):
        s, t = max(s, _EPS), max(t, _EPS)
        psi += (t - s) * math.log(t / s)
    return psi


@dataclass
class ShiftReport:
    """Per-backend source/target metrics + degradation (slice 368)."""

    backends: dict[str, dict[str, Any]]
    shift_key: str
    source_label: str
    target_label: str
    n_source: int
    n_target: int
    label_psi: float

    def degradation(self, backend: str, metric: str) -> float | None:
        """target minus source for ``metric`` (None when unscored)."""
        info = self._backend(backend)
        return info["degradation"].get(metric)

    def degraded(
        self,
        metric: str = "accuracy",
        min_drop: float = 0.05,
        higher_better: bool = True,
    ) -> list[tuple[str, float]]:
        """Backends whose ``metric`` fell by more than ``min_drop``.

        For higher-better metrics a drop means target < source; for
        lower-better (e.g. ECE) it means target > source.
        """
        if min_drop < 0:
            raise EvalError(f"min_drop must be >= 0, got {min_drop}")
        out = []
        for backend, info in self.backends.items():
            delta = info["degradation"].get(metric)
            if not isinstance(delta, (int, float)):
                continue
            drop = -delta if higher_better else delta
            if drop > min_drop:
                out.append((backend, drop))
        return sorted(out, key=lambda kv: kv[1], reverse=True)

    def _backend(self, backend: str) -> dict[str, Any]:
        try:
            return self.backends[backend]
        except KeyError:
            raise EvalError(f"unknown backend {backend!r}") from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backends": {b: dict(info)
                         for b, info in self.backends.items()},
            "shift_key": self.shift_key,
            "source_label": self.source_label,
            "target_label": self.target_label,
            "n_source": self.n_source,
            "n_target": self.n_target,
            "label_psi": self.label_psi,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ShiftReport:
        return cls(
            backends={b: dict(info)
                      for b, info in data["backends"].items()},
            shift_key=data["shift_key"],
            source_label=data["source_label"],
            target_label=data["target_label"],
            n_source=data["n_source"],
            n_target=data["n_target"],
            label_psi=data["label_psi"],
        )


def shift_evaluate(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backends: Sequence[str] | None = None,
    shift_key: str = "period",
    source: Any = "source",
    target: Any = "target",
    policy: DecisionPolicy | None = None,
    metrics: MetricSet | None = None,
    max_items: int | None = None,
) -> ShiftReport:
    """Evaluate source vs target cohorts; report degradation per backend.

    ``source``/``target`` are shift-key values (or lists of values)
    marking each cohort.  Items missing the shift key raise
    :class:`EvalError` — silent bucketing would hide the very drift
    being measured.
    """
    if not shift_key:
        raise EvalError("shift_key must be a non-empty string")
    source_vals = set(_as_list(source))
    target_vals = set(_as_list(target))
    if source_vals & target_vals:
        raise EvalError(
            f"source and target values overlap: "
            f"{source_vals & target_vals}")
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    if not items:
        raise EvalError("shift evaluation needs at least one item")

    src_items: list[Mapping[str, Any]] = []
    tgt_items: list[Mapping[str, Any]] = []
    missing = 0
    for item in items:
        value = item.get(shift_key)
        if value in source_vals:
            src_items.append(item)
        elif value in target_vals:
            tgt_items.append(item)
        else:
            missing += 1
    if missing:
        raise EvalError(
            f"{missing} item(s) carry no source/target {shift_key!r} "
            f"value; refusing to silently bucket them",
            n_missing=missing,
        )
    if not src_items or not tgt_items:
        raise EvalError(
            f"need non-empty source and target cohorts, got "
            f"{len(src_items)} source / {len(tgt_items)} target items")

    metric_set = metrics or MetricSet()
    metric_set.validate()
    policy = policy or DecisionPolicy()

    def _run(cohort: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        sub = dict(dataset)
        sub["items"] = cohort
        report = run_benchmark(
            sub, gate,
            backends=list(backends) if backends is not None else None,
            policy=policy,
        )
        return {
            name: metric_set.select(bm)
            for name, bm in report["backends"].items()
        }

    src_metrics = _run(src_items)
    tgt_metrics = _run(tgt_items)
    backend_names = sorted(set(src_metrics) | set(tgt_metrics))
    metric_keys = sorted(
        {k for m in list(src_metrics.values()) + list(tgt_metrics.values())
         for k in m})
    results: dict[str, dict[str, Any]] = {}
    for backend in backend_names:
        sm = src_metrics.get(backend, {})
        tm = tgt_metrics.get(backend, {})
        degradation: dict[str, float | None] = {}
        for metric in metric_keys:
            s_val, t_val = sm.get(metric), tm.get(metric)
            if isinstance(s_val, (int, float)) and isinstance(
                    t_val, (int, float)):
                degradation[metric] = float(t_val) - float(s_val)
            else:
                degradation[metric] = None
        results[backend] = {
            "source": dict(sm),
            "target": dict(tm),
            "degradation": degradation,
        }
    psi = label_psi(
        [i.get("expected") for i in src_items],
        [i.get("expected") for i in tgt_items],
    )
    return ShiftReport(
        backends=results,
        shift_key=shift_key,
        source_label=str(sorted(source_vals, key=repr)),
        target_label=str(sorted(target_vals, key=repr)),
        n_source=len(src_items),
        n_target=len(tgt_items),
        label_psi=psi,
    )
