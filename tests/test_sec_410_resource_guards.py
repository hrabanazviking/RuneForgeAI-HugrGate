"""Slice 410 — resource-exhaustion guards.

RLIMIT_CPU / RLIMIT_AS enforcement with restoration, plus a
cooperative cost ledger for algorithmic-complexity hazards.
"""

from __future__ import annotations

import resource

import pytest

from hugrgate.errors import HugrGateError, ResourceBudgetExceeded
from hugrgate.security.resource_guards import (
    CostLedger,
    ResourceBudget,
    guarded,
    posix_available,
)

needs_posix = pytest.mark.skipif(
    not posix_available(), reason="POSIX rlimit enforcement unavailable")


def _rss() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


@needs_posix
def test_cpu_hog_interrupted():
    budget = ResourceBudget(max_cpu_seconds=1)
    with pytest.raises(ResourceBudgetExceeded) as exc:
        with guarded(budget):
            while True:
                pass
    assert exc.value.code == "resource_budget_exceeded"
    assert exc.value.details["limit"] == "max_cpu_seconds"


@needs_posix
def test_memory_hog_converted():
    cap = _rss() + 256 * 1024 * 1024
    budget = ResourceBudget(max_rss_bytes=cap)
    with pytest.raises(ResourceBudgetExceeded) as exc:
        with guarded(budget):
            blob = bytearray(1024 * 1024 * 1024)  # 1 GiB > cap
            assert len(blob) > 0
    assert exc.value.details["limit"] == "max_rss_bytes"


@needs_posix
def test_normal_work_passes_and_limits_restored():
    before_cpu = resource.getrlimit(resource.RLIMIT_CPU)
    before_as = resource.getrlimit(resource.RLIMIT_AS)
    # RLIMIT_CPU counts the process's *total* consumed CPU, not time
    # since the limit was armed. After a long suite run the process
    # may already exceed a small absolute budget, so arm the budget
    # relative to already-consumed CPU (slice 500 fix).
    usage = resource.getrusage(resource.RUSAGE_SELF)
    consumed = usage.ru_utime + usage.ru_stime
    budget = ResourceBudget(max_cpu_seconds=consumed + 60,
                            max_rss_bytes=_rss() + 1024**3)
    with guarded(budget):
        assert sum(range(100_000)) == 4999950000
    assert resource.getrlimit(resource.RLIMIT_CPU) == before_cpu
    assert resource.getrlimit(resource.RLIMIT_AS) == before_as


def test_cost_ledger_trips():
    ledger = CostLedger(10, name="fanout")
    assert ledger.charge(4) == 4
    assert ledger.remaining == 6
    with pytest.raises(ResourceBudgetExceeded) as exc:
        ledger.charge(7, what="batch item 3")
    assert exc.value.details["spent"] == 11
    assert exc.value.details["budget"] == 10
    assert exc.value.details["what"] == "batch item 3"


def test_cost_ledger_boundary():
    ledger = CostLedger(5)
    ledger.charge(5)  # exactly at budget: ok
    assert ledger.remaining == 0
    with pytest.raises(ResourceBudgetExceeded):
        ledger.charge(1)


def test_cost_ledger_rejects_bad_charges():
    ledger = CostLedger(5)
    with pytest.raises(ValueError):
        ledger.charge(-1)
    with pytest.raises(ValueError):
        CostLedger(0)


def test_budget_describe():
    desc = ResourceBudget(max_cpu_seconds=2.0).describe()
    assert desc["max_cpu_seconds"] == 2.0
    assert desc["enforced"] == posix_available()


def test_error_wire_round_trip():
    err = ResourceBudgetExceeded("too much", limit="x")
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert isinstance(rebuilt, ResourceBudgetExceeded)
