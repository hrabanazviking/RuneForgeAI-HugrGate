"""Slice 268 — retry budget tests."""

from __future__ import annotations

import threading

import pytest

from hugrgate.chaos import RetryBudget, default_retry_policy, retry_with_budget
from hugrgate.chaos.backend_faults import FaultSpec, FaultyBackend
from hugrgate.core import HugrGate
from hugrgate.errors import (
    BackendError,
    BackendUnavailable,
    RetryBudgetExhausted,
    SpecError,
    TimeoutError,
)
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _flaky(failures, exc):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] <= failures:
            raise exc(f"boom {calls['n']}")
        return "ok"
    return fn, calls


# --- budget mechanics ----------------------------------------------------------------------------------------

def test_budget_acquire_and_refill():
    clock = Clock()
    budget = RetryBudget(2, window_s=60.0, clock=clock)
    assert budget.remaining == 2
    assert budget.acquire() is True
    assert budget.acquire() is True
    assert budget.acquire() is False
    assert budget.remaining == 0
    clock.now += 59.9
    assert budget.acquire() is False  # window not lapsed yet
    clock.now += 0.2
    assert budget.acquire() is True  # refilled
    stats = budget.stats()
    assert stats == {"max_retries": 2, "remaining": 1,
                     "consumed_total": 3, "window_s": 60.0}


def test_budget_rejects_bad_arguments():
    with pytest.raises(SpecError):
        RetryBudget(-1)
    with pytest.raises(SpecError):
        RetryBudget(True)
    with pytest.raises(SpecError):
        RetryBudget(2, window_s=0)
    with pytest.raises(SpecError):
        retry_with_budget(lambda: 1, "not-a-budget")  # type: ignore[arg-type]


def test_budget_is_thread_safe():
    clock = Clock()
    budget = RetryBudget(100, clock=clock)
    acquired = []

    def worker():
        for _ in range(25):
            if budget.acquire():
                acquired.append(1)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(acquired) == 100  # exactly the budget, no over-issue


# --- retry executor --------------------------------------------------------------------------------------------

def test_retry_succeeds_within_budget():
    fn, calls = _flaky(2, BackendUnavailable)
    retries = []
    out = retry_with_budget(fn, RetryBudget(3),
                            on_retry=lambda n, e: retries.append((n, e)))
    assert out == "ok"
    assert calls["n"] == 3  # 1 attempt + 2 retries
    assert len(retries) == 2
    assert isinstance(retries[0][1], BackendUnavailable)


def test_retry_exhausted_raises_with_details():
    fn, _calls = _flaky(99, TimeoutError)
    with pytest.raises(RetryBudgetExhausted) as ei:
        retry_with_budget(fn, RetryBudget(2))
    err = ei.value
    assert err.details["attempts"] == 3  # 1 attempt + 2 retries
    assert err.details["last_error_code"] == "timeout"
    assert err.recoverable is True
    assert err.code == "retry_budget_exhausted"
    assert isinstance(err.__cause__, TimeoutError)
    assert isinstance(err, BackendError)  # flows through backend handlers


def test_non_retryable_errors_never_consume_budget():
    budget = RetryBudget(5)
    fn, calls = _flaky(1, SpecError)
    with pytest.raises(SpecError):
        retry_with_budget(fn, budget)
    assert calls["n"] == 1
    assert budget.remaining == 5


def test_custom_policy():
    fn, calls = _flaky(3, RuntimeError)
    out = retry_with_budget(fn, RetryBudget(5),
                            is_retryable=lambda e: isinstance(e, RuntimeError))
    assert out == "ok"
    assert calls["n"] == 4


def test_default_policy_retries_recoverable_taxonomy_only():
    assert default_retry_policy(BackendUnavailable("x")) is True
    assert default_retry_policy(TimeoutError("x")) is True
    assert default_retry_policy(SpecError("x")) is False
    assert default_retry_policy(BackendError("x")) is True  # recoverable
    assert default_retry_policy(ValueError("x")) is False
    assert default_retry_policy(RetryBudgetExhausted("x")) is False


# --- HugrGate.decide integration -------------------------------------------------------------------------------

def test_decide_without_budget_keeps_single_attempt():
    gate = HugrGate()
    flaky = FaultyBackend(StubBackend(name="flaky", value="a"))
    flaky.arm(FaultSpec(mode="error_rate", rate=1.0))
    gate.register(flaky)
    # No budget: the injected BackendError propagates unwrapped, one attempt.
    with pytest.raises(BackendError) as ei:
        gate.decide({}, DecisionSpec(type="categorical", options=["a", "b"]),
                    backend_name="flaky")
    assert not isinstance(ei.value, RetryBudgetExhausted)


def test_decide_with_budget_exhausts_then_reports():
    gate = HugrGate()
    flaky = FaultyBackend(StubBackend(name="flaky", value="a"))
    flaky.arm(FaultSpec(mode="error_rate", rate=1.0))
    gate.register(flaky)
    budget = RetryBudget(2)
    with pytest.raises(RetryBudgetExhausted) as ei:
        gate.decide({}, DecisionSpec(type="categorical", options=["a", "b"]),
                    backend_name="flaky", retry_budget=budget)
    assert ei.value.details["attempts"] == 3  # 1 attempt + 2 retries
    assert budget.remaining == 0


def test_decide_with_budget_succeeds_without_consuming():
    gate = HugrGate()
    gate.register(StubBackend(name="ok", value="b"))
    budget = RetryBudget(3)
    result = gate.decide({}, DecisionSpec(
        type="categorical", options=["a", "b"]),
        backend_name="ok", retry_budget=budget)
    assert result.accepted is True
    assert result.value == "b"
    assert budget.remaining == 3  # first attempt is always free


def test_decide_with_budget_rides_out_transient_fault():
    gate = HugrGate()
    flaky = FaultyBackend(StubBackend(name="flaky", value="a"))
    flaky.arm(FaultSpec(mode="error_rate", rate=1.0))
    gate.register(flaky)

    calls = {"n": 0}
    faulty_evaluate = flaky.evaluate

    def sometimes(state, spec, context=None):
        calls["n"] += 1
        if calls["n"] > 1:
            flaky.disarm("error_rate")  # fault was transient; healthy now
        return faulty_evaluate(state, spec, context)

    flaky.evaluate = sometimes  # type: ignore[method-assign]
    budget = RetryBudget(3)
    result = gate.decide({}, DecisionSpec(
        type="categorical", options=["a", "b"]),
        backend_name="flaky", retry_budget=budget)
    assert result.accepted is True
    assert result.value == "a"
    assert budget.remaining == 2  # exactly one retry consumed
