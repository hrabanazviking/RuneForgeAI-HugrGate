"""Slice 269 — bulkhead (per-backend concurrency caps) tests."""

from __future__ import annotations

import threading
import time

import pytest

from hugrgate.chaos import (
    BulkheadExecutor,
    RetryBudget,
    default_retry_policy,
    retry_with_budget,
)
from hugrgate.core import HugrGate
from hugrgate.errors import BackendError, BulkheadRejected, SpecError
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


# --- cap mechanics -------------------------------------------------------------------------------------------

def test_fail_fast_when_full():
    ex = BulkheadExecutor(default_cap=1)
    entered = threading.Event()
    release = threading.Event()

    def hold():
        entered.set()
        release.wait(5)
        return "held"

    t = threading.Thread(target=lambda: ex.execute("slow", hold))
    t.start()
    assert entered.wait(5)
    with pytest.raises(BulkheadRejected) as ei:
        ex.execute("slow", lambda: "nope")
    err = ei.value
    assert err.details["backend_name"] == "slow"
    assert err.details["cap"] == 1
    assert err.code == "bulkhead_rejected"
    assert err.recoverable is True
    assert isinstance(err, BackendError)
    release.set()
    t.join(5)
    assert ex.execute("slow", lambda: "ok") == "ok"  # lane freed


def test_backends_are_isolated():
    ex = BulkheadExecutor(default_cap=1)
    entered = threading.Event()
    release = threading.Event()

    def hold():
        entered.set()
        release.wait(5)
        return "held"

    t = threading.Thread(target=lambda: ex.execute("slow", hold))
    t.start()
    assert entered.wait(5)
    # A different backend is unaffected by slow's full bulkhead.
    assert ex.execute("fast", lambda: "fast-ok") == "fast-ok"
    release.set()
    t.join(5)


def test_per_backend_caps():
    ex = BulkheadExecutor(default_cap=4, caps={"tiny": 1})
    assert ex.cap_for("tiny") == 1
    assert ex.cap_for("other") == 4
    entered = threading.Event()
    release = threading.Event()

    def hold():
        entered.set()
        release.wait(5)
    t = threading.Thread(target=lambda: ex.execute("tiny", hold))
    t.start()
    assert entered.wait(5)
    with pytest.raises(BulkheadRejected):
        ex.execute("tiny", lambda: None)
    # default-cap backend still has room for several concurrent calls
    assert ex.execute("other", lambda: 1) == 1
    release.set()
    t.join(5)


def test_timeout_waits_for_a_lane():
    ex = BulkheadExecutor(default_cap=1)
    release = threading.Event()

    def hold():
        release.wait(5)
        return "held"
    t = threading.Thread(target=lambda: ex.execute("slow", hold))
    t.start()
    time.sleep(0.05)
    release.set()  # free the lane while the next call waits
    assert ex.execute("slow", lambda: "waited", timeout_s=5.0) == "waited"
    t.join(5)


def test_timeout_expires_into_rejection():
    ex = BulkheadExecutor(default_cap=1)
    entered = threading.Event()
    release = threading.Event()

    def hold():
        entered.set()
        release.wait(5)
    t = threading.Thread(target=lambda: ex.execute("slow", hold))
    t.start()
    assert entered.wait(5)
    start = time.monotonic()
    with pytest.raises(BulkheadRejected):
        ex.execute("slow", lambda: None, timeout_s=0.2)
    assert time.monotonic() - start < 2.0  # did not wait forever
    release.set()
    t.join(5)


def test_cap_is_never_exceeded_under_threads():
    ex = BulkheadExecutor(default_cap=3)
    current = {"n": 0}
    peak = {"n": 0}
    lock = threading.Lock()

    def work():
        with lock:
            current["n"] += 1
            peak["n"] = max(peak["n"], current["n"])
        time.sleep(0.01)
        with lock:
            current["n"] -= 1
        return True

    threads = [threading.Thread(
        target=lambda: ex.execute("b", work, timeout_s=10.0))
        for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    assert peak["n"] <= 3
    assert peak["n"] == 3  # the cap was actually the binding constraint


def test_exceptions_release_the_lane():
    ex = BulkheadExecutor(default_cap=1)

    def boom():
        raise ValueError("inner")
    with pytest.raises(ValueError):
        ex.execute("b", boom)
    assert ex.stats()["b"]["in_flight"] == 0
    assert ex.execute("b", lambda: "recovered") == "recovered"


def test_stats_and_validation():
    ex = BulkheadExecutor(default_cap=2)
    ex.execute("a", lambda: 1)
    stats = ex.stats()
    assert stats["a"] == {"cap": 2, "in_flight": 0, "executed_total": 1,
                          "rejected_total": 0}
    with pytest.raises(SpecError):
        BulkheadExecutor(default_cap=0)
    with pytest.raises(SpecError):
        BulkheadExecutor(caps={"x": -2})
    with pytest.raises(SpecError):
        ex.cap_for("")


def test_rejected_total_counts():
    ex = BulkheadExecutor(default_cap=1)
    entered = threading.Event()
    release = threading.Event()

    def hold():
        entered.set()
        release.wait(5)
    t = threading.Thread(target=lambda: ex.execute("s", hold))
    t.start()
    assert entered.wait(5)
    for _ in range(3):
        with pytest.raises(BulkheadRejected):
            ex.execute("s", lambda: None)
    release.set()
    t.join(5)
    assert ex.stats()["s"]["rejected_total"] == 3


# --- retry policy: rejections are not retried -----------------------------------------------------------------

def test_default_policy_excludes_bulkhead_rejected():
    assert default_retry_policy(BulkheadRejected("full")) is False


def test_retry_with_budget_does_not_spin_on_rejection():
    budget = RetryBudget(5)
    with pytest.raises(BulkheadRejected):
        retry_with_budget(lambda: (_ for _ in ()).throw(
            BulkheadRejected("full")), budget)
    assert budget.remaining == 5  # not a single token burned


# --- HugrGate.decide integration ---------------------------------------------------------------------------------

def test_decide_with_bulkhead_rejects_fast_when_backend_stuck():
    gate = HugrGate()

    entered = threading.Event()
    release = threading.Event()

    class StuckBackend(StubBackend):
        def evaluate(self, state, spec, context=None):
            entered.set()
            release.wait(5)
            return super().evaluate(state, spec, context)

    gate.register(StuckBackend(name="stuck", value="a"))
    gate.register(StubBackend(name="free", value="b"))
    bulkhead = BulkheadExecutor(default_cap=8, caps={"stuck": 1})

    t = threading.Thread(
        target=lambda: gate.decide({}, _spec(), backend_name="stuck",
                                   bulkhead=bulkhead))
    t.start()
    assert entered.wait(5)
    # The stuck backend's single lane is occupied: fail fast...
    with pytest.raises(BulkheadRejected):
        gate.decide({}, _spec(), backend_name="stuck", bulkhead=bulkhead)
    # ...while the other backend is unaffected.
    result = gate.decide({}, _spec(), backend_name="free",
                         bulkhead=bulkhead)
    assert result.accepted is True
    assert result.value == "b"
    release.set()
    t.join(5)


def test_decide_bulkhead_holds_one_lane_across_retries():
    gate = HugrGate()
    inner = StubBackend(name="flaky", value="a")
    gate.register(inner)
    bulkhead = BulkheadExecutor(default_cap=8, caps={"flaky": 1})
    budget = RetryBudget(5)

    entered = threading.Event()
    release = threading.Event()
    real_evaluate = inner.evaluate
    calls = {"n": 0}

    def gate_fn(state, spec, context=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackendError("transient")  # retried inside the lane
        entered.set()
        release.wait(5)
        return real_evaluate(state, spec, context)

    inner.evaluate = gate_fn  # type: ignore[method-assign]
    outcome = {}

    def first_decide():
        try:
            outcome["result"] = gate.decide(
                {}, _spec(), backend_name="flaky",
                bulkhead=bulkhead, retry_budget=budget)
        except Exception as e:  # noqa: BLE001 - recorded for assertion
            outcome["error"] = e

    t = threading.Thread(target=first_decide, daemon=True)
    t.start()
    assert entered.wait(5)
    # The first decide is on its second attempt, still holding the
    # lane: a second decide is rejected fast, and the lane is held
    # across the retry (in_flight == 1, not 0-then-1).
    assert calls["n"] == 2
    assert budget.remaining == 4  # exactly one retry consumed
    with pytest.raises(BulkheadRejected):
        gate.decide({}, _spec(), backend_name="flaky", bulkhead=bulkhead)
    assert bulkhead.stats()["flaky"]["in_flight"] == 1
    release.set()
    t.join(5)
    assert outcome["result"].accepted is True
    assert bulkhead.stats()["flaky"]["in_flight"] == 0
