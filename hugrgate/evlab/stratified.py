"""Stratified evaluation — per-stratum metrics + aggregates. Slice 356.

A single headline metric hides *where* a backend fails.  This module
runs the v1 bench engine once per stratum (full reuse of
:func:`hugrgate.bench.run_benchmark`, including its abstention and
latency accounting) and aggregates:

- ``macro`` — unweighted mean across strata (every stratum counts the
  same, so a tiny failing stratum cannot hide behind a huge easy one);
- ``micro`` — ``n_decided``-weighted mean (the pooled headline);
- count metrics (``n_decided``/``n_abstained``/``n_errors``) are summed
  for ``micro`` and averaged for ``macro``.

:func:`StratifiedReport.worst_stratum` names the weakest stratum per
backend and metric — the lab's primary "where does it hurt" query.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.bench import run_benchmark
from hugrgate.core import HugrGate
from hugrgate.errors import DatasetError
from hugrgate.evlab.api import MetricSet
from hugrgate.policy import DecisionPolicy

__all__ = [
    "StratifiedReport",
    "stratified_evaluate",
]

#: Metrics aggregated as plain means (higher/lower-better quality and
#: latency/throughput signals).  ``n_*`` counts are summed instead.
_COUNT_PREFIX = "n_"


def _aggregate(
    scored: list[tuple[float | None, int]],
) -> dict[str, float | None]:
    """macro/micro aggregation over (value, n_decided) pairs."""
    vals = [(v, n) for v, n in scored if v is not None]
    if not vals:
        return {"macro": None, "micro": None}
    macro = sum(v for v, _ in vals) / len(vals)
    total_n = sum(n for _, n in vals)
    micro = (
        sum(v * n for v, n in vals) / total_n if total_n > 0 else None
    )
    return {"macro": macro, "micro": micro}


def _aggregate_counts(counts: list[int]) -> dict[str, float | None]:
    return {
        "macro": sum(counts) / len(counts) if counts else None,
        "micro": float(sum(counts)) if counts else None,
    }


@dataclass
class StratifiedReport:
    """Per-stratum metrics plus macro/micro aggregates (slice 356)."""

    stratify_key: str
    strata: list[str]
    stratum_sizes: dict[str, int]
    # stratum -> backend -> selected metrics
    per_stratum: dict[str, dict[str, dict[str, Any]]]
    # backend -> metric -> {"macro": x, "micro": y}
    aggregate: dict[str, dict[str, dict[str, float | None]]]
    n_items: int = 0

    def worst_stratum(
        self, backend: str, metric: str, higher_better: bool = True
    ) -> tuple[str | None, float | None]:
        """(stratum, value) where ``backend`` scores worst on ``metric``."""
        scored: list[tuple[str, float]] = []
        for stratum in self.strata:
            value = self.per_stratum[stratum][backend].get(metric)
            if isinstance(value, (int, float)):
                scored.append((stratum, float(value)))
        if not scored:
            return None, None
        pick = min if higher_better else max
        return pick(scored, key=lambda kv: kv[1])

    def disparity(
        self, backend: str, metric: str, higher_better: bool = True
    ) -> float | None:
        """max-minus-min of ``metric`` across strata (None when unscored)."""
        values = [
            float(self.per_stratum[s][backend][metric])
            for s in self.strata
            if isinstance(self.per_stratum[s][backend].get(metric),
                          (int, float))
        ]
        if len(values) < 2:
            return None
        return max(values) - min(values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stratify_key": self.stratify_key,
            "strata": list(self.strata),
            "stratum_sizes": dict(self.stratum_sizes),
            "per_stratum": {
                s: {b: dict(m) for b, m in backends.items()}
                for s, backends in self.per_stratum.items()
            },
            "aggregate": {
                b: {m: dict(a) for m, a in metrics.items()}
                for b, metrics in self.aggregate.items()
            },
            "n_items": self.n_items,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StratifiedReport:
        return cls(
            stratify_key=data["stratify_key"],
            strata=list(data["strata"]),
            stratum_sizes=dict(data["stratum_sizes"]),
            per_stratum={
                s: {b: dict(m) for b, m in backends.items()}
                for s, backends in data["per_stratum"].items()
            },
            aggregate={
                b: {m: dict(a) for m, a in metrics.items()}
                for b, metrics in data["aggregate"].items()
            },
            n_items=data.get("n_items", 0),
        )


def stratified_evaluate(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    *,
    stratify_key: str | None = None,
    key_fn: Callable[[Mapping[str, Any]], Any] | None = None,
    backends: Sequence[str] | None = None,
    policy: DecisionPolicy | None = None,
    metrics: MetricSet | None = None,
    max_items: int | None = None,
) -> StratifiedReport:
    """Evaluate ``dataset`` per stratum; return a :class:`StratifiedReport`.

    Strata come from ``item[stratify_key]`` (or ``key_fn(item)``).  An
    item missing its stratum label raises :class:`DatasetError` — a
    silent ``"unknown"`` bucket would hide label drift.
    """
    if stratify_key is None and key_fn is None:
        raise DatasetError("stratified_evaluate needs stratify_key or key_fn")
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    if not items:
        raise DatasetError("stratified evaluation needs at least one item")

    key_label = stratify_key if stratify_key is not None else "key_fn"
    if stratify_key is None:
        assert key_fn is not None  # guaranteed by the check above
        label_of: Callable[[Mapping[str, Any]], Any] = key_fn
    else:
        column = stratify_key

        def label_of(item: Mapping[str, Any]) -> Any:
            return item.get(column)

    groups: dict[Any, list[Mapping[str, Any]]] = {}
    missing = 0
    for item in items:
        key = label_of(item)
        if key is None:
            missing += 1
            continue
        groups.setdefault(key, []).append(item)
    if missing:
        raise DatasetError(
            f"{missing} item(s) are missing the stratum label "
            f"({key_label!r}); refusing to silently bucket them",
            n_missing=missing,
        )
    if not groups:
        raise DatasetError("no strata found in dataset")

    metric_set = metrics or MetricSet()
    metric_set.validate()
    policy = policy or DecisionPolicy()
    base = dict(dataset)
    per_stratum: dict[str, dict[str, dict[str, Any]]] = {}
    stratum_sizes: dict[str, int] = {}
    for key in sorted(groups, key=repr):
        sub = dict(base)
        sub["items"] = groups[key]
        report = run_benchmark(sub, gate, backends=list(backends)
                               if backends is not None else None,
                               policy=policy)
        label = str(key)
        stratum_sizes[label] = len(groups[key])
        per_stratum[label] = {
            name: metric_set.select(bm)
            for name, bm in report["backends"].items()
        }

    strata = sorted(per_stratum)
    backend_names = sorted(
        {b for per in per_stratum.values() for b in per})
    aggregate: dict[str, dict[str, dict[str, float | None]]] = {}
    metric_keys = sorted(
        {k for per in per_stratum.values()
         for bmetrics in per.values() for k in bmetrics})
    for backend in backend_names:
        aggregate[backend] = {}
        for metric in metric_keys:
            if metric.startswith(_COUNT_PREFIX):
                counts = [
                    int(per_stratum[s][backend].get(metric) or 0)
                    for s in strata
                ]
                aggregate[backend][metric] = _aggregate_counts(counts)
                continue
            scored: list[tuple[float | None, int]] = []
            for s in strata:
                raw = per_stratum[s][backend].get(metric)
                n = per_stratum[s][backend].get("n_decided")
                scored.append((
                    float(raw) if isinstance(raw, (int, float)) else None,
                    int(n) if isinstance(n, int) else 0,
                ))
            aggregate[backend][metric] = _aggregate(scored)

    return StratifiedReport(
        stratify_key=key_label,
        strata=strata,
        stratum_sizes=stratum_sizes,
        per_stratum=per_stratum,
        aggregate=aggregate,
        n_items=len(items),
    )
