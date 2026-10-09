"""Slice 017 — thread-safety baseline.

Hammers the shared mutable state (decision cache, backend registry,
provenance store, and a full HugrGate) from many threads at once.
Success: no exceptions, no lost updates, counters consistent, and the
provenance chain still verifies afterwards.
"""

from __future__ import annotations

import threading

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend, BackendRegistry
from hugrgate.cache import DecisionCache
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult

SPEC = DecisionSpec(type="categorical", options=["a", "b"])
POLICY = DecisionPolicy(minimum_probability=0.0)
N_THREADS = 16
N_OPS = 250


class StubBackend(Backend):
    def __init__(self, name="stub"):
        self.name = name

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0})


def _run_threads(fn):
    errors = []

    def target():
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — collected, asserted later
            errors.append(e)

    threads = [threading.Thread(target=target) for _ in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"{len(errors)} thread errors, first: {errors[0]!r}"


def _result(i):
    return DecisionResult(value="a", probability=1.0,
                          distribution={"a": 1.0}, backend=f"b{i % 4}")


def test_cache_concurrent_get_put_invalidate():
    cache = DecisionCache(ttl_seconds=60.0, max_size=64)

    def work():
        for i in range(N_OPS):
            state = {"n": i % 32}
            r = _result(i)
            cache.put(state, SPEC, POLICY, r)
            cache.get(state, SPEC, POLICY)
            if i % 50 == 0:
                cache.invalidate_backend(f"b{i % 4}")
            cache.stats()

    _run_threads(work)
    s = cache.stats()
    assert s["hits"] + s["misses"] == N_THREADS * N_OPS
    assert s["size"] <= 64


def test_registry_concurrent_register_unregister():
    reg = BackendRegistry()

    def work():
        for i in range(N_OPS):
            name = f"be-{i % 24}"
            try:
                reg.register(StubBackend(name))
            except Exception:  # noqa: BLE001 - duplicate race is fine
                pass  # the invariant is no corruption
            reg.get(name)
            reg.supporting(SPEC)
            reg.list()
            if i % 7 == 0:
                reg.unregister(name)

    _run_threads(work)
    # registry is internally consistent: every listed name resolves
    for name in reg.list():
        assert reg.get(name) is not None


def test_provenance_concurrent_append_and_verify():
    store = ProvenanceStore()

    def work():
        for i in range(N_OPS):
            rec = DecisionRecord.from_decision(
                {"n": i}, SPEC, _result(i), policy_threshold=0.0)
            store.append(rec)
            store.recent(5)
            store.by_hash(rec.request_hash)

    _run_threads(work)
    assert store.count() == N_THREADS * N_OPS
    assert store.verify_chain() is True


def test_gate_concurrent_decide():
    gate = HugrGate()
    gate.register(StubBackend("stub"))

    def work():
        for i in range(N_OPS):
            r = gate.decide({"n": i % 16}, SPEC, POLICY)
            assert r.value == "a"

    _run_threads(work)
    assert gate.provenance.count() == N_THREADS * N_OPS
    assert gate.provenance.verify_chain() is True
