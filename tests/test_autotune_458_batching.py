"""Slice 458 — batch-size tuner. Unit tests."""

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
from hugrgate.autotune.tuners.batching import (
    BatchSizeTuner,
    fit_linear,
    powers_of_two,
)
from hugrgate.errors import TunerError


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store(bs=4):
    s = ConfigStore()
    s.register(TunableParameter(name="batch", dtype="int", default=bs,
                                lo=1, hi=64))
    return s


def _samples(seed=31):
    """latency = 5 + 2*b + noise; memory = 100 + 10*b."""
    rng = seeded_rng(seed)
    out = []
    for b in (1, 2, 4, 8, 16, 32):
        for _ in range(5):
            out.append((b, 5.0 + 2.0 * b + rng.uniform(-0.5, 0.5),
                        100.0 + 10.0 * b))
    rng.shuffle(out)
    return out


def test_fit_linear():
    a, c, r2 = fit_linear([1.0, 2.0, 3.0, 4.0], [3.0, 5.0, 7.0, 9.0])
    assert a == pytest.approx(1.0) and c == pytest.approx(2.0)
    assert r2 == pytest.approx(1.0)
    with pytest.raises(TunerError):
        fit_linear([1.0, 2.0], [1.0, 2.0])
    with pytest.raises(TunerError):
        fit_linear([1.0, 1.0, 1.0], [1.0, 2.0, 3.0])


def test_powers_of_two():
    assert powers_of_two(1, 64) == [1, 2, 4, 8, 16, 32, 64]
    assert powers_of_two(3, 20) == [3, 4, 8, 16, 20]
    with pytest.raises(TunerError):
        powers_of_two(0, 10)


def test_tuner_picks_best_feasible():
    t = BatchSizeTuner(param="batch", objective_id="thr",
                       samples=_samples(), latency_cap_ms=50.0,
                       memory_cap_mb=10000.0, seed=1)
    prop = t.tune(_ctx(_store(bs=4)))
    assert prop is not None
    # latency(16) ~= 37 <= 50 feasible; latency(32) ~= 69 infeasible
    assert prop.changes["batch"] == 16
    assert prop.evidence["latency_model"]["r_squared"] > 0.99
    assert prop.evidence["tuned"]["modeled_throughput"] > \
        prop.evidence["baseline"]["modeled_throughput"]


def test_tuner_respects_memory_cap():
    t = BatchSizeTuner(param="batch", objective_id="thr",
                       samples=_samples(), latency_cap_ms=1000.0,
                       memory_cap_mb=200.0, seed=1)  # mem(16)=260 > 200
    prop = t.tune(_ctx(_store(bs=4)))
    assert prop is not None
    assert prop.changes["batch"] == 8  # mem(8)=180 <= 200


def test_tuner_silent_on_bad_fit():
    rng = seeded_rng(99)
    noise = [(b, rng.uniform(1, 100), rng.uniform(1, 100))
             for b in (1, 2, 4, 8, 16) for _ in range(4)]
    t = BatchSizeTuner(param="batch", objective_id="thr", samples=noise,
                       seed=1)
    assert t.tune(_ctx(_store())) is None


def test_tuner_silent_when_nothing_feasible():
    t = BatchSizeTuner(param="batch", objective_id="thr",
                       samples=_samples(), latency_cap_ms=1.0, seed=1)
    assert t.tune(_ctx(_store())) is None


def test_bad_specs_rejected():
    with pytest.raises(TunerError):
        BatchSizeTuner(param="batch", objective_id="o",
                       samples=[(1, 1.0, 1.0)] * 2, seed=1)
    with pytest.raises(TunerError):
        BatchSizeTuner(param="batch", objective_id="o",
                       samples=[(0, 1.0, 1.0)] * 5, seed=1)
    with pytest.raises(TunerError):
        BatchSizeTuner(param="", objective_id="o", samples=_samples(),
                       seed=1)
    s = ConfigStore()
    s.register(TunableParameter(name="f", dtype="float", default=1.0,
                                lo=0.0, hi=2.0))
    with pytest.raises(TunerError):
        BatchSizeTuner(param="f", objective_id="o", samples=_samples(),
                       seed=1).tune(_ctx(s))


def test_end_to_end_offline():
    store = _store(bs=4)
    c = OptimizationController(store=store)
    c.register_objective("thr", lambda values: 0.0)
    c.register_tuner(BatchSizeTuner(param="batch", objective_id="thr",
                                    samples=_samples(),
                                    latency_cap_ms=50.0, seed=1))
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].proposal_id != ""
    assert store.get("batch") == 4  # offline: untouched
