"""Fairness hooks — disparity measurement across groups. Slice 369.

This module is measurement, not policy: the lab does not decide what
is fair.  It hooks into the stratified machinery (slice 356) and adds
the two classic lenses:

- **parity gaps**: max-minus-min of any metric across groups, plus
  the worst-off group and a ``flagged()`` query;
- **disparate impact** (categorical specs): per-option selection
  rates per group and the min/max ratio behind the four-fifths rule.

Groups smaller than ``min_group_size`` raise instead of producing
noise dressed as evidence — lower the bound explicitly if you know
what you are doing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, EvalError
from hugrgate.evlab.api import MetricSet
from hugrgate.evlab.stratified import StratifiedReport, stratified_evaluate
from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec

__all__ = [
    "FairnessReport",
    "fairness_evaluate",
]

_FOUR_FIFTHS = 0.8


@dataclass
class FairnessReport:
    """Group-parity measurements for every backend (slice 369)."""

    stratified: StratifiedReport
    group_key: str
    groups: list[str]
    group_sizes: dict[str, int]
    # backend -> option -> group -> selection rate
    selection_rates: dict[str, dict[str, dict[str, float]]]

    @property
    def backends(self) -> list[str]:
        seen: list[str] = []
        for stratum in self.stratified.per_stratum.values():
            for backend in stratum:
                if backend not in seen:
                    seen.append(backend)
        return seen

    def gap(
        self, backend: str, metric: str = "accuracy"
    ) -> float | None:
        """Max-minus-min of ``metric`` across groups (None when unscored)."""
        return self.stratified.disparity(backend, metric)

    def worst_group(
        self,
        backend: str,
        metric: str = "accuracy",
        higher_better: bool = True,
    ) -> tuple[str | None, float | None]:
        """(group, value) where ``backend`` scores worst on ``metric``."""
        return self.stratified.worst_stratum(backend, metric,
                                             higher_better)

    def flagged(
        self, metric: str = "accuracy", max_gap: float = 0.1
    ) -> list[tuple[str, float]]:
        """Backends whose group gap on ``metric`` exceeds ``max_gap``."""
        if max_gap < 0:
            raise EvalError(f"max_gap must be >= 0, got {max_gap}")
        out = []
        for backend in self.backends:
            gap = self.gap(backend, metric)
            if isinstance(gap, (int, float)) and gap > max_gap:
                out.append((backend, float(gap)))
        return sorted(out, key=lambda kv: kv[1], reverse=True)

    def disparate_impact_ratio(
        self, backend: str, option: str
    ) -> float | None:
        """min/max selection rate of ``option`` across groups.

        None when the backend has no selection data (non-categorical
        spec or no decisions).
        """
        rates = self.selection_rates.get(backend, {}).get(option)
        if not rates:
            return None
        values = [r for r in rates.values()
                  if isinstance(r, (int, float))]
        if not values or max(values) == 0:
            return None
        return min(values) / max(values)

    def passes_four_fifths(
        self, backend: str
    ) -> dict[str, bool] | None:
        """Per-option four-fifths check; None for non-categorical specs."""
        options = self.selection_rates.get(backend)
        if not options:
            return None
        return {
            option: (self.disparate_impact_ratio(backend, option)
                     or 0.0) >= _FOUR_FIFTHS
            for option in options
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "stratified": self.stratified.to_dict(),
            "group_key": self.group_key,
            "groups": list(self.groups),
            "group_sizes": dict(self.group_sizes),
            "selection_rates": {
                b: {o: dict(g) for o, g in options.items()}
                for b, options in self.selection_rates.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FairnessReport:
        return cls(
            stratified=StratifiedReport.from_dict(data["stratified"]),
            group_key=data["group_key"],
            groups=list(data["groups"]),
            group_sizes=dict(data["group_sizes"]),
            selection_rates={
                b: {o: dict(g) for o, g in options.items()}
                for b, options in data["selection_rates"].items()
            },
        )


def fairness_evaluate(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backends: Sequence[str] | None = None,
    group_key: str = "group",
    policy: DecisionPolicy | None = None,
    metrics: MetricSet | None = None,
    max_items: int | None = None,
    min_group_size: int = 10,
) -> FairnessReport:
    """Measure group-parity gaps and selection-rate impact per backend."""
    if not group_key:
        raise EvalError("group_key must be a non-empty string")
    if min_group_size < 1:
        raise EvalError(
            f"min_group_size must be >= 1, got {min_group_size}")
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    if not items:
        raise EvalError("fairness evaluation needs at least one item")

    groups: dict[str, list[Mapping[str, Any]]] = {}
    missing = 0
    for item in items:
        group = item.get(group_key)
        if group is None:
            missing += 1
            continue
        groups.setdefault(str(group), []).append(item)
    if missing:
        raise EvalError(
            f"{missing} item(s) are missing the group key "
            f"{group_key!r}; refusing to silently bucket them",
            n_missing=missing,
        )
    small = {g: len(v) for g, v in groups.items()
             if len(v) < min_group_size}
    if small:
        raise EvalError(
            "groups below min_group_size "
            f"{min_group_size}: {small}; fairness numbers on tiny "
            "groups are noise — lower min_group_size explicitly if "
            "you accept that",
            small_groups=small,
        )
    if len(groups) < 2:
        raise EvalError(
            f"fairness needs 2+ groups, found {len(groups)}")

    stratified = stratified_evaluate(
        dataset, gate, stratify_key=group_key, backends=backends,
        policy=policy, metrics=metrics, max_items=max_items,
    )
    policy = policy or DecisionPolicy()
    backend_names = list(stratified.aggregate)

    selection_rates: dict[str, dict[str, dict[str, float]]] = {}
    if spec.type == "categorical":
        options = [str(o) for o in (spec.options or [])]
        for backend in backend_names:
            counts: dict[str, dict[str, int]] = {
                o: {g: 0 for g in groups} for o in options}
            totals = dict.fromkeys(groups, 0)
            for group, members in groups.items():
                for item in members:
                    try:
                        result = gate.decide(dict(item["state"]), spec,
                                             policy,
                                             backend_name=backend)
                    except Abstention:
                        continue
                    totals[group] += 1
                    value = str(result.value)
                    if value in counts:
                        counts[value][group] += 1
            selection_rates[backend] = {
                option: {
                    group: (counts[option][group] / totals[group]
                            if totals[group] else 0.0)
                    for group in groups
                }
                for option in options
            }
    return FairnessReport(
        stratified=stratified,
        group_key=group_key,
        groups=sorted(groups),
        group_sizes={g: len(v) for g, v in groups.items()},
        selection_rates=selection_rates,
    )
