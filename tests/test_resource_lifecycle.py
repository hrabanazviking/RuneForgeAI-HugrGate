"""Slice 019 — resource lifecycle management.

Every resource-owning component gets an explicit, tested lifecycle:
backends release via ``close()``, gates shut them down, the batching
queue is an async context manager, and the provenance store bounds its
memory without breaking its integrity chain.
"""

from __future__ import annotations

import asyncio

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.daemon import BatchingQueue
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult

SPEC = DecisionSpec(type="categorical", options=["a", "b"])
POLICY = DecisionPolicy(minimum_probability=0.0)


class StubBackend(Backend):
    def __init__(self, name="stub"):
        self.name = name
        self.closed = False

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0})

    def close(self):
        self.closed = True


class FlakyCloseBackend(StubBackend):
    def close(self):
        raise RuntimeError("cannot release")


def _record(i=0):
    r = DecisionResult(value="a", probability=1.0,
                       distribution={"a": 1.0})
    return DecisionRecord.from_decision({"n": i}, SPEC, r)


# --- Backend.close / HugrGate.close ------------------------------------------

def test_backend_close_defaults_to_noop():
    class Bare(Backend):
        name = "bare"

        def capabilities(self):
            return {}

        def supports(self, spec):
            return True

        def evaluate(self, state, spec, context=None):
            raise AssertionError("unused")

    Bare().close()  # must not raise


def test_gate_close_releases_all_backends():
    gate = HugrGate()
    a, b = StubBackend("a"), StubBackend("b")
    gate.register(a)
    gate.register(b)
    gate.close()
    assert a.closed and b.closed


def test_gate_close_is_best_effort():
    gate = HugrGate()
    good, bad = StubBackend("good"), FlakyCloseBackend("bad")
    gate.register(good)
    gate.register(bad)
    gate.close()  # bad.close() raises; good must still be closed
    assert good.closed


def test_gate_context_manager_closes():
    with HugrGate() as gate:
        b = StubBackend("s")
        gate.register(b)
    assert b.closed


# --- BatchingQueue async context manager --------------------------------------

def test_batching_queue_async_context_manager():
    async def main():
        gate = HugrGate()
        gate.register(StubBackend("stub"))
        async with BatchingQueue(gate) as q:
            r = await q.submit({"n": 1}, SPEC.to_dict(), None, None, None)
            assert r.value == "a"
        assert q._accepting is False

    asyncio.run(main())


# --- ProvenanceStore max_records ----------------------------------------------

def test_max_records_rejects_zero():
    with pytest.raises(ValueError):
        ProvenanceStore(max_records=0)


def test_max_records_bounds_memory_and_keeps_chain_valid():
    store = ProvenanceStore(max_records=3)
    for i in range(10):
        store.append(_record(i))
    assert store.count() == 3
    assert store.evicted_count() == 7
    assert store.verify_chain() is True
    # newest records are the ones kept
    kept = [r.metadata for r in store.recent(3)]
    assert store.recent(3)[-1].request_hash == _record(9).request_hash


def test_unbounded_store_still_default():
    store = ProvenanceStore()
    for i in range(50):
        store.append(_record(i))
    assert store.count() == 50
    assert store.evicted_count() == 0
    assert store.verify_chain() is True
