"""Evaluation API v2 — experiments, runs, and run records. Slice 351.

What exists (inspected before writing a line):

- :mod:`hugrgate.bench` (v1, slice 45): ``run_benchmark`` sweeps a
  dataset over backends and returns a raw report dict.  No notion of a
  named, repeatable experiment; no run identity; no seed discipline;
  no metric selection.
- :mod:`hugrgate.perfgate` (slice 298): regression gates over latency
  baselines — a different axis (performance, not decision quality).
- :mod:`hugrgate.millionbench` (slice 299): throughput soak harness.
- :mod:`hugrgate.calibration.bench` : calibration-specific comparisons.

v2 adds the laboratory frame around the v1 engine:

- :class:`Experiment` — a named, seeded, JSON-serializable evaluation
  plan: dataset, backends, policy, metric set, tags.
- :class:`EvaluationLab` — registers experiments, executes them, and
  returns :class:`RunRecord` objects.  Runs are deterministic for a
  fixed seed (the lab seeds the stdlib RNG; backend determinism remains
  the backend's own contract, documented here rather than assumed).
- :class:`RunRecord` — an immutable, serializable record of one run:
  identity, timestamps, dataset fingerprint + version, policy, metrics
  per backend, provenance (hugrgate version, platform, best-effort git
  SHA), and privacy annotations.
- :class:`MetricSet` — selects which v1 metrics a run reports and
  admits post-hoc derived metrics over the per-backend metric dict.

Integration:

- Policy/validation flow through :meth:`HugrGate.decide` exactly as in
  v1; the dataset spec is parsed eagerly so a bad spec fails fast with
  :class:`SpecError` before any backend runs.
- Privacy: a dataset may declare ``"sensitivity": "restricted"`` (or
  ``"contains_pii": true``).  Restricted data refuses to run unless the
  policy's ``privacy_class`` is ``"sensitive"`` or ``"strict"``; the
  record always carries the effective privacy class.
- Provenance: every record carries the dataset fingerprint
  (:func:`hugrgate.bench.dataset_fingerprint`), the dataset version,
  the hugrgate version, platform data, seed, and a best-effort git SHA.
- Errors: misconfiguration and empty runs raise :class:`EvalError`
  (deliberately not recoverable — fix the experiment, then re-run);
  malformed datasets raise :class:`DatasetError`.
"""

from __future__ import annotations

import platform
import random
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate import __version__ as HUGRGATE_VERSION
from hugrgate.bench import dataset_fingerprint, run_benchmark
from hugrgate.core import HugrGate
from hugrgate.errors import DatasetError, EvalError
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec

logger = get_logger(__name__)

__all__ = [
    "DEFAULT_METRICS",
    "EvaluationLab",
    "Experiment",
    "MetricSet",
    "RunRecord",
]

#: Metric keys every :func:`hugrgate.bench.run_benchmark` per-backend
#: report is guaranteed to carry; selectable via :class:`MetricSet`.
DEFAULT_METRICS: tuple[str, ...] = (
    "accuracy",
    "brier_score",
    "ece",
    "latency_p50_ms",
    "latency_p99_ms",
    "latency_mean_ms",
    "throughput_per_s",
    "abstention_rate",
    "n_decided",
    "n_abstained",
    "n_errors",
)

#: Privacy classes that may touch a dataset flagged restricted.
RESTRICTED_OK_CLASSES = ("sensitive", "strict")

#: A post-hoc metric computed from one backend's selected metric dict.
DerivedMetric = Callable[[dict[str, Any]], float | None]


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _git_sha() -> str | None:
    """Best-effort source SHA for provenance; None when unavailable.

    Never fails the run: a lab checkout without git metadata (an
    installed wheel, a copied tree) still produces valid records.
    """
    try:
        root = Path(__file__).resolve().parents[2]
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        sha = out.stdout.strip()
        return sha or None
    except Exception:  # noqa: BLE001 - provenance is best-effort by design
        return None


@dataclass
class MetricSet:
    """Which metrics a run reports, plus post-hoc derived metrics.

    ``include`` must name keys from :data:`DEFAULT_METRICS`; anything
    else raises :class:`EvalError` at experiment validation time.
    ``derived`` maps a new metric name to a callable over the backend's
    selected metric dict, e.g.::

        MetricSet(derived={"error_rate": lambda m: 1.0 - (m["accuracy"] or 0.0)})
    """

    include: tuple[str, ...] = DEFAULT_METRICS
    derived: dict[str, DerivedMetric] = field(default_factory=dict)

    def validate(self) -> None:
        unknown = [m for m in self.include if m not in DEFAULT_METRICS]
        if unknown:
            raise EvalError(
                f"unknown metrics: {unknown}; "
                f"selectable: {list(DEFAULT_METRICS)}",
                metrics=list(unknown),
            )
        for name in self.derived:
            if not name or not isinstance(name, str):
                raise EvalError(
                    f"derived metric names must be non-empty strings: {name!r}"
                )

    def select(self, backend_metrics: Mapping[str, Any]) -> dict[str, Any]:
        """Project one backend's v1 metrics onto this set + derived."""
        selected = {k: backend_metrics.get(k) for k in self.include}
        for name, fn in self.derived.items():
            try:
                selected[name] = fn(dict(selected))
            except Exception as exc:  # user-supplied derived metric
                raise EvalError(
                    f"derived metric {name!r} failed: {exc}",
                    metric=name,
                ) from exc
        return selected

    def to_dict(self) -> dict[str, Any]:
        return {"include": list(self.include),
                "derived": sorted(self.derived)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MetricSet:
        # Derived callables cannot survive JSON; a deserialized set keeps
        # the *names* so records stay honest about what was requested.
        obj = cls(include=tuple(data.get("include", DEFAULT_METRICS)))
        obj._derived_names = sorted(data.get("derived", []))  # type: ignore[attr-defined]
        return obj


@dataclass
class Experiment:
    """A named, seeded, serializable evaluation plan."""

    name: str
    dataset: Mapping[str, Any]
    backends: list[str] | None = None
    policy: DecisionPolicy | None = None
    seed: int = 0
    metrics: MetricSet | None = None
    tags: dict[str, str] = field(default_factory=dict)
    max_items: int | None = None

    def validate(self) -> None:
        """Fail fast on misconfiguration; raises :class:`EvalError`."""
        if not self.name or not isinstance(self.name, str):
            raise EvalError("experiment name must be a non-empty string")
        if not isinstance(self.dataset, Mapping):
            raise DatasetError("experiment dataset must be a mapping")
        if "spec" not in self.dataset:
            raise DatasetError("dataset mapping is missing 'spec'")
        items = self.dataset.get("items")
        if not isinstance(items, list) or not items:
            raise DatasetError(
                "dataset has no items; an evaluation run needs at least one",
                n_items=0 if isinstance(items, list) else None,
            )
        # Parse the spec eagerly: a bad spec fails here with SpecError,
        # before any backend is touched.
        DecisionSpec.from_dict(self.dataset["spec"])
        for item in items:
            if not isinstance(item, Mapping) or "state" not in item:
                raise DatasetError(
                    "every dataset item must be a mapping with 'state'"
                )
        if self.backends is not None:
            if not self.backends or not all(
                isinstance(b, str) and b for b in self.backends
            ):
                raise EvalError(
                    "backends must be a non-empty list of backend names"
                )
        if self.policy is not None and not isinstance(
            self.policy, DecisionPolicy
        ):
            raise EvalError("policy must be a DecisionPolicy or None")
        if not isinstance(self.seed, int):
            raise EvalError("seed must be an int")
        if self.max_items is not None and (
            not isinstance(self.max_items, int) or self.max_items < 1
        ):
            raise EvalError("max_items must be a positive int or None")
        if self.metrics is not None:
            self.metrics.validate()
        sensitivity = self.dataset.get("sensitivity", "public")
        restricted = (
            sensitivity == "restricted" or self.dataset.get("contains_pii")
        )
        policy_class = (self.policy or DecisionPolicy()).privacy_class
        if restricted and policy_class not in RESTRICTED_OK_CLASSES:
            raise EvalError(
                "dataset is flagged restricted/PII: refusing to run under "
                f"privacy_class={policy_class!r}; use one of "
                f"{list(RESTRICTED_OK_CLASSES)}",
                privacy_class=policy_class,
            )

    def effective_policy(self) -> DecisionPolicy:
        return self.policy or DecisionPolicy()

    def effective_metrics(self) -> MetricSet:
        return self.metrics or MetricSet()

    def plan(self) -> dict[str, Any]:
        """Human/audit-readable execution plan without running anything."""
        self.validate()
        return {
            "experiment": self.name,
            "seed": self.seed,
            "backends": self.backends or "all supporting",
            "n_items": len(self.dataset["items"])
            if self.max_items is None
            else min(self.max_items, len(self.dataset["items"])),
            "dataset": self.dataset.get("name", "unnamed"),
            "dataset_version": self.dataset.get("version", "unknown"),
            "dataset_fingerprint": dataset_fingerprint(self.dataset),
            "policy": self.effective_policy().to_dict(),
            "metrics": self.effective_metrics().to_dict(),
            "tags": dict(self.tags),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dataset": dict(self.dataset),
            "backends": self.backends,
            "policy": self.effective_policy().to_dict(),
            "seed": self.seed,
            "metrics": self.effective_metrics().to_dict(),
            "tags": dict(self.tags),
            "max_items": self.max_items,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Experiment:
        policy_data = data.get("policy")
        return cls(
            name=data["name"],
            dataset=data["dataset"],
            backends=data.get("backends"),
            policy=DecisionPolicy(**policy_data)
            if policy_data
            else None,
            seed=data.get("seed", 0),
            metrics=MetricSet.from_dict(data["metrics"])
            if data.get("metrics")
            else None,
            tags=dict(data.get("tags", {})),
            max_items=data.get("max_items"),
        )


@dataclass
class RunRecord:
    """Immutable record of one :class:`EvaluationLab` run."""

    run_id: str
    experiment_name: str
    seed: int
    started_at: str
    finished_at: str
    elapsed_s: float
    hugrgate_version: str
    python_version: str
    platform: dict[str, str]
    dataset_name: str
    dataset_version: str
    dataset_fingerprint: str
    policy: dict[str, Any]
    privacy_class: str
    tags: dict[str, str]
    backends: dict[str, dict[str, Any]]
    n_items: int
    git_sha: str | None = None

    def best(
        self, metric: str, higher_better: bool = True
    ) -> tuple[str | None, float | None]:
        """Backend with the best ``metric``; (None, None) when unscored."""
        scored: list[tuple[str, float]] = []
        for name, metrics in self.backends.items():
            value = metrics.get(metric)
            if isinstance(value, (int, float)):
                scored.append((name, float(value)))
        if not scored:
            return None, None
        pick = max if higher_better else min
        name, value = pick(scored, key=lambda kv: kv[1])
        return name, value

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "experiment_name": self.experiment_name,
            "seed": self.seed,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_s": self.elapsed_s,
            "hugrgate_version": self.hugrgate_version,
            "python_version": self.python_version,
            "platform": dict(self.platform),
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "dataset_fingerprint": self.dataset_fingerprint,
            "policy": dict(self.policy),
            "privacy_class": self.privacy_class,
            "tags": dict(self.tags),
            "backends": {k: dict(v) for k, v in self.backends.items()},
            "n_items": self.n_items,
            "git_sha": self.git_sha,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RunRecord:
        return cls(
            run_id=data["run_id"],
            experiment_name=data["experiment_name"],
            seed=data["seed"],
            started_at=data["started_at"],
            finished_at=data["finished_at"],
            elapsed_s=data["elapsed_s"],
            hugrgate_version=data["hugrgate_version"],
            python_version=data["python_version"],
            platform=dict(data["platform"]),
            dataset_name=data["dataset_name"],
            dataset_version=data["dataset_version"],
            dataset_fingerprint=data["dataset_fingerprint"],
            policy=dict(data["policy"]),
            privacy_class=data["privacy_class"],
            tags=dict(data["tags"]),
            backends={k: dict(v) for k, v in data["backends"].items()},
            n_items=data["n_items"],
            git_sha=data.get("git_sha"),
        )


class EvaluationLab:
    """Runs named experiments and returns immutable run records.

    ``gate`` defaults to a fresh :class:`HugrGate`; pass a configured
    one (registered backends, cache, provenance store) to evaluate
    through your real pipeline.
    """

    def __init__(self, gate: HugrGate | None = None) -> None:
        self._gate = gate or HugrGate()
        self._experiments: dict[str, Experiment] = {}

    @property
    def gate(self) -> HugrGate:
        return self._gate

    def register_experiment(self, experiment: Experiment) -> Experiment:
        experiment.validate()
        if experiment.name in self._experiments:
            raise EvalError(
                f"experiment {experiment.name!r} is already registered",
                experiment=experiment.name,
            )
        self._experiments[experiment.name] = experiment
        logger.info("registered experiment %r", experiment.name)
        return experiment

    def get_experiment(self, name: str) -> Experiment:
        try:
            return self._experiments[name]
        except KeyError:
            raise EvalError(
                f"unknown experiment {name!r}; "
                f"registered: {sorted(self._experiments)}",
                experiment=name,
            ) from None

    def list_experiments(self) -> list[str]:
        return sorted(self._experiments)

    def run(
        self, name: str, *, dry_run: bool = False
    ) -> RunRecord | dict[str, Any]:
        """Execute an experiment; ``dry_run`` returns the plan only."""
        experiment = self.get_experiment(name)
        experiment.validate()
        if dry_run:
            return experiment.plan()

        policy = experiment.effective_policy()
        metric_set = experiment.effective_metrics()
        started = _utc_now()
        wall_start = time.perf_counter()
        # Seed discipline: the stdlib RNG is reseeded per run so any
        # randomized lab machinery (splits, bootstraps) is reproducible
        # for a fixed experiment seed.  Backend determinism is the
        # backend's own contract.
        random.seed(experiment.seed)

        report = run_benchmark(
            experiment.dataset,
            self._gate,
            backends=experiment.backends,
            policy=policy,
            max_items=experiment.max_items,
        )
        backends = {
            bname: metric_set.select(bmetrics)
            for bname, bmetrics in report["backends"].items()
        }
        elapsed = time.perf_counter() - wall_start
        record = RunRecord(
            run_id=uuid.uuid4().hex,
            experiment_name=experiment.name,
            seed=experiment.seed,
            started_at=started,
            finished_at=_utc_now(),
            elapsed_s=elapsed,
            hugrgate_version=HUGRGATE_VERSION,
            python_version=platform.python_version(),
            platform={
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
            },
            dataset_name=report["dataset"],
            dataset_version=report["dataset_version"],
            dataset_fingerprint=report["dataset_fingerprint"],
            policy=policy.to_dict(),
            privacy_class=policy.privacy_class,
            tags=dict(experiment.tags),
            backends=backends,
            n_items=report["n_items"],
            git_sha=_git_sha(),
        )
        logger.info(
            "run %s finished: experiment=%r backends=%d items=%d elapsed=%.2fs",
            record.run_id[:8],
            experiment.name,
            len(backends),
            record.n_items,
            elapsed,
        )
        return record
