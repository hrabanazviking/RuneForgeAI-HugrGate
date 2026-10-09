"""Slice 018 — async-readiness audit.

Findings and fixes in the async surfaces: the daemon's batching queue
and the new first-class ``HugrGate.adecide``.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.daemon import BatchingQueue
from hugrgate.errors import QueueFull
from hugrgate.result import DecisionResult

SPEC = DecisionSpec(type="categorical", options=["a", "b"])
POLICY = DecisionPolicy(minimum_probability=0.0)


class StubBackend(Backend):
    def __init__(self, name="stub", delay=0.0):
        self.name = name
        self.delay = delay

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        if self.delay:
            time.sleep(self.delay)
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0})


def _gate(**kw):
    gate = HugrGate()
    gate.register(StubBackend(**kw))
    return gate


# --- adecide ---------------------------------------------------------------

def test_adecide_matches_decide():
    async def main():
        gate = _gate()
        sync_r = gate.decide({"x": 1}, SPEC, POLICY)
        async_r = await gate.adecide({"x": 1}, SPEC, POLICY)
        assert async_r.value == sync_r.value == "a"
        assert async_r.probability == sync_r.probability

    asyncio.run(main())


def test_adecide_does_not_block_the_loop():
    async def main():
        gate = _gate(delay=0.3)
        ticked = []
        task = asyncio.create_task(gate.adecide({"x": 1}, SPEC, POLICY))
        for _ in range(5):
            await asyncio.sleep(0.1)
            ticked.append(True)
        result = await task
        assert result.value == "a"
        assert len(ticked) == 5  # loop stayed responsive during inference

    asyncio.run(main())


def test_adecide_propagates_backend_errors():
    async def main():
        gate = _gate()
        with pytest.raises(Exception):
            await gate.adecide({"x": 1}, SPEC, POLICY,
                               backend_name="ghost")

    asyncio.run(main())


# --- BatchingQueue stop() must not strand submitters -------------------------

def test_stop_drains_in_flight_without_hanging():
    async def main():
        gate = _gate(delay=0.2)
        q = BatchingQueue(gate, window_ms=5.0, max_batch=8)
        await q.start()
        results = await asyncio.gather(*[
            q.submit({"n": i}, SPEC.to_dict(), None, None, None)
            for i in range(6)
        ])
        assert all(r.value == "a" for r in results)
        # stop while a slow batch is mid-flight: submitters of the NEXT
        # wave were already resolved above; now verify a fresh stop
        # with in-flight work resolves instead of hanging.
        pending = [asyncio.create_task(
            q.submit({"n": i}, SPEC.to_dict(), None, None, None))
            for i in range(4)]
        await asyncio.sleep(0.05)  # let the worker pull a batch
        await asyncio.wait_for(q.stop(), timeout=10.0)
        done = await asyncio.gather(*pending)
        assert all(r.value == "a" for r in done)

    asyncio.run(main())


def test_stop_with_drain_timeout_fails_pending_fast():
    async def main():
        gate = _gate(delay=5.0)  # slower than the drain timeout
        q = BatchingQueue(gate, window_ms=5.0, max_batch=8)
        await q.start()
        pending = asyncio.create_task(
            q.submit({"n": 1}, SPEC.to_dict(), None, None, None))
        await asyncio.sleep(0.05)
        await q.stop(drain_timeout=0.2)
        with pytest.raises(QueueFull):
            await asyncio.wait_for(pending, timeout=5.0)

    asyncio.run(main())


def test_submit_after_stop_rejected():
    async def main():
        q = BatchingQueue(_gate())
        await q.start()
        await q.stop()
        with pytest.raises(QueueFull):
            await q.submit({"n": 1}, SPEC.to_dict(), None, None, None)

    asyncio.run(main())
