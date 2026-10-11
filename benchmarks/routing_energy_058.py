"""Slice 058 measurement artifact: energy-aware vs baseline routing.

Two local backends do the same work (80ms sleeps) with different power
draws: "gpu-hog" declares 250W, "lean" declares 15W. The baseline plan is
energy-unaware (cheapest-first ordering, gpu-hog inserted first, wins
every round). The energy-aware plan prunes gpu-hog under a 5J budget and
routes to "lean" instead.

Latencies are *measured* on this machine; power draws are the backends'
declared figures (stated assumptions, see hugrgate/routing/energy.py).
Joules per decision = measured latency × declared power. No numbers are
invented: rerun to reproduce.

Usage: python benchmarks/routing_energy_058.py [--rounds N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hugrgate import (Backend, BackendRegistry, DecisionPolicy, DecisionResult,
                      DecisionSpec)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (DynamicRungPlanner, EnergyAwarePlanner,
                              EnergyLedger, EnergyModel, LadderRouterV2,
                              RoutingOptions)


class WattBackend(Backend):
    def __init__(self, name, watts, sleep_ms, prob):
        self.name = name
        self._watts = watts
        self._sleep = sleep_ms
        self._prob = prob

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        time.sleep(self._sleep / 1000.0)
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)

    def estimated_latency(self):
        return float(self._sleep)

    def hardware_requirements(self):
        return {"power_watts": self._watts}


def _round_floats(obj):
    """Recursively round every float to 6 dp (slice 11: kill float noise)."""
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v) for v in obj]
    return obj


def run(rounds, energy_aware):
    registry = BackendRegistry()
    hog = WattBackend("gpu-hog", watts=250.0, sleep_ms=80, prob=0.99)
    lean = WattBackend("lean", watts=15.0, sleep_ms=80, prob=0.95)
    registry.register(hog)
    registry.register(lean)
    model = EnergyModel()
    spend_ledger = EnergyLedger(None, model)
    planner = DynamicRungPlanner(registry)
    if energy_aware:
        planner = EnergyAwarePlanner(planner, registry, budget_j=5.0,
                                     model=model)
    router = LadderRouterV2(
        registry,
        ladders={"categorical": [LadderRung("gpu-hog", 0.9),
                                 LadderRung("lean", 0.9)]},
        planner=planner,  # type: ignore[arg-type]
        energy_ledger=spend_ledger)
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy(minimum_probability=0.9)
    winners = []
    for _ in range(rounds):
        winners.append(router.decide({}, spec, policy).backend)
    return {
        "winners": winners,
        "spent_j": round(spend_ledger.spent, 4),
        "per_backend_watts": {"gpu-hog": model.power_watts(hog),
                              "lean": model.power_watts(lean)},
    }


def main() -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "routing_energy_058.json"))
    args = ap.parse_args()

    baseline = run(args.rounds, energy_aware=False)
    aware = run(args.rounds, energy_aware=True)
    artifact = {
        "slice": "058",
        "description": "energy-aware pruning vs energy-unaware baseline",
        "rounds": args.rounds,
        "power_model": {
            "note": "latencies measured; power draws are declared "
                    "backend figures (see hugrgate/routing/energy.py)",
        },
        "baseline": baseline,
        "energy_aware": aware,
        "joules_saved": round(baseline["spent_j"] - aware["spent_j"], 4),
        "savings_factor": (round(baseline["spent_j"] / aware["spent_j"], 2)
                           if aware["spent_j"] > 0 else None),
    }
    artifact = _round_floats(artifact)
    with open(args.out, "w") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return artifact


if __name__ == "__main__":
    main()
