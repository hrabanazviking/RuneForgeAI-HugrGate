"""Fuzzing campaign harness. Slice 422.

Threat T-16: malformed JSON/compact encodings crash serde or
validation instead of raising taxonomy errors. This module is the
reusable harness; the campaign itself lives in the test suite,
which fuzzes the real parsers (``DecisionSpec.from_dict``,
``policy_from_dict``/``result_from_dict``, the compact codecs,
``validate_state``, and the security detectors).

Design (stdlib only, seeded for reproducibility — the same
convention as the slice-247 privacy fuzz):

- :class:`FuzzTarget` wraps a callable and classifies each case:
  ``ok``, ``taxonomy_error`` (an expected :class:`HugrGateError`
  or other *declared* exception), ``crash`` (anything else), or
  ``hang`` (per-case timeout exceeded).
- :func:`run_campaign` drives a generator for ``n_cases`` with a
  fixed seed, runs each case in a worker thread with a timeout,
  and returns a :class:`FuzzReport` with the crash corpus
  (deduplicated by exception type + message) and reproduction
  seeds.
- Generators: :func:`hostile_values` (nested hostile scalars),
  :func:`hostile_json_texts` (malformed JSON), :func:`hostile_states`.
"""

from __future__ import annotations

import json
import random
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import HugrGateError

__all__ = [
    "FuzzReport",
    "FuzzTarget",
    "hostile_json_texts",
    "hostile_states",
    "hostile_values",
    "run_campaign",
]


@dataclass
class Crash:
    seed: int
    case_index: int
    input_repr: str
    exc_type: str
    message: str

    @property
    def signature(self) -> str:
        return f"{self.exc_type}: {self.message[:160]}"


@dataclass
class FuzzReport:
    target_name: str
    cases: int
    ok: int = 0
    taxonomy_errors: int = 0
    hangs: int = 0
    crashes: list[Crash] = field(default_factory=list)

    @property
    def unique_crashes(self) -> list[Crash]:
        seen: set[str] = set()
        unique: list[Crash] = []
        for crash in self.crashes:
            if crash.signature not in seen:
                seen.add(crash.signature)
                unique.append(crash)
        return unique

    def summary(self) -> dict[str, Any]:
        return {
            "target": self.target_name,
            "cases": self.cases,
            "ok": self.ok,
            "taxonomy_errors": self.taxonomy_errors,
            "hangs": self.hangs,
            "crashes": len(self.unique_crashes),
        }


class FuzzTarget:
    """A callable under fuzz with declared (non-crash) exceptions."""

    def __init__(self, name: str, fn: Callable[[Any], Any],
                 allowed: tuple[type[BaseException], ...] = ()) -> None:
        self.name = name
        self.fn = fn
        # HugrGateError is always taxonomy, never a crash; callers
        # add stdlib parsing errors (JSONDecodeError, ...) as needed.
        self.allowed: tuple[type[BaseException], ...] = (
            HugrGateError, *allowed)


def _run_one(target: FuzzTarget, case: Any,
             timeout_s: float) -> tuple[str, BaseException | None]:
    outcome: list[tuple[str, BaseException | None]] = []

    def worker() -> None:
        try:
            target.fn(case)
        except BaseException as e:  # noqa: BLE001 - classification
            if isinstance(e, target.allowed):
                outcome.append(("taxonomy_error", e))
            else:
                outcome.append(("crash", e))
        else:
            outcome.append(("ok", None))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        return "hang", None
    return outcome[0]


def run_campaign(target: FuzzTarget,
                 generator: Callable[[random.Random], Any],
                 n_cases: int = 500, seed: int = 20261009,
                 timeout_s: float = 5.0) -> FuzzReport:
    """Fuzz ``target`` with ``n_cases`` generated inputs."""
    report = FuzzReport(target_name=target.name, cases=n_cases)
    rng = random.Random(seed)
    for index in range(n_cases):
        case_seed = rng.randrange(2 ** 32)
        case_rng = random.Random(case_seed)
        case = generator(case_rng)
        try:
            input_repr = repr(case)[:300]
        except Exception:  # noqa: BLE001 - repr must never break fuzz
            input_repr = "<unrepresentable>"
        outcome, exc = _run_one(target, case, timeout_s)
        if outcome == "ok":
            report.ok += 1
        elif outcome == "taxonomy_error":
            report.taxonomy_errors += 1
        elif outcome == "hang":
            report.hangs += 1
        else:
            assert exc is not None
            report.crashes.append(Crash(
                seed=case_seed, case_index=index,
                input_repr=input_repr,
                exc_type=type(exc).__name__,
                message=str(exc)[:500] + "\n" +
                "".join(traceback.format_tb(exc.__traceback__, limit=3))))
    return report


# -- generators ----------------------------------------------------

_HOSTILE_WORDS = [
    "", "x", "null", "true", "NaN", "Infinity", "-Infinity",
    "üñîçødé", "a" * 10_000, "\x00\x01\x02", "\n\r\t",
    "{{{{", "[[[[", '"', "'", "\\", "${jndi:ldap://x}",
    "__proto__", "constructor", "prototype",
]


def hostile_values(rng: random.Random, depth: int = 0) -> Any:
    """One hostile scalar / container, nested up to depth 4."""
    choice = rng.randrange(12)
    if choice < 4:
        return rng.choice(_HOSTILE_WORDS)
    if choice == 4:
        return rng.choice([0, -1, 2 ** 63, -(2 ** 63) - 1,
                           1.5, float("nan"), float("inf"),
                           10 ** 400, -(10 ** 400)])
    if choice == 5:
        return rng.choice([True, False, None])
    if choice == 6:
        return [hostile_values(rng, depth + 1)
                for _ in range(rng.randrange(6))] if depth < 4 else []
    if choice == 7:
        return {f"k{i}": hostile_values(rng, depth + 1)
                for i in range(rng.randrange(5))} if depth < 4 else {}
    if choice == 8:
        return (hostile_values(rng, depth + 1),
                hostile_values(rng, depth + 1))
    if choice == 9:
        return {rng.randrange(3), "s", None}
    if choice == 10:
        return b"\x00\xff binary"
    return float(rng.randrange(-100, 100))


def hostile_states(rng: random.Random) -> Any:
    """Hostile decision-state candidates (not always dicts)."""
    if rng.random() < 0.2:
        return hostile_values(rng)
    state: dict[str, Any] = {}
    for _ in range(rng.randrange(8)):
        key = rng.choice(["text", "x", "", "a" * 500, "__proto__",
                          "options", "type", "spec"])
        state[key] = hostile_values(rng)
    return state


def hostile_json_texts(rng: random.Random) -> str:
    """Malformed JSON texts plus hostile-but-valid JSON."""
    choice = rng.randrange(10)
    if choice < 5:
        fragments = ['{"a":', '{"a": 1,', "[1, 2,", '{"a": undefined}',
                     "{'a': 1}", '{"a": 01}', '{"a": NaN}',
                     '{"a": ' + '"x" * 5000, ', ""]
        text = rng.choice(fragments)
        if rng.random() < 0.5:
            text += rng.choice(_HOSTILE_WORDS)
        return text
    return json.dumps(hostile_values(rng), default=str)
