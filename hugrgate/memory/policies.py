"""Contextual memory policies. Slice 307.

Not every decision deserves remembering. A :class:`MemoryPolicy` is
an ordered list of :class:`MemoryRule` objects evaluated against each
candidate record; the first matching rule wins and the default is to
record. Actions:

- ``"record"`` — remember the episode as-is;
- ``"drop"`` — do not remember it at all (``DecisionHistory.record``
  returns ``None``);
- ``"redact"`` — remember it, but strip the record's ``metadata``
  (state keys and other context) and mark the episode redacted.

Built-in factories cover the common cases; custom rules are plain
predicates over ``(record, privacy_class, tags)``. The
:func:`drop_forbidden` factory mirrors
:mod:`hugrgate.privacy_retention` — ``forbidden``-class decisions must
never persist — and :func:`redact_above` uses the existing privacy
ladder (:func:`hugrgate.privacy.at_least`) so policy authors think in
sensitivity levels, not string lists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from hugrgate.privacy import at_least
from hugrgate.provenance import DecisionRecord

__all__ = [
    "MemoryAction",
    "MemoryDecision",
    "MemoryPolicy",
    "MemoryRule",
    "drop_backend",
    "drop_forbidden",
    "drop_unaccepted",
    "record_only_backend",
    "redact_above",
]

#: What a memory rule may decree.
MemoryAction = Literal["record", "drop", "redact"]

ACTIONS: tuple[str, ...] = ("record", "drop", "redact")

#: A predicate over (record, privacy_class, tags) deciding a rule fires.
RulePredicate = Callable[[DecisionRecord, str, tuple[str, ...]], bool]


@dataclass(frozen=True)
class MemoryRule:
    """One named policy rule: predicate -> action + human reason."""

    name: str
    predicate: RulePredicate
    action: MemoryAction
    reason: str = ""

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(
                f"rule action must be one of {ACTIONS}, got "
                f"{self.action!r}")
        if not self.name:
            raise ValueError("rule name must be non-empty")


@dataclass(frozen=True)
class MemoryDecision:
    """The verdict of a :class:`MemoryPolicy` for one candidate."""

    action: MemoryAction
    rule: str  # rule name, or "default"
    reason: str = ""


class MemoryPolicy:
    """Ordered memory rules; first match wins, default is ``record``."""

    def __init__(self, rules: list[MemoryRule] | tuple[MemoryRule, ...]
                 = ()) -> None:
        names = [r.name for r in rules]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate rule names: {names}")
        self._rules = tuple(rules)

    def decide(self, record: DecisionRecord, privacy_class: str,
               tags: tuple[str, ...] = ()) -> MemoryDecision:
        """Evaluate rules in order; return the first firing verdict."""
        for rule in self._rules:
            if rule.predicate(record, privacy_class, tuple(tags)):
                return MemoryDecision(action=rule.action, rule=rule.name,
                                      reason=rule.reason)
        return MemoryDecision(action="record", rule="default",
                              reason="no rule fired")

    def explain(self) -> str:
        """Human-readable listing of the rules in evaluation order."""
        if not self._rules:
            return "MemoryPolicy(default=record)"
        lines = [f"MemoryPolicy({len(self._rules)} rules):"]
        for i, rule in enumerate(self._rules, 1):
            lines.append(f"  {i}. [{rule.action}] {rule.name}"
                         + (f" — {rule.reason}" if rule.reason else ""))
        lines.append("  default: [record]")
        return "\n".join(lines)


# -- built-in rule factories ------------------------------------------


def drop_forbidden() -> MemoryRule:
    """Drop ``forbidden``-class decisions: they must never persist."""
    return MemoryRule(
        name="drop-forbidden",
        predicate=lambda record, privacy_class, tags:
        privacy_class == "forbidden",
        action="drop",
        reason="forbidden privacy class must never be retained",
    )


def redact_above(privacy_class: str) -> MemoryRule:
    """Redact metadata for decisions at/above a sensitivity level."""
    return MemoryRule(
        name=f"redact-above-{privacy_class}",
        predicate=lambda record, cls, tags: at_least(cls, privacy_class),
        action="redact",
        reason=f"privacy class at least {privacy_class}: strip metadata",
    )


def drop_backend(*backends: str) -> MemoryRule:
    """Drop decisions served by the named backends."""
    names = frozenset(backends)
    return MemoryRule(
        name="drop-backend:" + ",".join(sorted(names)),
        predicate=lambda record, cls, tags: record.backend in names,
        action="drop",
        reason=f"backend in {sorted(names)} is not worth remembering",
    )


def record_only_backend(*backends: str) -> MemoryRule:
    """Drop decisions *not* served by the named backends."""
    names = frozenset(backends)
    return MemoryRule(
        name="record-only-backend:" + ",".join(sorted(names)),
        predicate=lambda record, cls, tags: record.backend not in names,
        action="drop",
        reason=f"only {sorted(names)} backends are worth remembering",
    )


def drop_unaccepted() -> MemoryRule:
    """Drop decisions the policy did not accept (abstentions etc.)."""
    return MemoryRule(
        name="drop-unaccepted",
        predicate=lambda record, cls, tags: not record.accepted,
        action="drop",
        reason="unaccepted decisions carry no acted-upon outcome",
    )
