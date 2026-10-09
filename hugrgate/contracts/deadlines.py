"""Decision deadlines — temporal bounds on decisions. Gjallarbrú slice 040.

Backend latency has a policy knob (`maximum_latency_ms`), but the
*decision itself* carries no temporal contract: nothing says "decide
within 500 ms of the request" or "this decision is only valid during the
trading window". :class:`TimedContract` (kind ``"timed"``) wraps any
inner contract with:

- ``budget_ms`` — the decision must be produced within this many
  milliseconds of the request;
- ``not_before`` / ``not_after`` — absolute unix-timestamp window in
  which the decision may be made (and remains valid).

Value validation delegates to the inner contract; temporal validation is
explicit and clock-injectable (``now`` parameters default to
``time.time()``), so every rule is deterministically testable.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from hugrgate.contracts.schema import (
    DecisionContract,
    contract_from_dict,
    register_kind,
)
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec

__all__ = [
    "TimedContract",
]

#: What may sit inside a TimedContract.
InnerContract = DecisionContract | DecisionSpec


def _check_ts(value: Any, *, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{what} must be a unix timestamp number, "
                            f"got {value!r}", code="bad_timestamp")
    return float(value)


@register_kind
@dataclass
class TimedContract(DecisionContract):
    """Any contract with temporal bounds (kind ``"timed"``)."""

    kind: ClassVar[str] = "timed"

    inner: InnerContract = None  # type: ignore[assignment]
    budget_ms: float | None = None
    not_before: float | None = None
    not_after: float | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.inner, (DecisionContract, DecisionSpec)):
            raise ContractError(
                "timed contract needs an inner DecisionContract or "
                f"DecisionSpec, got {type(self.inner).__name__}",
                code="bad_inner_contract")
        if self.budget_ms is not None:
            if (isinstance(self.budget_ms, bool)
                    or not isinstance(self.budget_ms, (int, float))
                    or self.budget_ms <= 0):
                raise ContractError("budget_ms must be > 0",
                                    code="bad_budget")
            self.budget_ms = float(self.budget_ms)
        if self.not_before is not None:
            self.not_before = _check_ts(self.not_before, what="not_before")
        if self.not_after is not None:
            self.not_after = _check_ts(self.not_after, what="not_after")
        if (self.not_before is not None and self.not_after is not None
                and not self.not_before < self.not_after):
            raise ContractError("not_before must be < not_after",
                                code="bad_window")
        if (self.budget_ms is None and self.not_before is None
                and self.not_after is None):
            raise ContractError(
                "timed contract needs at least one temporal bound "
                "(budget_ms, not_before, not_after)",
                code="no_temporal_bound")

    # -- value validation (delegated) ----------------------------------------

    def validate_value(self, value: Any) -> None:
        inner = self.inner
        assert isinstance(inner, (DecisionContract, DecisionSpec))
        if isinstance(inner, DecisionContract):
            inner.validate_value(value)
        else:
            from hugrgate.contracts.composite import _validate_spec_value
            _validate_spec_value(inner, value, field_name="value")

    # -- temporal validation ---------------------------------------------------

    def timing_violations(self, request_ts: float,
                          decided_ts: float) -> list[str]:
        """Was the decision *made* within its temporal bounds?"""
        problems: list[str] = []
        request_ts = _check_ts(request_ts, what="request_ts")
        decided_ts = _check_ts(decided_ts, what="decided_ts")
        if decided_ts < request_ts:
            problems.append(
                f"decided_ts {decided_ts} precedes request_ts {request_ts}")
        if self.budget_ms is not None:
            elapsed_ms = (decided_ts - request_ts) * 1000.0
            if elapsed_ms > self.budget_ms:
                problems.append(
                    f"decision took {elapsed_ms:.1f}ms, budget "
                    f"{self.budget_ms:.1f}ms")
        if self.not_before is not None and decided_ts < self.not_before:
            problems.append(
                f"decided at {decided_ts}, before not_before "
                f"{self.not_before}")
        if self.not_after is not None and decided_ts > self.not_after:
            problems.append(
                f"decided at {decided_ts}, after not_after {self.not_after}")
        return problems

    def check_timing(self, request_ts: float, decided_ts: float) -> None:
        """Raise ContractError aggregating every timing violation."""
        problems = self.timing_violations(request_ts, decided_ts)
        if problems:
            raise ContractError(
                f"{len(problems)} deadline violation(s):\n" +
                "\n".join(f"  - {p}" for p in problems),
                code="deadline_violation", violations=problems)

    def is_valid_at(self, now: float | None = None) -> bool:
        """Is a decision still *valid* at ``now`` (window check)?"""
        now = time.time() if now is None else _check_ts(now, what="now")
        if self.not_before is not None and now < self.not_before:
            return False
        if self.not_after is not None and now > self.not_after:
            return False
        return True

    def remaining_budget_ms(self, request_ts: float,
                            now: float | None = None) -> float | None:
        """Milliseconds of budget left at ``now`` (None when no budget)."""
        if self.budget_ms is None:
            return None
        now = time.time() if now is None else _check_ts(now, what="now")
        request_ts = _check_ts(request_ts, what="request_ts")
        return self.budget_ms - (now - request_ts) * 1000.0

    # -- serialization -----------------------------------------------------------

    @staticmethod
    def _inner_to_dict(inner: InnerContract) -> dict[str, Any]:
        if isinstance(inner, DecisionContract):
            return inner.to_dict()
        return {"decision_spec": inner.to_dict()}

    @staticmethod
    def _inner_from_dict(d: Any) -> InnerContract:
        if not isinstance(d, dict):
            raise ContractError("inner contract payload must be a dict",
                                code="bad_inner_contract")
        if "kind" in d:
            return contract_from_dict(d)
        if "decision_spec" in d:
            return DecisionSpec.from_dict(d["decision_spec"])
        if "type" in d:
            return DecisionSpec.from_dict(d)
        raise ContractError(
            f"inner payload needs 'kind' or 'decision_spec'/'type', got "
            f"{sorted(d)}", code="bad_inner_contract")

    def _payload_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"inner": self._inner_to_dict(self.inner)}
        if self.budget_ms is not None:
            d["budget_ms"] = self.budget_ms
        if self.not_before is not None:
            d["not_before"] = self.not_before
        if self.not_after is not None:
            d["not_after"] = self.not_after
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> TimedContract:
        raw = d.get("inner")
        if raw is None:
            raise ContractError("timed payload needs 'inner'",
                                code="missing_inner")
        return cls(inner=cls._inner_from_dict(raw),
                   budget_ms=d.get("budget_ms"),
                   not_before=d.get("not_before"),
                   not_after=d.get("not_after"), **common)

    def describe(self) -> str:
        parts = []
        if self.budget_ms is not None:
            parts.append(f"budget {self.budget_ms:g}ms")
        if self.not_before is not None or self.not_after is not None:
            parts.append(f"window [{self.not_before}, {self.not_after}]")
        inner = self.inner
        inner_kind = (inner.kind if isinstance(inner, DecisionContract)
                      else f"spec/{inner.type}")
        return (f"timed contract {self.name or self.contract_id!r}: "
                f"{inner_kind}; " + "; ".join(parts))
