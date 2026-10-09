"""Rule backend — predicates, decision tables, confidence distributions.

Slices 11-13: a deterministic backend that evaluates predicate rules
against the decision state.

Slice 11 — predicates:
    {"if": {"field": "temperature", "gt": 90},
     "then": "critical", "confidence": 0.99}
Operators: eq, ne, gt, gte, lt, lte, in, contains, exists.
First-match wins.

Slice 12 — decision tables:
Rows of conditions -> outcome, explicit priority ordering, a default
rule, and YAML-loadable rule sets::

    rules:
      - name: critical-malware
        priority: 100
        if:
          all:
            - {field: severity, gte: 8}
            - {field: category, eq: malware}
        then: escalate
        confidence: 0.97
      - {default: log, confidence: 0.5}

Slice 13 — confidence & distribution:
The matched rule's confidence becomes the winner's probability; the
remainder (1 - confidence) is split uniformly across the other options
of the spec's value space. supports(): categorical, binary, ordinal.

Missing-field semantics (documented, pinned by tests):
  - eq / in / contains / gt / gte / lt / lte on a missing field -> False
  - ne on a missing field -> True ("not equal" includes absent)
  - exists -> True iff the field is present (or per explicit flag)
Comparison type errors (e.g. gt between str and int) never match.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

import yaml

from hugrgate.backend import Backend
from hugrgate.errors import Abstention, BackendError, BackendUnavailable, SpecError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "OPERATORS",
    "Rule",
    "RuleBackend",
]

OPERATORS = ("eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "exists")

_MISSING = object()


def _get_field(state: Mapping[str, Any], dotted: str) -> Any:
    """Resolve a dotted field path (``source.ip``) against nested dicts."""
    current: Any = state
    for part in str(dotted).split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def _eval_predicate(cond: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    # Compatibility: also accept the nested predicate shape
    # {"temperature": {"gt": 90}} alongside the flat shape
    # {"field": "temperature", "gt": 90}. Purely additive — flat shapes
    # are untouched.
    if "field" not in cond and len(cond) == 1:
        ((only_key, only_val),) = cond.items()
        if (isinstance(only_val, Mapping)
                and only_val
                and all(k in OPERATORS for k in only_val)):
            cond = {"field": only_key, **dict(only_val)}
    field_name = cond.get("field")
    if field_name is None:
        raise SpecError(f"predicate needs a 'field': {cond!r}")

    # Operator may be given as a key ({"field": "t", "gt": 90})
    # or explicitly ({"field": "t", "op": "gt", "value": 90}).
    op = cond.get("op")
    value = cond.get("value", _MISSING)
    if op is None:
        for candidate in OPERATORS:
            if candidate in cond:
                op = candidate
                value = cond[candidate]
                break
    if op is None:
        raise SpecError(f"predicate needs an operator {OPERATORS}: {cond!r}")
    if op not in OPERATORS:
        raise SpecError(f"unknown operator {op!r}", valid=OPERATORS)

    actual = _get_field(state, field_name)

    if op == "exists":
        expected = True if value is _MISSING else bool(value)
        return (actual is not _MISSING) == expected
    if actual is _MISSING:
        # Documented missing-field semantics: only ne matches absence.
        return op == "ne"
    if op == "eq":
        return actual == value
    if op == "ne":
        return actual != value
    if op == "in":
        try:
            return actual in value
        except TypeError:
            return False
    if op == "contains":
        try:
            return value in actual
        except TypeError:
            return False
    # Ordered comparisons: type errors never match.
    try:
        if op == "gt":
            return actual > value
        if op == "gte":
            return actual >= value
        if op == "lt":
            return actual < value
        if op == "lte":
            return actual <= value
    except TypeError:
        return False
    raise SpecError(f"unhandled operator {op!r}")  # pragma: no cover


def _eval_condition(cond: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    """Evaluate a condition: predicate or all/any/not composition."""
    if "all" in cond:
        sub = cond["all"]
        if not isinstance(sub, (list, tuple)):
            raise SpecError("'all' needs a list of conditions")
        return all(_eval_condition(c, state) for c in sub)
    if "any" in cond:
        sub = cond["any"]
        if not isinstance(sub, (list, tuple)):
            raise SpecError("'any' needs a list of conditions")
        return any(_eval_condition(c, state) for c in sub)
    if "not" in cond:
        return not _eval_condition(cond["not"], state)
    return _eval_predicate(cond, state)


@dataclass
class Rule:
    """A single decision rule.

    ``condition`` is None for a default rule (always matches; evaluated
    after every non-default rule regardless of priority).
    """
    condition: Optional[Dict[str, Any]]
    then: Any
    confidence: float = 1.0
    priority: int = 0
    name: Optional[str] = None

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise SpecError(
                f"rule confidence must be in [0,1], got {self.confidence}")
        if self.condition is not None and not isinstance(self.condition, dict):
            raise SpecError("rule condition must be a mapping")

    @property
    def is_default(self) -> bool:
        return self.condition is None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Rule":
        if not isinstance(d, Mapping):
            raise SpecError(f"rule must be a mapping, got {d!r}")
        if "default" in d:
            condition = None
            then = d["default"]
        elif "if" in d:
            condition = dict(d["if"])
            then = d.get("then")
        elif "when" in d:
            condition = dict(d["when"])
            then = d.get("then")
        else:
            raise SpecError(
                f"rule needs 'if'/'when' or 'default': {d!r}")
        if then is None:
            raise SpecError(f"rule needs a 'then' outcome: {d!r}")
        return cls(
            condition=condition,
            then=then,
            confidence=float(d.get("confidence", 1.0)),
            priority=int(d.get("priority", 0)),
            name=d.get("name"),
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"then": self.then,
                             "confidence": self.confidence,
                             "priority": self.priority}
        if self.name:
            d["name"] = self.name
        if self.is_default:
            d["default"] = self.then
            del d["then"]
        else:
            d["if"] = self.condition
        return d

    def matches(self, state: Mapping[str, Any]) -> bool:
        condition = self.condition
        if condition is None:
            return True
        return _eval_condition(condition, state)


class RuleBackend(Backend):
    """Deterministic predicate-rule backend.

    Rules are evaluated in priority order (higher ``priority`` first;
    declaration order breaks ties). The first matching rule wins.
    Default rules (``{"default": outcome}``) are always evaluated last.
    """

    def __init__(self, rules: Optional[List[Rule]] = None,
                 name: str = "rules", model_name: str = "ruleset"):
        self.name = name
        self.model_name = model_name
        self._rules: List[Rule] = list(rules or [])
        # Priority order: non-default rules sorted by (-priority, order),
        # then default rules in declaration order.
        ordered: List[Rule] = []
        defaults: List[Rule] = []
        for rule in self._rules:
            (defaults if rule.is_default else ordered).append(rule)
        ordered.sort(key=lambda r: -r.priority)  # stable: ties keep order
        self._ordered: List[Rule] = ordered + defaults

    # -- construction helpers ------------------------------------------------
    @classmethod
    def from_rules(cls, rules: List[Rule], **kwargs) -> "RuleBackend":
        return cls(rules=rules, **kwargs)

    @classmethod
    def from_dicts(cls, dicts: List[Mapping[str, Any]],
                   **kwargs) -> "RuleBackend":
        return cls(rules=[Rule.from_dict(d) for d in dicts], **kwargs)

    @classmethod
    def from_yaml_text(cls, text: str, **kwargs) -> "RuleBackend":
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise SpecError(f"invalid YAML rule set: {e}")
        return cls._from_yaml_data(data, **kwargs)

    @classmethod
    def from_yaml_file(cls, path: str, **kwargs) -> "RuleBackend":
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SpecError(f"invalid YAML rule set in {path}: {e}")
        return cls._from_yaml_data(data, **kwargs)

    @classmethod
    def _from_yaml_data(cls, data: Any, **kwargs) -> "RuleBackend":
        if isinstance(data, Mapping) and "rules" in data:
            name = data.get("name", kwargs.pop("name", "rules"))
            return cls.from_dicts(list(data["rules"]), name=name, **kwargs)
        if isinstance(data, list):
            return cls.from_dicts(data, **kwargs)
        raise SpecError("YAML rule set must be a list or a "
                        "{name, rules} mapping")

    def to_dicts(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._rules]

    # -- Backend contract -----------------------------------------------------
    def capabilities(self) -> Dict[str, Any]:
        return {
            "spec_types": ["categorical", "binary", "ordinal"],
            "deterministic": True,
            "rule_count": len(self._rules),
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in ("categorical", "binary", "ordinal")

    def estimated_latency(self) -> float:
        return 2.0  # ms: rule evaluation is cheap

    def health(self) -> Dict[str, Any]:
        return {"status": "ok", "backend": self.name,
                "rules": len(self._rules)}

    def _normalize_outcome(self, outcome: Any,
                           spec: DecisionSpec) -> Any:
        if spec.type == "binary" and isinstance(outcome, bool):
            return "true" if outcome else "false"
        return outcome

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Optional[Mapping[str, Any]] = None
                 ) -> DecisionResult:
        start = time.perf_counter()
        if not self.supports(spec):
            raise BackendUnavailable(
                f"RuleBackend does not support spec type {spec.type!r}")

        matched: Optional[Rule] = None
        matched_index: int = -1
        for i, rule in enumerate(self._ordered):
            if rule.matches(state):
                matched = rule
                matched_index = i
                break

        if matched is None:
            raise Abstention(
                "no rule matched and no default rule is defined",
                reason="no_rule_matched",
                backend=self.name,
                rules=len(self._rules))

        outcome = self._normalize_outcome(matched.then, spec)
        space = spec.value_space()
        if outcome not in space:
            raise BackendError(
                f"rule {matched.name or matched_index!r} outcome "
                f"{outcome!r} is outside the spec value space {space}")

        confidence = max(0.0, min(1.0, matched.confidence))
        distribution = self._distribution(space, outcome, confidence)

        result = DecisionResult(
            value=outcome,
            probability=confidence,
            distribution=distribution,
            uncertainty=1.0 - confidence,
            backend=self.name,
            model=self.model_name,
            latency_ms=(time.perf_counter() - start) * 1000,
            metadata={
                "matched_rule": matched.name or f"rule_{matched_index}",
                "rule_index": matched_index,
                "default_used": matched.is_default,
                "rule_count": len(self._rules),
            },
        )
        return result

    @staticmethod
    def _distribution(space: List[str], winner: Any,
                      confidence: float) -> Dict[str, float]:
        """Winner gets confidence; the remainder is split uniformly."""
        others = [o for o in space if o != winner]
        dist = {winner: confidence}
        share = (1.0 - confidence) / len(others) if others else 0.0
        for o in others:
            dist[o] = share
        # Renormalize against float drift so the sum is exactly ~1.
        total = sum(dist.values())
        if total > 0:
            dist = {k: v / total for k, v in dist.items()}
        return dist

    def __len__(self) -> int:
        return len(self._rules)
