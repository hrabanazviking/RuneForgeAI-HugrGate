"""Gjallarbrú slice 049 — contract fuzzing."""

from __future__ import annotations

import random

import pytest

from hugrgate.contracts.distributions import DistributionContract
from hugrgate.contracts.fuzz import (
    FUZZ_KINDS,
    FuzzReport,
    fuzz,
    random_contract,
    random_invalid_value,
    random_valid_distribution,
    random_valid_value,
)
from hugrgate.contracts.multilabel import MultilabelContract
from hugrgate.contracts.nested import NestedCategoricalContract
from hugrgate.errors import ContractError

# --- the fuzzer finds nothing (the engine holds) -------------------------------

@pytest.mark.parametrize("seed", [42, 7, 1234, 99, 2026])
def test_fuzz_passes_fixed_seeds(seed):
    report = fuzz(seed=seed, cases_per_kind=20)
    assert report.passed, report.describe()
    assert report.cases == len(FUZZ_KINDS) * 20
    # every case ran several invariant checks
    assert report.invariants > report.cases * 4


def test_fuzz_covers_all_kinds():
    seen = set()
    rng = random.Random(11)
    for _ in range(200):
        seen.add(random_contract(rng).kind)
    assert seen == set(FUZZ_KINDS)


# --- determinism -----------------------------------------------------------------

def test_fuzz_deterministic():
    assert fuzz(seed=5, cases_per_kind=10).describe() == \
        fuzz(seed=5, cases_per_kind=10).describe()


def test_fuzz_seeds_differ():
    a = fuzz(seed=5, cases_per_kind=10)
    b = fuzz(seed=6, cases_per_kind=10)
    assert a.describe() != b.describe()


# --- samplers ----------------------------------------------------------------------

def test_valid_values_pass_validation():
    rng = random.Random(3)
    for _ in range(60):
        c = random_contract(rng)
        c.validate_value(random_valid_value(rng, c))  # must not raise


def test_valid_distributions_satisfy_constraints():
    rng = random.Random(9)
    for _ in range(40):
        c = random_contract(rng, "distribution")
        assert isinstance(c, DistributionContract)
        dist = random_valid_distribution(rng, c)
        assert abs(sum(dist.values()) - 1.0) < 1e-6
        c.validate_distribution(dist)  # must not raise


def test_invalid_values_usually_rejected():
    rng = random.Random(13)
    rejected = 0
    total = 0
    for _ in range(60):
        c = random_contract(rng)
        bad = random_invalid_value(rng, c)
        total += 1
        try:
            c.validate_value(bad)
        except (ContractError, TypeError, ValueError):
            rejected += 1
    assert rejected / total > 0.8


def test_multilabel_sampler_respects_unbounded_max():
    rng = random.Random(0)  # first draw has min_count=2, max_count=0
    c = random_contract(rng, "multilabel-cardinality")
    assert isinstance(c, MultilabelContract)
    for _ in range(20):
        v = random_valid_value(rng, c)
        c.validate_value(v)


def test_nested_sampler_draws_leaf_paths():
    rng = random.Random(21)
    for _ in range(30):
        c = random_contract(rng, "nested-categorical")
        assert isinstance(c, NestedCategoricalContract)
        v = random_valid_value(rng, c)
        c.validate_value(v)


# --- report / guards ---------------------------------------------------------------

def test_report_api():
    r = FuzzReport(seed=1, cases=10, invariants=50)
    assert r.passed and "seed=1" in r.describe()
    r.failures.append("boom")
    assert not r.passed and "FAILURE" in r.describe()


def test_fuzz_guards():
    with pytest.raises(ContractError):
        fuzz(seed=1, cases_per_kind=0)
    with pytest.raises(ContractError):
        random_contract(random.Random(1), kind="nope")
