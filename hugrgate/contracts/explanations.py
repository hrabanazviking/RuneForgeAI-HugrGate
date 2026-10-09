"""Output explanation contracts — decisions must show their work.

Gjallarbrú slice 043.

Explanations currently live as ad-hoc ``DecisionResult.metadata`` keys:
nothing requires one, nothing checks its shape, and nothing verifies it
even mentions the decided value. :class:`ExplanationContract` (kind
``"explanation"``) contracts the explanation itself:

- ``required_fields`` — keys the explanation mapping must carry;
- ``text_field`` / ``min_length`` — the narrative and its minimum length;
- ``reasons_field`` / ``min_reasons`` — a structured reason list with a
  minimum count;
- ``must_mention_value`` — faithfulness: the text must name the decided
  value (every element, for collection values), case-insensitively;
- ``forbidden_phrases`` — strings that must not appear (case-insensitive).

:func:`check_result` / :meth:`ExplanationContract.check_result` pull the
value and the explanation (``metadata["explanation"]``) straight off a
:class:`DecisionResult`, so existing results validate without modification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Mapping

from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError
from hugrgate.result import DecisionResult

__all__ = [
    "EXPLANATION_METADATA_KEY",
    "ExplanationContract",
]

#: DecisionResult.metadata key holding the explanation mapping.
EXPLANATION_METADATA_KEY = "explanation"


def _as_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def _mentioned(needle: str, haystack_lower: str) -> bool:
    """Word-boundary, case-insensitive mention check.

    Plain substring matching would count "b" as mentioned in "label";
    word boundaries keep faithfulness honest.
    """
    return re.search(r"\b" + re.escape(needle.lower()) + r"\b",
                     haystack_lower) is not None


@register_kind
@dataclass
class ExplanationContract(DecisionContract):
    """What a decision's explanation must contain (kind ``"explanation"``)."""

    kind: ClassVar[str] = "explanation"

    required_fields: List[str] = field(default_factory=list)
    text_field: str = "text"
    min_length: int = 0
    reasons_field: str = "reasons"
    min_reasons: int = 0
    must_mention_value: bool = True
    forbidden_phrases: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("required_fields", "forbidden_phrases"):
            vs = getattr(self, name)
            if not isinstance(vs, list):
                raise ContractError(f"'{name}' must be a list",
                                    code="bad_explanation_contract")
            if any(not isinstance(v, str) or not v for v in vs):
                raise ContractError(f"'{name}' must hold non-empty strings",
                                    code="bad_explanation_contract")
            setattr(self, name, list(vs))
        for name in ("text_field", "reasons_field"):
            v = getattr(self, name)
            if not isinstance(v, str) or not v:
                raise ContractError(f"'{name}' must be a non-empty string",
                                    code="bad_explanation_contract")
        for name in ("min_length", "min_reasons"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ContractError(f"'{name}' must be an int ≥ 0",
                                    code="bad_explanation_contract")
        if not isinstance(self.must_mention_value, bool):
            raise ContractError("'must_mention_value' must be a bool",
                                code="bad_explanation_contract")

    # -- validation ----------------------------------------------------------

    def violations(self, value: Any, explanation: Any) -> List[str]:
        """Every explanation problem (possibly empty)."""
        problems: List[str] = []
        if isinstance(explanation, str) or not isinstance(
                explanation, Mapping):
            return [f"explanation must be a mapping, got "
                    f"{type(explanation).__name__}"]
        for f in self.required_fields:
            if f not in explanation:
                problems.append(f"explanation missing field: {f!r}")
        text = explanation.get(self.text_field, "")
        if self.text_field in explanation or self.min_length or \
                self.must_mention_value or self.forbidden_phrases:
            if not isinstance(text, str) or not text:
                problems.append(
                    f"explanation[{self.text_field!r}] must be a non-empty "
                    f"string")
                text = ""
            elif len(text) < self.min_length:
                problems.append(
                    f"explanation text length {len(text)} < min_length "
                    f"{self.min_length}")
        if self.min_reasons:
            reasons = explanation.get(self.reasons_field, [])
            if not isinstance(reasons, (list, tuple)):
                problems.append(
                    f"explanation[{self.reasons_field!r}] must be a list")
            else:
                good = [r for r in reasons
                        if isinstance(r, str) and r.strip()]
                if len(good) < self.min_reasons:
                    problems.append(
                        f"explanation needs ≥{self.min_reasons} reasons, "
                        f"got {len(good)}")
        lowered = text.lower() if isinstance(text, str) else ""
        if self.must_mention_value and text:
            missing = [s for s in _as_list(value)
                       if not _mentioned(s, lowered)]
            if missing:
                problems.append(
                    f"explanation does not mention decided value(s): "
                    f"{missing}")
        for phrase in self.forbidden_phrases:
            if phrase.lower() in lowered:
                problems.append(
                    f"explanation contains forbidden phrase: {phrase!r}")
        return problems

    def validate_explanation(self, value: Any, explanation: Any) -> None:
        """Raise ContractError aggregating every explanation problem."""
        problems = self.violations(value, explanation)
        if problems:
            raise ContractError(
                f"{len(problems)} explanation violation(s):\n" +
                "\n".join(f"  - {p}" for p in problems),
                code="explanation_violation", violations=problems)

    def validate_value(self, value: Any) -> None:
        # The contract governs explanations, not decision values; any
        # JSON-serializable value is acceptable here.
        super().validate_value(value)

    def check_result(self, result: DecisionResult) -> List[str]:
        """Validate the explanation attached to a DecisionResult."""
        if not isinstance(result, DecisionResult):
            raise ContractError(
                f"check_result needs a DecisionResult, got "
                f"{type(result).__name__}", code="bad_result")
        return self.violations(result.value,
                               result.metadata.get(EXPLANATION_METADATA_KEY))

    def validate_result(self, result: DecisionResult) -> None:
        """Raise on any explanation problem in a DecisionResult."""
        problems = self.check_result(result)
        if problems:
            raise ContractError(
                f"{len(problems)} explanation violation(s):\n" +
                "\n".join(f"  - {p}" for p in problems),
                code="explanation_violation", violations=problems)

    # -- serialization -----------------------------------------------------------

    def _payload_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.required_fields:
            d["required_fields"] = list(self.required_fields)
        if self.text_field != "text":
            d["text_field"] = self.text_field
        if self.min_length:
            d["min_length"] = self.min_length
        if self.reasons_field != "reasons":
            d["reasons_field"] = self.reasons_field
        if self.min_reasons:
            d["min_reasons"] = self.min_reasons
        if not self.must_mention_value:
            d["must_mention_value"] = False
        if self.forbidden_phrases:
            d["forbidden_phrases"] = list(self.forbidden_phrases)
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: Dict[str, Any]) -> "ExplanationContract":
        return cls(
            required_fields=d.get("required_fields", []),
            text_field=d.get("text_field", "text"),
            min_length=d.get("min_length", 0),
            reasons_field=d.get("reasons_field", "reasons"),
            min_reasons=d.get("min_reasons", 0),
            must_mention_value=d.get("must_mention_value", True),
            forbidden_phrases=d.get("forbidden_phrases", []),
            **common)

    def describe(self) -> str:
        bits = [f"{len(self.required_fields)} required field(s)"]
        if self.min_length:
            bits.append(f"text ≥ {self.min_length} chars")
        if self.min_reasons:
            bits.append(f"≥ {self.min_reasons} reasons")
        if self.must_mention_value:
            bits.append("must mention value")
        return (f"explanation contract {self.name or self.contract_id!r}: "
                + ", ".join(bits))
