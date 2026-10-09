"""Contract fuzzing — seeded random contracts, invariant checking.

Gjallarbrú slice 049.

Hand-written tests prove the engine handles the cases we thought of.
The fuzzer hunts the ones we didn't: it builds random contracts from a
seeded RNG, throws random values at them, and checks invariants that
must hold for *every* contract — dict round-trips, ``validate_value``
soundness on in-space values, canonical-hash stability, and a
non-empty ``describe()``.

Everything is deterministic: the same seed always produces the same
contracts, the same values, and the same report, so a failure is a
reproduction recipe, not a ghost.

>>> from hugrgate.contracts.fuzz import fuzz
>>> report = fuzz(seed=42, cases_per_kind=50)
>>> report.failures
[]
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from hugrgate.contracts.cost import CostSensitiveContract
from hugrgate.contracts.distributions import (
    DistributionConstraint,
    DistributionContract,
)
from hugrgate.contracts.multilabel import MultilabelContract
from hugrgate.contracts.nested import NestedCategoricalContract
from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.schema import DecisionContract, contract_from_dict
from hugrgate.contracts.uncertainty import NumericIntervalContract
from hugrgate.errors import ContractError, SpecError

__all__ = [
    "FUZZ_KINDS",
    "FuzzReport",
    "fuzz",
    "random_contract",
    "random_invalid_value",
    "random_valid_distribution",
    "random_valid_value",
]

_WORDS = ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta",
          "theta", "iota", "kappa")


def _words(rng: random.Random, lo: int, hi: int) -> List[str]:
    n = rng.randint(lo, hi)
    return rng.sample(list(_WORDS), n)


def _cid(rng: random.Random) -> str:
    return f"fuzz-{rng.randrange(1 << 30):08x}"


def _fuzz_nested(rng: random.Random, _depth: int = 0) -> NestedCategoricalContract:
    options = _words(rng, 1, 4)
    children = {}
    for opt in options:
        if _depth < 2 and rng.random() < 0.4:
            children[opt] = _fuzz_nested(rng, _depth + 1)
    return NestedCategoricalContract(contract_id=_cid(rng),
                                     options=options, children=children)


def _fuzz_ordinal(rng: random.Random) -> OrdinalContract:
    levels = _words(rng, 2, 5)
    kw: Dict[str, Any] = {}
    if rng.random() < 0.5:
        pos = sorted(rng.random() for _ in levels)
        kw["anchors"] = {l: p for l, p in zip(levels, pos)}
    return OrdinalContract(contract_id=_cid(rng), levels=levels, **kw)


def _fuzz_numeric(rng: random.Random) -> NumericIntervalContract:
    lo = rng.uniform(-100.0, 100.0)
    hi = lo + rng.uniform(0.01, 200.0)
    kw: Dict[str, Any] = {}
    if rng.random() < 0.4:
        kw["max_width"] = rng.uniform(0.01, hi - lo)
    return NumericIntervalContract(contract_id=_cid(rng), minimum=lo,
                                   maximum=hi, **kw)


def _fuzz_multilabel(rng: random.Random) -> MultilabelContract:
    labels = _words(rng, 2, 5)
    kw: Dict[str, Any] = {}
    if rng.random() < 0.5:
        kw["min_count"] = rng.randint(0, len(labels) - 1)
    if rng.random() < 0.5:
        kw["max_count"] = rng.randint(kw.get("min_count", 0), len(labels))
    return MultilabelContract(contract_id=_cid(rng), labels=labels, **kw)


def _fuzz_cost(rng: random.Random) -> CostSensitiveContract:
    outcomes = _words(rng, 2, 3)
    costs = {a: {b: (0.0 if a == b else round(rng.uniform(0, 100), 2))
                 for b in outcomes}
             for a in outcomes}
    return CostSensitiveContract(contract_id=_cid(rng), outcomes=outcomes,
                                 costs=costs)


def _fuzz_distribution(rng: random.Random) -> DistributionContract:
    outcomes = _words(rng, 2, 4)
    constraints = []
    if rng.random() < 0.5:
        labels = rng.sample(outcomes, rng.randint(1, len(outcomes)))
        constraints.append(DistributionConstraint(
            op="min_mass", threshold=round(rng.uniform(0.1, 0.9), 2),
            labels=tuple(labels)))
    return DistributionContract(contract_id=_cid(rng), outcomes=outcomes,
                                constraints=constraints)


_GENERATORS: Dict[str, Callable[[random.Random], DecisionContract]] = {
    "nested-categorical": _fuzz_nested,
    "ordinal": _fuzz_ordinal,
    "numeric-interval": _fuzz_numeric,
    "multilabel-cardinality": _fuzz_multilabel,
    "cost-sensitive": _fuzz_cost,
    "distribution": _fuzz_distribution,
}

#: Kinds the fuzzer can generate.
FUZZ_KINDS = tuple(sorted(_GENERATORS))


def random_contract(rng: random.Random,
                    kind: Optional[str] = None) -> DecisionContract:
    """Build one random contract; ``kind`` pins the generator."""
    if kind is None:
        kind = rng.choice(FUZZ_KINDS)
    if kind not in _GENERATORS:
        raise ContractError(f"fuzzer has no generator for kind {kind!r}",
                            code="bad_fuzz_kind")
    return _GENERATORS[kind](rng)


def _nested_leaves(c: NestedCategoricalContract) -> List[str]:
    return [".".join(path) for path in c.leaf_paths()]


def random_valid_value(rng: random.Random,
                       contract: DecisionContract) -> Any:
    """Draw a value from inside the contract's accepted space."""
    if isinstance(contract, NestedCategoricalContract):
        return rng.choice(_nested_leaves(contract))
    if isinstance(contract, OrdinalContract):
        return rng.choice(contract.levels)
    if isinstance(contract, NumericIntervalContract):
        return rng.uniform(contract.minimum, contract.maximum)
    if isinstance(contract, MultilabelContract):
        labels = list(contract.labels)
        lo = contract.min_count or 0
        hi = contract.max_count or len(labels)  # 0 = no upper bound
        n = rng.randint(lo, hi)
        return rng.sample(labels, n)
    if isinstance(contract, CostSensitiveContract):
        return rng.choice(contract.outcomes)
    if isinstance(contract, DistributionContract):
        # validate_value takes a single outcome; full distributions go
        # through validate_distribution (see random_valid_distribution).
        return rng.choice(contract.outcomes)
    raise ContractError(f"fuzzer cannot sample kind {contract.kind!r}",
                        code="bad_fuzz_kind")


def random_valid_distribution(rng: random.Random,
                              contract: DistributionContract) -> Dict[str, float]:
    """Draw a full distribution satisfying the contract's constraints."""
    outcomes = list(contract.outcomes)
    weights = {o: rng.random() + 0.01 for o in outcomes}
    for con in contract.constraints:
        if con.op != "min_mass":
            continue
        labels = [lab for lab in con.labels if lab in weights]
        others = [o for o in outcomes if o not in labels]
        target = min(con.threshold + 0.05, 1.0)
        total = sum(weights.values())
        mass = sum(weights[lab] for lab in labels) / total
        if mass < target:
            labels_sum = sum(weights[lab] for lab in labels)
            others_sum = total - labels_sum
            if target >= 1.0 or not others:
                for lab in labels:
                    weights[lab] = 1.0 / len(labels)
                for o in others:
                    weights[o] = 0.0
            else:
                factor = (target / (1.0 - target)) * (others_sum
                                                     / labels_sum)
                for lab in labels:
                    weights[lab] *= factor
    total = sum(weights.values())
    return {o: weights[o] / total for o in outcomes}


def random_invalid_value(rng: random.Random,
                         contract: DecisionContract) -> Any:
    """Draw a value likely outside the contract's accepted space.

    Best-effort: acceptance of one of these is recorded as a warning,
    not a failure — the generator is heuristic, the contract is truth.
    """
    cands: List[Any] = [None, object(),  object, ["nested", "list"],
                        {"a": "dict"}, "zzz-no-such-outcome",
                        -1e18, 1e18, float("nan")]
    if isinstance(contract, NumericIntervalContract):
        span = contract.maximum - contract.minimum
        cands.append(contract.minimum - span - 1.0)
        cands.append(contract.maximum + span + 1.0)
    return rng.choice(cands)


@dataclass
class FuzzReport:
    """What one fuzz run did and found."""

    seed: int
    cases: int
    invariants: int
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def describe(self) -> str:
        head = (f"fuzz seed={self.seed}: {self.cases} cases, "
                f"{self.invariants} invariant checks, "
                f"{len(self.failures)} failure(s), "
                f"{len(self.warnings)} warning(s)")
        lines = [head]
        lines.extend(f"  FAILURE: {f}" for f in self.failures)
        lines.extend(f"  warning: {w}" for w in self.warnings)
        return "\n".join(lines)


def _check_invariants(contract: DecisionContract, label: str,
                      report: FuzzReport) -> None:
    """Assert the universal contract invariants; record failures."""
    d = contract.to_dict()
    # 1. dict round-trip
    try:
        back = contract_from_dict(d)
        if back.to_dict() != d:
            report.failures.append(
                f"{label}: round-trip dict mismatch for "
                f"{contract.contract_id}")
        report.invariants += 1
    except (ContractError, SpecError) as e:
        report.failures.append(
            f"{label}: round-trip raised for {contract.contract_id}: {e}")
        return
    # 2. canonical hash stability
    try:
        if back.canonical_hash() != contract.canonical_hash():
            report.failures.append(
                f"{label}: hash drift for {contract.contract_id}")
        report.invariants += 1
    except (ContractError, SpecError) as e:
        report.failures.append(
            f"{label}: hash raised for {contract.contract_id}: {e}")
    # 3. describe() non-empty
    try:
        if not contract.describe():
            report.failures.append(
                f"{label}: empty describe() for {contract.contract_id}")
        report.invariants += 1
    except (ContractError, SpecError) as e:
        report.failures.append(
            f"{label}: describe() raised for {contract.contract_id}: {e}")


def fuzz(seed: int, cases_per_kind: int = 25,
         values_per_case: int = 5) -> FuzzReport:
    """Run the fuzzer: random contracts, random values, invariant checks.

    Deterministic in ``seed``. Failures carry the seed and case label so
    rerunning reproduces them exactly.
    """
    if cases_per_kind < 1:
        raise ContractError("cases_per_kind must be ≥ 1",
                            code="bad_fuzz_config")
    rng = random.Random(seed)
    report = FuzzReport(seed=seed, cases=0, invariants=0)
    for kind in FUZZ_KINDS:
        for i in range(cases_per_kind):
            label = f"{kind}#{i}"
            try:
                contract = random_contract(rng, kind)
            except (ContractError, SpecError) as e:
                report.failures.append(f"{label}: generator raised: {e}")
                continue
            report.cases += 1
            _check_invariants(contract, label, report)
            # 4. validate_value soundness on in-space values
            for j in range(values_per_case):
                try:
                    value = random_valid_value(rng, contract)
                except (ContractError, SpecError) as e:
                    report.failures.append(
                        f"{label}: value sampler raised: {e}")
                    break
                try:
                    contract.validate_value(value)
                    report.invariants += 1
                except (ContractError, SpecError) as e:
                    report.failures.append(
                        f"{label}: in-space value {value!r} rejected: {e}")
            # 5. invalid values are *usually* rejected (advisory)
            for _ in range(values_per_case):
                bad = random_invalid_value(rng, contract)
                try:
                    contract.validate_value(bad)
                    report.warnings.append(
                        f"{label}: heuristic-invalid value {bad!r} "
                        f"accepted")
                except (ContractError, SpecError, TypeError, ValueError):
                    report.invariants += 1
            # 6. distributions satisfy their own health constraints
            if isinstance(contract, DistributionContract):
                try:
                    dist = random_valid_distribution(rng, contract)
                    contract.validate_distribution(dist)
                    report.invariants += 1
                except (ContractError, SpecError) as e:
                    report.failures.append(
                        f"{label}: sampled distribution rejected: {e}")
    return report
