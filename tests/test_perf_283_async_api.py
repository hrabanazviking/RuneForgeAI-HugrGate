"""Slice 283 — async backend API.

Covers: AsyncRequest validation, AsyncGate single/batch/stream paths,
timeout semantics (explicit wins, policy budget honored, taxonomy
TimeoutError with details), input-order preservation, consumer-paced
streaming with early break, closed-gate rejection, and empty input.
"""

from __future__ import annotations

import asyncio

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.async_backend import AsyncGate, AsyncRequest, evaluate_async
from hugrgate.asyncx import AsyncBackendBase, is_async_backend
from hugrgate.backend import Backend
from hugrgate.errors import SpecError, TimeoutError
from hugrgate.result import DecisionResult

pytestmark = pytest.mark.slow

SPEC = DecisionSpec(type="categorical", options=["a", "b"])
POLICY = DecisionPolicy(minimum_probability=0.0)


def _result(**kw):
    base = {"value": "a", "probability": 1.0,
            "distribution": {"a": 1.0, "b": 0.0}}
    base.update(kw)
    return DecisionResult(**base)


class SyncBackend(Backend):
    name = "sync-283"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        return _result(metadata={"echo": state.get("x")})


class SlowAsyncBackend(AsyncBackendBase):
    name = "slow-283"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):  # pragma: no cover
        raise AssertionError("async-only")

    async def aevaluate(self, state, spec, context=None):
        await asyncio.sleep(state.get("delay", 0.01))
        return _result(metadata={"echo": state.get("x")})


def _gate(backend=None, **kw) -> AsyncGate:
    gate = AsyncGate(**kw)
    gate.register(backend or SyncBackend())
    return gate


# --- request validation -------------------------------------------------------

def test_request_rejects_bad_timeout():
    with pytest.raises(SpecError):
        AsyncRequest(state={}, spec=SPEC, timeout_s=0)
    with pytest.raises(SpecError):
        AsyncRequest(state={}, spec=SPEC, timeout_s=-1)


def test_request_rejects_non_mapping_state():
    with pytest.raises(SpecError):
        AsyncRequest(state=[1, 2], spec=SPEC)


def test_gate_rejects_bad_concurrency():
    with pytest.raises(SpecError):
        AsyncGate(max_concurrency=0)


# --- single ---------------------------------------------------------------------

def test_adecide_single():
    async def main():
        gate = _gate()
        result = await gate.adecide({"x": 7}, SPEC, POLICY)
        assert result.value == "a"
        assert result.metadata["echo"] == 7
        assert result.backend == "sync-283"

    asyncio.run(main())


def test_adecide_explicit_timeout_fires():
    async def main():
        gate = _gate(SlowAsyncBackend())
        with pytest.raises(TimeoutError) as exc:
            await gate.adecide({"x": 1, "delay": 0.3}, SPEC, POLICY,
                               timeout_s=0.05)
        assert exc.value.code == "timeout"
        assert exc.value.recoverable is True
        assert exc.value.details["budget_ms"] == pytest.approx(50.0)

    asyncio.run(main())


def test_adecide_policy_latency_budget_honored():
    async def main():
        gate = _gate(SlowAsyncBackend())
        budgeted = DecisionPolicy(minimum_probability=0.0,
                                  maximum_latency_ms=40.0)
        with pytest.raises(TimeoutError):
            await gate.adecide({"x": 1, "delay": 0.3}, SPEC, budgeted)

    asyncio.run(main())


def test_adecide_no_timeout_when_unbounded():
    async def main():
        gate = _gate(SlowAsyncBackend())
        result = await gate.adecide({"x": 1, "delay": 0.05}, SPEC, POLICY)
        assert result.value == "a"

    asyncio.run(main())


def test_evaluate_async_reexport_dispatches():
    assert is_async_backend(SlowAsyncBackend())
    assert not is_async_backend(SyncBackend())

    async def main():
        result = await evaluate_async(SlowAsyncBackend(), {"x": 1}, SPEC)
        assert result.value == "a"

    asyncio.run(main())


# --- batch ------------------------------------------------------------------------

def test_adecide_many_preserves_order():
    async def main():
        gate = _gate(SlowAsyncBackend(), max_concurrency=4)
        requests = [AsyncRequest(state={"x": i, "delay": 0.01 * (5 - i)},
                                 spec=SPEC, policy=POLICY)
                    for i in range(6)]
        results = await gate.adecide_many(requests)
        assert [r.metadata["echo"] for r in results] == list(range(6))

    asyncio.run(main())


def test_adecide_many_empty():
    async def main():
        gate = _gate()
        assert await gate.adecide_many([]) == []

    asyncio.run(main())


def test_adecide_many_propagates_first_error():
    class Boom(Backend):
        name = "boom-283"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            if state.get("x") == 2:
                raise RuntimeError("kablam")
            return _result()

    async def main():
        gate = AsyncGate(max_concurrency=2)
        gate.register(Boom())
        requests = [AsyncRequest(state={"x": i}, spec=SPEC, policy=POLICY)
                    for i in range(4)]
        with pytest.raises(Exception):
            await gate.adecide_many(requests)

    asyncio.run(main())


# --- stream --------------------------------------------------------------------------

def test_astream_yields_as_completed():
    async def main():
        gate = _gate(SlowAsyncBackend(), max_concurrency=4)
        # later indices finish first (shorter delays)
        requests = [AsyncRequest(state={"x": i, "delay": 0.02 * (4 - i)},
                                 spec=SPEC, policy=POLICY)
                    for i in range(5)]
        order = []
        async for index, result in gate.astream(requests):
            order.append(index)
            assert result.metadata["echo"] == index
        assert sorted(order) == list(range(5))
        # completion order is NOT input order (that's the point)
        assert order != list(range(5))

    asyncio.run(main())


def test_astream_early_break_stops_new_work():
    started = []

    class Counting(SlowAsyncBackend):
        async def aevaluate(self, state, spec, context=None):
            started.append(state["x"])
            return await super().aevaluate(state, spec, context)

    async def main():
        gate = AsyncGate(max_concurrency=1)
        gate.register(Counting())
        requests = [AsyncRequest(state={"x": i, "delay": 0.02},
                                 spec=SPEC, policy=POLICY)
                    for i in range(10)]
        seen = 0
        async for _index, _result in gate.astream(requests):
            seen += 1
            if seen == 2:
                break
        # with max_concurrency=1, at most 3 evaluations could have
        # started (2 consumed + 1 in flight when we broke out)
        assert len(started) <= 3

    asyncio.run(main())


def test_astream_empty():
    async def main():
        gate = _gate()
        count = 0
        async for _ in gate.astream([]):
            count += 1
        assert count == 0

    asyncio.run(main())


# --- lifecycle --------------------------------------------------------------------------

def test_closed_gate_rejected():
    async def main():
        gate = _gate()
        gate.close()
        assert gate.closed
        with pytest.raises(SpecError):
            await gate.adecide({"x": 1}, SPEC, POLICY)
        with pytest.raises(SpecError):
            gate.register(SyncBackend())

    asyncio.run(main())


def test_close_is_idempotent():
    gate = _gate()
    gate.close()
    gate.close()
    assert gate.closed
