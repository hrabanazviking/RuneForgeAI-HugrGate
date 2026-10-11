"""Slice 056 measurement artifact: measured vs declared rung latencies.

Runs real decisions through LadderRouterV2 with backends whose true
latencies are fixed sleeps. The LatencyTracker learns the EMA of measured
rung latencies; this script compares the learned EMA against the
*baseline* — the backends' declared estimated_latency() values — and
writes benchmarks/routing_latency_056.json. No numbers are invented:
every figure below is measured on this machine, on this run.

Usage: python benchmarks/routing_latency_056.py [--rounds N] [--out PATH]
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
from hugrgate.routing import (DynamicRungPlanner, LadderRouterV2,
                              LatencyTracker)

TRUE_LATENCIES = {"tortoise": 120.0, "hare": 15.0, "mid": 55.0}
DECLARED_LATENCIES = {"tortoise": 100.0, "hare": 100.0, "mid": 100.0}
# Probabilities are staggered in registry-insertion order so every round
# climbs through all three rungs (declared latencies are all the flat
# 100ms default, so insertion order rules): only the last clears the 0.9
# gate, so every backend is measured every round.
TRUE_PROBS = {"tortoise": 0.5, "hare": 0.6, "mid": 0.99}


class SleepBackend(Backend):
    def __init__(self, name, true_ms, declared_ms, prob):
        self.name = name
        self._true = true_ms
        self._declared = declared_ms
        self._prob = prob

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        time.sleep(self._true / 1000.0)
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)

    def estimated_latency(self):
        return self._declared


def _round_floats(obj):
    """Recursively round every float to 6 dp (slice 11: kill float noise)."""
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v) for v in obj]
    return obj


def main() -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "routing_latency_056.json"))
    args = ap.parse_args()

    registry = BackendRegistry()
    backends = {}
    for name, true_ms in TRUE_LATENCIES.items():
        b = SleepBackend(name, true_ms, DECLARED_LATENCIES[name],
                         prob=TRUE_PROBS[name])
        registry.register(b)
        backends[name] = b

    tracker = LatencyTracker(alpha=0.3, min_samples=3)
    router = LadderRouterV2(
        registry,
        ladders={"categorical": [LadderRung(n, 0.9)
                                 for n in TRUE_LATENCIES]},
        planner=DynamicRungPlanner(registry),
        latency_tracker=tracker)
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy(minimum_probability=0.9)

    for _ in range(args.rounds):
        router.decide({}, spec, policy)

    per_backend = {}
    for name, b in backends.items():
        declared = b.estimated_latency()
        measured = tracker.estimate(b)
        true = TRUE_LATENCIES[name]
        per_backend[name] = {
            "true_latency_ms": true,
            "declared_latency_ms": declared,
            "measured_ema_ms": measured,
            "tracker_samples": tracker.samples(name),
            "declared_abs_error_ms": round(abs(declared - true), 3),
            "measured_abs_error_ms": round(abs(measured - true), 3),
        }

    declared_err = sum(v["declared_abs_error_ms"]
                       for v in per_backend.values())
    measured_err = sum(v["measured_abs_error_ms"]
                       for v in per_backend.values())
    artifact = {
        "slice": "056",
        "description": "measured EMA rung latencies vs declared estimates",
        "rounds": args.rounds,
        "tracker": {"alpha": tracker.alpha,
                    "min_samples": tracker.min_samples},
        "per_backend": per_backend,
        "baseline_total_abs_error_ms": round(declared_err, 3),
        "measured_total_abs_error_ms": round(measured_err, 3),
        "error_reduction_factor": (round(declared_err / measured_err, 2)
                                   if measured_err > 0 else None),
    }
    artifact = _round_floats(artifact)
    with open(args.out, "w") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return artifact


if __name__ == "__main__":
    main()
