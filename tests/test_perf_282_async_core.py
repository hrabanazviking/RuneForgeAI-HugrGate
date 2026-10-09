"""Slice 282 — async core path.

Covers: AsyncBackend protocol structural detection, AsyncBackendBase
default thread delegation, evaluate_async dispatch (native stays on the
loop thread, sync goes to a worker thread), adecide contract parity
with decide (result fields, provenance, errors), adecide_batch
ordering + concurrency bound + validation.
"""

from __future__ import annotations

import asyncio
import threading
from typing import ClassVar

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.asyncx import (
    AsyncBackend,
    AsyncBackendBase,
    evaluate_async,
    is_async_backend,
)
from hugrgate.backend import Backend
from hugrgate.errors import Abstention, BackendError, SpecError
from hugrgate.result import DecisionResult

pytestmark = pytest.mark.slow

SPEC = DecisionSpec(type="categorical", options=["a", "b"])
POLICY = DecisionPolicy(minimum_probability=0.0)


def _result(value="a", prob=1.0):
    return DecisionResult(value=value, probability=prob,
                          distribution={"a": prob, "b": 1.0 - prob})


class SyncBackend(Backend):
    name = "sync-282"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        return _result()


class NativeAsyncBackend(AsyncBackendBase):
    name = "native-async-282"
    seen_threads: ClassVar[list[int]] = []

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):  # pragma: no cover
        raise AssertionError("native path must not call sync evaluate")

    async def aevaluate(self, state, spec, context=None):
        NativeAsyncBackend.seen_threads.append(threading.get_ident())
        await asyncio.sleep(0)  # genuinely non-blocking
        return _result()


class DuckAsyncBackend(Backend):
    """No inheritance from async types — structural detection must work."""
    name = "duck-async-282"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):  # pragma: no cover
        raise AssertionError("async-only backend")

    async def aevaluate(self, state, spec, context=None):
        return _result()


class DefaultAsyncBase(AsyncBackendBase):
    """Uses the default aevaluate -> to_thread delegation."""
    name = "default-async-282"
    seen_threads: ClassVar[list[int]] = []

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        DefaultAsyncBase.seen_threads.append(threading.get_ident())
        return _result()


# --- protocol / dispatch -------------------------------------------------------

def test_is_async_backend_structural():
    assert is_async_backend(NativeAsyncBackend())
    assert is_async_backend(DuckAsyncBackend())  # no inheritance needed
    assert is_async_backend(DefaultAsyncBase())
    assert not is_async_backend(SyncBackend())
    assert not is_async_backend(object())


def test_protocol_runtime_check():
    assert isinstance(NativeAsyncBackend(), AsyncBackend)
    assert isinstance(DuckAsyncBackend(), AsyncBackend)
    assert not isinstance(SyncBackend(), AsyncBackend)


def test_evaluate_async_native_stays_on_loop_thread():
    async def main():
        loop_thread = threading.get_ident()
        backend = NativeAsyncBackend()
        NativeAsyncBackend.seen_threads.clear()
        result = await evaluate_async(backend, {"x": 1}, SPEC)
        assert result.value == "a"
        assert NativeAsyncBackend.seen_threads == [loop_thread]

    asyncio.run(main())


def test_evaluate_async_sync_backend_uses_worker_thread():
    async def main():
        loop_thread = threading.get_ident()
        seen = []

        class Probe(SyncBackend):
            def evaluate(self, state, spec, context=None):
                seen.append(threading.get_ident())
                return _result()

        result = await evaluate_async(Probe(), {"x": 1}, SPEC)
        assert result.value == "a"
        assert seen and seen[0] != loop_thread

    asyncio.run(main())


def test_default_async_base_delegates_to_thread():
    async def main():
        loop_thread = threading.get_ident()
        backend = DefaultAsyncBase()
        DefaultAsyncBase.seen_threads.clear()
        result = await backend.aevaluate({"x": 1}, SPEC)
        assert result.value == "a"
        assert DefaultAsyncBase.seen_threads != [loop_thread]

    asyncio.run(main())


# --- adecide parity ---------------------------------------------------------------

def _gate_with(backend) -> HugrGate:
    gate = HugrGate()
    gate.register(backend)
    return gate


def test_adecide_matches_decide_contract():
    async def main():
        gate = _gate_with(NativeAsyncBackend())
        async_result = await gate.adecide({"x": 1}, SPEC, POLICY)
        # parity against the sync path on an equivalent sync backend
        sync_gate = _gate_with(SyncBackend())
        sync_result = sync_gate.decide({"x": 1}, SPEC, POLICY)
        assert async_result.value == sync_result.value
        assert async_result.probability == sync_result.probability
        assert async_result.backend == "native-async-282"
        assert async_result.metadata["policy_verdict"] == "accept"
        assert gate.provenance.count() == 1

    asyncio.run(main())


def test_adecide_sync_backend_still_works():
    async def main():
        gate = _gate_with(SyncBackend())
        result = await gate.adecide({"x": 1}, SPEC, POLICY)
        assert result.value == "a"
        assert result.backend == "sync-282"

    asyncio.run(main())


def test_adecide_error_semantics():
    class FailBackend(Backend):
        name = "fail-282"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            raise RuntimeError("boom")

    class AbstainBackend(Backend):
        name = "abstain-282"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            from hugrgate.errors import Abstention as A
            raise A("nope")

    async def main():
        gate = _gate_with(FailBackend())
        with pytest.raises(BackendError):
            await gate.adecide({"x": 1}, SPEC, POLICY)
        gate2 = _gate_with(AbstainBackend())
        with pytest.raises(Abstention):
            await gate2.adecide({"x": 1}, SPEC, POLICY)
        # unknown backend + policy-blocked backend
        with pytest.raises(Exception):
            await gate.adecide({"x": 1}, SPEC, POLICY,
                               backend_name="nope")

    asyncio.run(main())


def test_adecide_policy_abstention():
    strict = DecisionPolicy(minimum_probability=0.99)

    class LowConf(Backend):
        name = "lowconf-282"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            return _result(prob=0.5)

    async def main():
        gate = _gate_with(LowConf())
        with pytest.raises(Abstention):
            await gate.adecide({"x": 1}, SPEC, strict)

    asyncio.run(main())


# --- adecide_batch ------------------------------------------------------------

def test_adecide_batch_order_and_concurrency_bound():
    in_flight = 0
    max_seen = 0

    class SlowAsync(AsyncBackendBase):
        name = "slow-282"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):  # pragma: no cover
            raise AssertionError("async-only backend")

        async def aevaluate(self, state, spec, context=None):
            nonlocal in_flight, max_seen
            in_flight += 1
            max_seen = max(max_seen, in_flight)
            try:
                await asyncio.sleep(0.02)
                return DecisionResult(
                    value="a", probability=1.0,
                    distribution={"a": 1.0, "b": 0.0},
                    metadata={"echo": state["x"]})
            finally:
                in_flight -= 1

    async def main():
        gate = _gate_with(SlowAsync())
        states = [{"x": i} for i in range(10)]
        results = await gate.adecide_batch(states, SPEC, POLICY,
                                           max_concurrency=3)
        assert [r.metadata["echo"] for r in results] == list(range(10))
        assert max_seen <= 3
        assert max_seen > 1  # genuinely concurrent

    asyncio.run(main())


def test_adecide_batch_rejects_bad_concurrency():
    async def main():
        gate = _gate_with(SyncBackend())
        with pytest.raises(SpecError):
            await gate.adecide_batch([{"x": 1}], SPEC, POLICY,
                                     max_concurrency=0)

    asyncio.run(main())
