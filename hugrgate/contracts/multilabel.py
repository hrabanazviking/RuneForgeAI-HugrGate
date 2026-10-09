"""Multilabel cardinality constraints — how many, which, with what.

Gjallarbrú slice 036.

Hierarchical contracts (slice 029) validate *membership* of label sets.
They say nothing about *shape*: "pick 1-3", "exactly 2", "'urgent' is
mandatory", "'a' and 'c' never co-occur", "'x' implies 'y'".
:class:`MultilabelContract` (kind ``"multilabel-cardinality"``) adds:

- ``min_count`` / ``max_count`` / ``exact_count`` (exact wins when set);
- ``required`` / ``forbidden`` label lists;
- ``implies``: selecting a label requires its consequents;
- ``excludes``: selecting a label forbids its antagonists (symmetrized at
  construction — exclusion is inherently mutual).

All violations aggregate into a single error; construction rejects
incoherent rule sets (e.g. a label both required and forbidden).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "MultilabelContract",
]


def _label_list(values: Any, *, what: str) -> list[str]:
    if not isinstance(values, list):
        raise ContractError(f"'{what}' must be a list", code="bad_label_list")
    for v in values:
        if not isinstance(v, str) or not v:
            raise ContractError(f"'{what}' labels must be non-empty strings",
                                code="bad_label_list")
    if len(set(values)) != len(values):
        raise ContractError(f"'{what}' labels must be unique",
                            code="bad_label_list")
    return list(values)


@register_kind
@dataclass
class MultilabelContract(DecisionContract):
    """Label-set decisions with cardinality and co-occurrence rules."""

    kind: ClassVar[str] = "multilabel-cardinality"

    labels: list[str] = field(default_factory=list)
    min_count: int = 0
    max_count: int = 0  # 0 = no upper bound... see __post_init__
    exact_count: int = -1  # -1 = unset
    required: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    implies: dict[str, list[str]] = field(default_factory=dict)
    excludes: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.labels = _label_list(self.labels, what="labels")
        if not self.labels:
            raise ContractError("multilabel contract needs ≥1 label",
                                code="no_labels")
        n = len(self.labels)
        for name in ("min_count", "max_count", "exact_count"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int):
                raise ContractError(f"{name} must be an int",
                                    code="bad_cardinality")
        if self.min_count < 0 or self.max_count < 0:
            raise ContractError("min/max_count must be ≥ 0",
                                code="bad_cardinality")
        if self.max_count and self.max_count < self.min_count:
            raise ContractError("max_count < min_count",
                                code="bad_cardinality")
        if self.max_count and self.max_count > n:
            raise ContractError("max_count exceeds label count",
                                code="bad_cardinality")
        if self.min_count > n:
            raise ContractError("min_count exceeds label count",
                                code="bad_cardinality")
        if self.exact_count != -1:
            if not 0 <= self.exact_count <= n:
                raise ContractError("exact_count out of range",
                                    code="bad_cardinality")
        self.required = _label_list(self.required, what="required")
        self.forbidden = _label_list(self.forbidden, what="forbidden")
        for lbl in self.required:
            if lbl not in self.labels:
                raise ContractError(f"required label {lbl!r} not in labels",
                                    code="rule_on_unknown_label")
        for lbl in self.forbidden:
            if lbl not in self.labels:
                raise ContractError(f"forbidden label {lbl!r} not in labels",
                                    code="rule_on_unknown_label")
        clash = set(self.required) & set(self.forbidden)
        if clash:
            raise ContractError(
                f"labels both required and forbidden: {sorted(clash)}",
                code="required_forbidden_clash")
        self.implies = self._check_map(self.implies, "implies",
                                       allow_self=False)
        self.excludes = self._symmetrize(self._check_map(
            self.excludes, "excludes", allow_self=False))
        if self.exact_count != -1:
            if len(self.required) > self.exact_count:
                raise ContractError(
                    "more required labels than exact_count",
                    code="required_exceeds_exact")
        # required labels must not exclude each other
        for lbl in self.required:
            bad = [e for e in self.excludes.get(lbl, []) if e in self.required]
            if bad:
                raise ContractError(
                    f"required label {lbl!r} excludes required {bad}",
                    code="required_excludes_required")

    def _check_map(self, m: Any, what: str,
                   allow_self: bool) -> dict[str, list[str]]:
        if not isinstance(m, dict):
            raise ContractError(f"'{what}' must be a dict",
                                code="bad_rule_map")
        out: dict[str, list[str]] = {}
        for k, vs in m.items():
            if k not in self.labels:
                raise ContractError(
                    f"{what} key {k!r} not in labels",
                    code="rule_on_unknown_label")
            vs = _label_list(vs, what=f"{what}[{k}]")
            for v in vs:
                if v not in self.labels:
                    raise ContractError(
                        f"{what}[{k!r}] references unknown label {v!r}",
                        code="rule_on_unknown_label")
                if not allow_self and v == k:
                    raise ContractError(
                        f"{what}[{k!r}] cannot reference itself",
                        code="rule_self_reference")
            out[k] = vs
        return out

    @staticmethod
    def _symmetrize(m: dict[str, list[str]]) -> dict[str, list[str]]:
        """Exclusion is mutual: a→b implies b→a."""
        out = {k: list(v) for k, v in m.items()}
        for k, vs in m.items():
            for v in vs:
                out.setdefault(v, [])
                if k not in out[v]:
                    out[v].append(k)
        return {k: sorted(v) for k, v in out.items() if v}

    # -- validation ----------------------------------------------------------

    def violations(self, value: Any) -> list[str]:
        """Every cardinality/co-occurrence problem (possibly empty)."""
        problems: list[str] = []
        if isinstance(value, str) or not isinstance(value, (list, tuple)):
            return [f"multilabel value must be a list, got "
                    f"{type(value).__name__}"]
        labels = list(value)
        unknown = [lbl for lbl in labels if lbl not in self.labels]
        if unknown:
            problems.append(f"unknown labels: {unknown}")
        if len(set(labels)) != len(labels):
            problems.append(f"duplicate labels: {labels}")
        known = [lbl for lbl in labels if lbl in self.labels]
        count = len(known)
        if self.exact_count != -1:
            if count != self.exact_count:
                problems.append(
                    f"need exactly {self.exact_count} labels, got {count}")
        else:
            if count < self.min_count:
                problems.append(
                    f"need ≥{self.min_count} labels, got {count}")
            if self.max_count and count > self.max_count:
                problems.append(
                    f"need ≤{self.max_count} labels, got {count}")
        missing_req = [lbl for lbl in self.required if lbl not in known]
        if missing_req:
            problems.append(f"missing required labels: {missing_req}")
        present_forbidden = [lbl for lbl in self.forbidden if lbl in known]
        if present_forbidden:
            problems.append(
                f"forbidden labels present: {present_forbidden}")
        seen_pairs = set()
        for lbl in known:
            for need in self.implies.get(lbl, []):
                if need not in known:
                    problems.append(
                        f"{lbl!r} implies {need!r}, which is missing")
            for foe in self.excludes.get(lbl, []):
                if foe in known:
                    pair = tuple(sorted((lbl, foe)))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        problems.append(
                            f"{pair[0]!r} excludes {pair[1]!r}; both present")
        return problems

    def validate_value(self, value: Any) -> None:
        problems = self.violations(value)
        if problems:
            raise ContractError(
                f"{len(problems)} multilabel violation(s):\n" +
                "\n".join(f"  - {p}" for p in problems),
                code="multilabel_violation", violations=problems)

    # -- serialization ---------------------------------------------------------

    def _payload_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"labels": list(self.labels)}
        if self.exact_count != -1:
            d["exact_count"] = self.exact_count
        else:
            if self.min_count:
                d["min_count"] = self.min_count
            if self.max_count:
                d["max_count"] = self.max_count
        if self.required:
            d["required"] = list(self.required)
        if self.forbidden:
            d["forbidden"] = list(self.forbidden)
        if self.implies:
            d["implies"] = {k: list(v) for k, v in self.implies.items()}
        if self.excludes:
            # Persist the symmetrized form: canonical and round-trips.
            d["excludes"] = {k: list(v) for k, v in self.excludes.items()}
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> MultilabelContract:
        labels = d.get("labels")
        if not isinstance(labels, list):
            raise ContractError("multilabel payload needs a 'labels' list",
                                code="missing_labels")
        kwargs: dict[str, Any] = {
            "labels": labels,
            "min_count": d.get("min_count", 0),
            "max_count": d.get("max_count", 0),
            "exact_count": d.get("exact_count", -1),
            "required": d.get("required", []),
            "forbidden": d.get("forbidden", []),
            "implies": d.get("implies", {}),
            "excludes": d.get("excludes", {}),
        }
        return cls(**kwargs, **common)

    def describe(self) -> str:
        if self.exact_count != -1:
            card = f"exactly {self.exact_count}"
        else:
            hi = self.max_count or "∞"
            card = f"{self.min_count}..{hi}"
        rules = (f", {len(self.required)} required, {len(self.forbidden)} "
                 f"forbidden, {len(self.implies)} implies, "
                 f"{len(self.excludes)} excludes")
        return (f"multilabel-cardinality contract "
                f"{self.name or self.contract_id!r}: {len(self.labels)} "
                f"labels, count {card}{rules}")
