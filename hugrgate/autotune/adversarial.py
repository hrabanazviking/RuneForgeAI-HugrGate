"""Optimizer adversarial tests. Slice 473.

Tuners consume data and propose config changes — both are attack
surfaces. This module is the red-team harness for the optimizer:

- :func:`poison_labels` / :func:`spike_samples`: corrupt a tuner's
  inputs (flipped labels, injected latency spikes) with a seeded,
  reproducible corruption;
- :func:`label_poisoning_attack`: run a threshold tuner on clean vs
  poisoned data and measure how far the poisoned proposal's
  *clean-data* metric falls;
- :func:`latency_spike_attack`: run the latency tuner on spiked
  samples and check the allocation stays sane (sums to the budget,
  no stage starved below its minimum);
- :func:`malicious_tuner_attack`: a tuner proposing unknown params,
  out-of-bounds values, and wrong types must never change the
  store — the controller rejects before any driver sees them;
- :func:`crash_storm_attack`: every tuner crashing must still leave
  a completed cycle with all tuners skipped.

Each attack returns an :class:`AttackResult` (measurements, not just
pass/fail) so the containment properties are auditable. The test
suite asserts the properties; the harness supplies the attacks.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import (
    Disposition,
    Mode,
    OptimizationController,
    Proposal,
    TuningContext,
)
from hugrgate.autotune.tuners._base import BaseTuner, seeded_rng
from hugrgate.errors import ParameterError

__all__ = [
    "AttackResult",
    "crash_storm_attack",
    "label_poisoning_attack",
    "latency_spike_attack",
    "malicious_tuner_attack",
    "poison_labels",
    "spike_samples",
]


@dataclass
class AttackResult:
    """One executed attack with its measurements."""

    name: str
    measurements: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name,
                "measurements": dict(self.measurements),
                "notes": self.notes}


def poison_labels(dataset: Sequence[tuple[float, int]],
                  fraction: float, seed: int) -> list[tuple[float, int]]:
    """Flip ``fraction`` of binary labels (seeded, reproducible)."""
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be in [0, 1]")
    rng = seeded_rng(seed)
    idx = list(range(len(dataset)))
    rng.shuffle(idx)
    poisoned = set(idx[:int(len(dataset) * fraction)])
    return [(s, 1 - lab if i in poisoned else lab)
            for i, (s, lab) in enumerate(dataset)]


def spike_samples(samples: Mapping[str, Sequence[float]],
                  fraction: float, spike_factor: float,
                  seed: int) -> dict[str, list[float]]:
    """Inject ``spike_factor``x latency spikes into ``fraction`` of samples."""
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be in [0, 1]")
    if spike_factor < 1.0:
        raise ValueError("spike_factor must be >= 1")
    rng = seeded_rng(seed)
    out = {}
    for stage, xs in samples.items():
        xs = list(xs)
        idx = list(range(len(xs)))
        rng.shuffle(idx)
        spiked = set(idx[:int(len(xs) * fraction)])
        out[stage] = [x * spike_factor if i in spiked else x
                      for i, x in enumerate(xs)]
    return out


def label_poisoning_attack(
    tuner_factory: Callable[[Sequence[tuple[float, int]]], BaseTuner],
    dataset: Sequence[tuple[float, int]],
    clean_metric: Callable[[float], float],
    param: str,
    poison_fraction: float = 0.2,
    seed: int = 0,
) -> AttackResult:
    """How far does label poisoning move the tuned threshold?

    ``clean_metric(threshold)`` scores a threshold on *clean* held-out
    data. The attack passes (tuner contained) when the poisoned tuner
    stays silent or its clean-data metric stays within 0.10 of the
    clean tuner's.
    """
    from hugrgate.autotune.controller import ConfigStore, TunableParameter
    clean_tuner = tuner_factory(dataset)
    poisoned_tuner = tuner_factory(poison_labels(dataset, poison_fraction,
                                                 seed))

    def _ctx() -> TuningContext:
        store = ConfigStore()
        store.register(TunableParameter(name=param, dtype="float",
                                        default=0.9, lo=0.0, hi=1.0))
        return TuningContext(store=store, objectives={}, constraints=[],
                             seed=seed, mode=Mode.OFFLINE, run_id="atk")

    clean_prop = clean_tuner.tune(_ctx())
    poisoned_prop = poisoned_tuner.tune(_ctx())
    clean_thr = clean_prop.changes[param] if clean_prop else None
    poisoned_thr = poisoned_prop.changes[param] if poisoned_prop else None
    m_clean = clean_metric(clean_thr) if clean_thr is not None else None
    m_poisoned = clean_metric(poisoned_thr) if poisoned_thr is not None else None
    drift = (abs(m_clean - m_poisoned)
             if m_clean is not None and m_poisoned is not None else None)
    contained = poisoned_prop is None or (drift is not None
                                          and drift <= 0.10)
    return AttackResult(
        name="label_poisoning",
        measurements={"poison_fraction": poison_fraction,
                      "clean_threshold": clean_thr,
                      "poisoned_threshold": poisoned_thr,
                      "clean_metric_clean": m_clean,
                      "clean_metric_poisoned": m_poisoned,
                      "metric_drift": drift,
                      "contained": contained},
        notes="poisoned tuner must stay silent or stay within 0.10 of "
              "the clean metric")


def latency_spike_attack(
    tuner_factory: Callable[[Mapping[str, Sequence[float]]], BaseTuner],
    samples: Mapping[str, Sequence[float]],
    total_budget_ms: float,
    min_stage_ms: float,
    spike_fraction: float = 0.1,
    spike_factor: float = 10.0,
    seed: int = 0,
) -> AttackResult:
    """Do latency spikes make the budget allocator insane?

    Contained when the spiked allocation still sums to the budget and
    no stage is starved below its minimum or given more than the
    total budget.
    """
    from hugrgate.autotune.controller import ConfigStore, TunableParameter
    stages = list(samples)

    def _ctx() -> TuningContext:
        store = ConfigStore()
        for st in stages:
            store.register(TunableParameter(name=st, dtype="float",
                                            default=100.0, lo=1.0,
                                            hi=10000.0))
        return TuningContext(store=store, objectives={}, constraints=[],
                             seed=seed, mode=Mode.OFFLINE, run_id="atk")

    tuner = tuner_factory(spike_samples(samples, spike_fraction,
                                        spike_factor, seed))
    prop = tuner.tune(_ctx())
    alloc = prop.changes if prop else None
    sane = True
    if alloc is not None:
        total = sum(alloc.values())
        sane = (abs(total - total_budget_ms) < 1e-6
                and all(min_stage_ms <= v <= total_budget_ms
                        for v in alloc.values()))
    return AttackResult(
        name="latency_spike",
        measurements={"spike_fraction": spike_fraction,
                      "spike_factor": spike_factor,
                      "proposed": alloc is not None,
                      "allocation": alloc,
                      "allocation_sane": sane,
                      "contained": prop is None or sane},
        notes="spiked allocation must sum to budget with no starved stage")


def malicious_tuner_attack(controller: OptimizationController,
                           malicious_changes: Mapping[str, Any],
                           tuner_name: str = "malicious") -> AttackResult:
    """A hostile tuner must never change the store.

    The tuner proposes unknown params / out-of-bounds / wrong types.
    Contained when the store is byte-identical afterwards and the
    cycle either rejects the proposal or raises ParameterError (a
    programming bug, never a silent apply).
    """
    before = controller.store.snapshot()

    class _Malicious:
        name = tuner_name

        def tune(self, ctx: TuningContext) -> Proposal | None:
            return Proposal(proposal_id="evil", tuner=tuner_name,
                            changes=dict(malicious_changes),
                            objective_id="o", baseline=0.0, estimate=1.0,
                            seed=ctx.seed)

    controller.register_tuner(_Malicious())
    outcome = "completed"
    try:
        run = controller.run_cycle(mode=Mode.OFFLINE, seed=1)
        dispositions = [r.disposition.value for r in run.results]
    except ParameterError as exc:
        dispositions = [f"raised:{exc.code}"]
        outcome = "rejected-by-validation"
    after = controller.store.snapshot()
    untouched = before == after
    return AttackResult(
        name="malicious_tuner",
        measurements={"changes": dict(malicious_changes),
                      "dispositions": dispositions,
                      "store_untouched": untouched,
                      "outcome": outcome,
                      "contained": untouched},
        notes="unknown/out-of-bounds/wrong-type changes must never apply")


def crash_storm_attack(controller: OptimizationController,
                       n_crashers: int = 5) -> AttackResult:
    """Every tuner crashing must still leave a completed cycle."""
    for i in range(n_crashers):
        class _Crasher:
            name = f"crasher-{i}"

            def tune(self, ctx: TuningContext) -> Proposal | None:
                raise RuntimeError("storm")

        controller.register_tuner(_Crasher())
    run = controller.run_cycle(mode=Mode.OFFLINE, seed=1)
    skipped = [r for r in run.results
               if r.disposition == Disposition.SKIPPED]
    crashed = [r for r in run.results
               if r.detail.get("tuner", "").startswith("crasher-")]
    return AttackResult(
        name="crash_storm",
        measurements={"n_crashers": n_crashers,
                      "results": len(run.results),
                      "skipped": len(skipped),
                      "crasher_notes": len([n for n in run.notes
                                            if "crasher-" in n]),
                      "contained": len(skipped) == n_crashers
                      and len(crashed) == n_crashers},
        notes="a storm of crashing tuners must not break the cycle")
