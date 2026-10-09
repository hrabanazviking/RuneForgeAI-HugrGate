"""Cross-validation harness — k-fold evaluation over backends. Slice 357.

Folds come from :func:`hugrgate.evlab.splits.kfold_indices` (each item
tests exactly once); each fold's test items run through the v1 bench
engine (:func:`hugrgate.bench.run_benchmark`), so abstention, latency,
and calibration accounting stay identical to single-shot runs.  The
:class:`CVReport` aggregates each metric across folds as
mean/sample-std/min/max — the honest spread of a backend's quality,
not just its headline.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.bench import run_benchmark
from hugrgate.core import HugrGate
from hugrgate.errors import EvalError
from hugrgate.evlab.api import MetricSet
from hugrgate.evlab.splits import kfold_indices
from hugrgate.policy import DecisionPolicy

__all__ = [
    "CVReport",
    "FoldResult",
    "cross_validate",
]


@dataclass
class FoldResult:
    """One fold: test metrics per backend + fold geometry."""

    fold: int
    n_train: int
    n_test: int
    backends: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold": self.fold,
            "n_train": self.n_train,
            "n_test": self.n_test,
            "backends": {b: dict(m) for b, m in self.backends.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FoldResult:
        return cls(
            fold=data["fold"],
            n_train=data["n_train"],
            n_test=data["n_test"],
            backends={b: dict(m) for b, m in data["backends"].items()},
        )


@dataclass
class CVReport:
    """Aggregated k-fold cross-validation results (slice 357)."""

    k: int
    seed: int
    n_items: int
    folds: list[FoldResult]
    # backend -> metric -> {"mean","std","min","max","n_folds"}
    aggregate: dict[str, dict[str, dict[str, float | None]]]

    def summarize(
        self, backend: str, metric: str
    ) -> dict[str, float | None]:
        """Fold-aggregate for one backend/metric; KeyError if unknown."""
        try:
            return dict(self.aggregate[backend][metric])
        except KeyError:
            raise EvalError(
                f"no CV aggregate for backend={backend!r} metric={metric!r}",
                backend=backend, metric=metric,
            ) from None

    def rank(
        self, metric: str, higher_better: bool = True
    ) -> list[tuple[str, float | None]]:
        """Backends ordered by fold-mean of ``metric``."""
        scored = [
            (backend, agg[metric]["mean"])
            for backend, agg in self.aggregate.items()
            if metric in agg
        ]
        scored.sort(key=lambda kv: (
            kv[1] is None,  # unscored backends sink to the end
            -(kv[1] or 0.0) if higher_better else (kv[1] or 0.0),
        ))
        return scored

    def to_dict(self) -> dict[str, Any]:
        return {
            "k": self.k,
            "seed": self.seed,
            "n_items": self.n_items,
            "folds": [f.to_dict() for f in self.folds],
            "aggregate": {
                b: {m: dict(a) for m, a in metrics.items()}
                for b, metrics in self.aggregate.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CVReport:
        return cls(
            k=data["k"],
            seed=data["seed"],
            n_items=data["n_items"],
            folds=[FoldResult.from_dict(f) for f in data["folds"]],
            aggregate={
                b: {m: dict(a) for m, a in metrics.items()}
                for b, metrics in data["aggregate"].items()
            },
        )


def _fold_stats(values: list[float | None]) -> dict[str, float | None]:
    scored = [v for v in values if v is not None]
    if not scored:
        return {"mean": None, "std": None, "min": None, "max": None,
                "n_folds": 0.0}
    return {
        "mean": statistics.fmean(scored),
        "std": statistics.stdev(scored) if len(scored) > 1 else 0.0,
        "min": min(scored),
        "max": max(scored),
        "n_folds": float(len(scored)),
    }


def cross_validate(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    k: int = 5,
    seed: int = 0,
    backends: Sequence[str] | None = None,
    policy: DecisionPolicy | None = None,
    metrics: MetricSet | None = None,
) -> CVReport:
    """k-fold cross-validation of backends; return a :class:`CVReport`.

    Each fold trains on nothing (HugrGate backends are stateless w.r.t.
    the lab — the "train" split sizes are reported for geometry) and
    evaluates on its test fold through the v1 bench engine.  Folds are
    deterministic for a fixed seed via
    :func:`hugrgate.evlab.splits.kfold_indices`.
    """
    items = list(dataset.get("items", []))
    if not items:
        raise EvalError("cross-validation needs at least one item")
    folds_idx = kfold_indices(len(items), k, seed=seed)
    metric_set = metrics or MetricSet()
    metric_set.validate()
    policy = policy or DecisionPolicy()

    fold_results: list[FoldResult] = []
    for fold_no, (train_idx, test_idx) in enumerate(folds_idx):
        sub = dict(dataset)
        sub["items"] = [items[i] for i in test_idx]
        report = run_benchmark(
            sub, gate,
            backends=list(backends) if backends is not None else None,
            policy=policy,
        )
        fold_results.append(FoldResult(
            fold=fold_no,
            n_train=len(train_idx),
            n_test=len(test_idx),
            backends={
                name: metric_set.select(bm)
                for name, bm in report["backends"].items()
            },
        ))

    backend_names = sorted(
        {b for f in fold_results for b in f.backends})
    metric_keys = sorted(
        {m for f in fold_results for b in f.backends
         for m in f.backends[b]})
    aggregate: dict[str, dict[str, dict[str, float | None]]] = {}
    for backend in backend_names:
        aggregate[backend] = {}
        for metric in metric_keys:
            values = [
                (f.backends[backend].get(metric)
                 if backend in f.backends else None)
                for f in fold_results
            ]
            typed = [float(v) if isinstance(v, (int, float)) else None
                     for v in values]
            aggregate[backend][metric] = _fold_stats(typed)

    return CVReport(k=k, seed=seed, n_items=len(items),
                    folds=fold_results, aggregate=aggregate)
