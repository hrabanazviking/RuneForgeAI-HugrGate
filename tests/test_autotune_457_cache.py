"""Slice 457 — cache-policy tuner. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    OptimizationController,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.tuners._base import seeded_rng
from hugrgate.autotune.tuners.cache import CachePolicyTuner, simulate_trace
from hugrgate.errors import TunerError


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store(ttl=60.0, size=32, ev="lru"):
    s = ConfigStore()
    s.register(TunableParameter(name="ttl", dtype="float", default=ttl,
                                lo=10.0, hi=600.0))
    s.register(TunableParameter(name="maxsize", dtype="int", default=size,
                                lo=16, hi=4096))
    s.register(TunableParameter(name="evict", dtype="str", default=ev,
                                choices=("lru", "lfu")))
    return s


def _trace(seed=13, n=600):
    """Hot keys: 5 keys get 80% of traffic over 1000s."""
    rng = seeded_rng(seed)
    hot = [f"hot{i}" for i in range(5)]
    out = []
    t = 0.0
    for _ in range(n):
        t += rng.uniform(0.5, 3.0)
        key = rng.choice(hot) if rng.random() < 0.8 \
            else f"cold{rng.randrange(200)}"
        out.append((key, t, 10.0))
    return out


def _tuner(**kw):
    base = dict(objective_id="cost", ttl_param="ttl", size_param="maxsize",
                eviction_param="evict", trace=_trace(), seed=1)
    base.update(kw)
    return CachePolicyTuner(**base)


def test_simulator_hits_and_expiry():
    trace = [("a", 0.0, 1.0), ("a", 5.0, 1.0), ("a", 500.0, 1.0)]
    res = simulate_trace(trace, ttl=60.0, max_size=10, eviction="lru")
    assert res["hits"] == 1.0 and res["misses"] == 2.0
    assert res["hit_rate"] == pytest.approx(1 / 3)


def test_simulator_eviction_lru_vs_lfu():
    # 'x' accessed often long ago, 'y' once recently; small cache.
    trace = [("x", 0.0, 1.0), ("x", 1.0, 1.0), ("x", 2.0, 1.0),
             ("y", 3.0, 1.0), ("z", 4.0, 1.0), ("x", 5.0, 1.0)]
    lru = simulate_trace(trace, ttl=100.0, max_size=2, eviction="lru")
    lfu = simulate_trace(trace, ttl=100.0, max_size=2, eviction="lfu")
    # LRU evicts x (stale) for z -> final x is a miss; LFU keeps x -> hit.
    assert lru["hits"] == 2.0
    assert lfu["hits"] == 3.0
    with pytest.raises(TunerError):
        simulate_trace(trace, ttl=10.0, max_size=2, eviction="fifo")


def test_tuner_finds_cheaper_config():
    t = _tuner()
    prop = t.tune(_ctx(_store(ttl=60.0, size=32)))
    assert prop is not None
    ev = prop.evidence
    assert ev["tuned"]["total_cost"] < ev["baseline"]["total_cost"]
    assert ev["tuned"]["hit_rate"] > ev["baseline"]["hit_rate"]
    assert prop.delta > 0  # negated cost
    assert ev["candidates_evaluated"] == 9 * 4 * 2  # grid x ladder x evict


def test_tuner_deterministic():
    p1 = _tuner().tune(_ctx(_store(), seed=8))
    p2 = _tuner().tune(_ctx(_store(), seed=8))
    assert p1 is not None and p2 is not None
    assert p1.changes == p2.changes


def test_tuner_silent_when_already_best():
    t = _tuner()
    first = t.tune(_ctx(_store()))
    assert first is not None
    # apply the winner, then re-tune: nothing left to win
    s = _store()
    s.apply(first.changes)
    t2 = _tuner(min_delta=1e-9)
    assert t2.tune(_ctx(s)) is None


def test_bad_specs_rejected():
    with pytest.raises(TunerError):
        _tuner(trace=[("a", 0.0, 1.0)] * 5)  # too short
    with pytest.raises(TunerError):
        _tuner(trace=[("a", float("nan"), 1.0)] * 30)
    with pytest.raises(TunerError):
        _tuner(trace=[("a", 0.0, -1.0)] * 30)
    with pytest.raises(TunerError):
        _tuner(ttl_param="")  # missing param


def test_wrong_param_types_rejected():
    s = ConfigStore()
    s.register(TunableParameter(name="ttl", dtype="int", default=60,
                                lo=10, hi=600))
    s.register(TunableParameter(name="maxsize", dtype="int", default=32,
                                lo=16, hi=4096))
    s.register(TunableParameter(name="evict", dtype="str", default="lru",
                                choices=("lru", "lfu")))
    with pytest.raises(TunerError):
        _tuner().tune(_ctx(s))


def test_end_to_end_offline():
    store = _store()
    c = OptimizationController(store=store)
    c.register_objective("cost", lambda values: 0.0)
    c.register_tuner(_tuner())
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].proposal_id != ""
    assert store.get("maxsize") == 32  # offline: untouched
