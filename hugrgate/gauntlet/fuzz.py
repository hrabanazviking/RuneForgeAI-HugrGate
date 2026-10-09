"""Public-interface fuzzer (slice 489).

Privacy (slice 247) and security (slice 422) already fuzz their own
corners; this module is the *generic* harness: enumerate public
entry points, feed them seeded garbage (hostile shapes included —
huge strings, deep nesting, NaN/Inf, wrong types), and prove that
only documented exception kinds ever escape.

A public function may raise:

- any :class:`hugrgate.errors.HugrGateError` (the taxonomy), or
- stdlib validation errors: ``ValueError``, ``TypeError``,
  ``KeyError``, ``AttributeError``, ``NotImplementedError``.

Anything else (``IndexError``, ``ZeroDivisionError``,
``RecursionError``, ``SystemExit``, ...) is recorded as an
*unexpected* escape — a robustness bug, since callers cannot be
expected to catch what the contract never names.

:func:`fuzz_targets` runs the curated 1.0 target list;
:func:`fuzz_callable` fuzzes one function; both are deterministic
for a fixed seed.
"""

from __future__ import annotations

import random
import sys
import traceback
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import HugrGateError

__all__ = [
    "ALLOWED_EXCEPTIONS",
    "FuzzReport",
    "fuzz_callable",
    "fuzz_targets",
    "generate_garbage",
]

#: Exception kinds a public interface may raise on hostile input.
ALLOWED_EXCEPTIONS: tuple[type[BaseException], ...] = (
    HugrGateError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    NotImplementedError,
)

_MAX_STRING = 10_000
_MAX_DEPTH = 6


def generate_garbage(rng: random.Random, depth: int = 0) -> Any:
    """One hostile value: scalars, containers, wrong types, extremes."""
    if depth > _MAX_DEPTH:
        return None
    choice = rng.randrange(14)
    if choice == 0:
        return None
    if choice == 1:
        return rng.choice([True, False])
    if choice == 2:
        return rng.choice([0, 1, -1, 2**63 - 1, -(2**63), 10**100])
    if choice == 3:
        return rng.choice([0.0, -1.5, float("nan"), float("inf"),
                           float("-inf"), 1e-300, 1e300])
    if choice == 4:
        n = rng.choice([0, 1, 16, _MAX_STRING])
        alphabet = rng.choice(["x", "\u0000", "\U0001f525", "é", "%s", "{}"])
        return alphabet * n
    if choice == 5:
        return bytes(rng.randrange(256) for _ in range(rng.randrange(8)))
    if choice == 6:
        return [generate_garbage(rng, depth + 1)
                for _ in range(rng.randrange(5))]
    if choice == 7:
        return {f"k{i}": generate_garbage(rng, depth + 1)
                for i in range(rng.randrange(4))}
    if choice == 8:
        return tuple(generate_garbage(rng, depth + 1)
                     for _ in range(rng.randrange(4)))
    if choice == 9:
        out: set[Any] = set()
        for _ in range(rng.randrange(3)):
            try:
                out.add(generate_garbage(rng, depth + 1))
            except TypeError:
                pass  # unhashable garbage has no place in a set
        return out
    if choice == 10:
        # Deeply nested hostile shape.
        nested: Any = "bottom"
        for _ in range(_MAX_DEPTH):
            nested = [nested]
        return nested
    if choice == 11:
        return rng.choice([object(), Ellipsis, NotImplemented])
    if choice == 12:
        return {"type": "categorical", "options": ["a"],
                "__proto__": "pollution", "constructor": 1}
    return rng.choice(["", "null", "undefined", "NaN", "0", "-0"])


@dataclass
class FuzzReport:
    """Outcome of fuzzing one callable."""

    target: str
    cases: int
    ok_cases: int = 0
    allowed_raises: int = 0
    unexpected: tuple[tuple[str, str], ...] = ()

    @property
    def clean(self) -> bool:
        return not self.unexpected

    def raise_if_dirty(self) -> None:
        if self.unexpected:
            kinds = sorted({k for k, _ in self.unexpected})
            sample = self.unexpected[0][1].splitlines()[-1]
            raise AssertionError(
                f"fuzz found unexpected escapes in {self.target}: "
                f"{kinds} (e.g. {sample})"
            )


def _fuzz_one(func: Any, args: list[Any]
              ) -> tuple[str, tuple[str, str] | None]:
    """Run one case: returns ("ok"/"allowed", None) or ("unexpected",
    (kind, traceback))."""
    try:
        func(*args)
        return "ok", None
    except ALLOWED_EXCEPTIONS:
        return "allowed", None
    except BaseException:  # noqa: BLE001 - the finding IS the except
        kind = type(sys.exc_info()[1]).__name__
        return "unexpected", (kind, traceback.format_exc())


def fuzz_callable(func: Any, *, seed: int = 489, cases: int = 300,
                  name: str | None = None) -> FuzzReport:
    """Fuzz one callable with seeded garbage; deterministic per seed."""
    rng = random.Random(seed)
    label = name if name is not None else str(
        getattr(func, "__qualname__", repr(func)))
    report = FuzzReport(target=label, cases=cases)
    unexpected: list[tuple[str, str]] = []
    for _ in range(cases):
        argc = rng.choice([1, 1, 1, 2, 3])
        args = [generate_garbage(rng) for _ in range(argc)]
        outcome, detail = _fuzz_one(func, args)
        if outcome == "ok":
            report.ok_cases += 1
        elif outcome == "allowed":
            report.allowed_raises += 1
        else:
            assert detail is not None
            unexpected.append(detail)
    report.unexpected = tuple(unexpected)
    return report


def fuzz_targets(*, seed: int = 489, cases: int = 300) -> list[FuzzReport]:
    """Fuzz the curated 1.0 entry-point list.

    Targets are the data-facing public functions most likely to meet
    hostile input: spec/policy/result (de)serialization and state
    validation. Deterministic per seed.
    """
    from hugrgate.serde import (
        policy_from_compact,
        policy_from_dict,
        result_from_compact,
        result_from_dict,
    )
    from hugrgate.spec import DecisionSpec
    from hugrgate.validation import validate_state

    targets = [
        (DecisionSpec.from_dict, "DecisionSpec.from_dict"),
        (policy_from_dict, "policy_from_dict"),
        (policy_from_compact, "policy_from_compact"),
        (result_from_dict, "result_from_dict"),
        (result_from_compact, "result_from_compact"),
        (validate_state, "validate_state"),
    ]
    return [fuzz_callable(func, seed=seed, cases=cases, name=name)
            for func, name in targets]
