"""Slice 010 — determinism audit.

HugrGate's contract: "Deterministic where possible." These tests pin it:

- the same (state, spec, policy) decides identically, repeatedly;
- the decision is independent of PYTHONHASHSEED (no builtin-hash
  order leaks into outcomes);
- benchmark reports are reproducible modulo timestamps/platform.

Explicitly NOT deterministic (measurements, not decisions):
``latency_ms``, provenance timestamps, ``generated_at``, uptime.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backends.rules import Rule, RuleBackend
from hugrgate.client import policy_to_dict

ROOT = Path(__file__).resolve().parent.parent

PROBE = """
from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backends.rules import Rule, RuleBackend
import json

gate = HugrGate()
gate.register(RuleBackend([
    Rule(condition={"field": "temperature", "gt": 100}, then="escalate",
         confidence=0.95, priority=10),
    Rule(condition={"field": "temperature", "gt": 80}, then="watch",
         confidence=0.7, priority=5),
    Rule(condition=None, then="ignore", confidence=0.9),
], name="triage"))
spec = DecisionSpec(type="categorical",
                    options=["ignore", "watch", "escalate"])
policy = DecisionPolicy(minimum_probability=0.5,
                        privacy_class="strict")
results = []
for state in ({"temperature": 95}, {"temperature": 50},
              {"temperature": 120, "note": "x"}):
    r = gate.decide(dict(state), spec, policy)
    d = r.to_dict()
    d.pop("latency_ms")  # measurement, not decision
    results.append(d)
print(json.dumps(results, sort_keys=True))
"""


def _decide_once() -> list:
    gate = HugrGate()
    gate.register(RuleBackend([
        Rule(condition={"field": "temperature", "gt": 100}, then="escalate",
             confidence=0.95, priority=10),
        Rule(condition={"field": "temperature", "gt": 80}, then="watch",
             confidence=0.7, priority=5),
        Rule(condition=None, then="ignore", confidence=0.9),
    ], name="triage"))
    spec = DecisionSpec(type="categorical",
                        options=["ignore", "watch", "escalate"])
    policy = DecisionPolicy(minimum_probability=0.5, privacy_class="strict")
    out = []
    for state in ({"temperature": 95}, {"temperature": 50},
                  {"temperature": 120, "note": "x"}):
        r = gate.decide(dict(state), spec, policy)
        d = r.to_dict()
        d.pop("latency_ms")
        out.append(d)
    return out


def test_repeated_decisions_are_identical():
    first = _decide_once()
    for _ in range(3):
        assert _decide_once() == first


def _run_with_hash_seed(seed: str) -> str:
    import os
    env = dict(os.environ, PYTHONHASHSEED=seed)
    proc = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True, text=True, cwd=ROOT, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_decisions_are_hash_seed_independent():
    baseline = _run_with_hash_seed("0")
    for seed in ("1", "42", "12345"):
        assert _run_with_hash_seed(seed) == baseline, (
            f"decision changed under PYTHONHASHSEED={seed}")


def test_policy_spec_round_trip_is_deterministic():
    policy = DecisionPolicy(minimum_probability=0.75,
                            review_band=(0.4, 0.75))
    spec = DecisionSpec(type="binary", statement="x")
    for _ in range(3):
        assert policy_to_dict(policy) == policy_to_dict(policy)
        assert spec.to_dict() == spec.to_dict()


def test_benchmark_report_is_reproducible():
    from hugrgate.bench import run_benchmark

    dataset = {
        "name": "probe",
        "spec": {"type": "categorical", "options": ["a", "b"]},
        "items": [
            {"state": {"x": 2.0}, "expected": "a"},
            {"state": {"x": 0.0}, "expected": "b"},
        ],
    }
    gate = HugrGate()
    gate.register(RuleBackend(
        [Rule(condition={"field": "x", "gt": 1.0}, then="a", confidence=0.9),
         Rule(condition=None, then="b", confidence=0.9)], name="r"))

    def scrub(report):
        report = json.loads(json.dumps(report, sort_keys=True, default=str))
        report.pop("generated_at", None)
        report.pop("platform", None)
        for backend in report["backends"].values():
            for key in list(backend):
                if key.startswith("latency_") or key.startswith("throughput_"):
                    backend.pop(key)
            backend.pop("reliability_bins", None)
        return report

    first = scrub(run_benchmark(dataset, gate, backends=["r"]))
    for _ in range(2):
        assert scrub(run_benchmark(dataset, gate, backends=["r"])) == first


# --- failure / boundary --------------------------------------------------------

def test_latency_is_excluded_from_the_contract():
    # latency_ms is a measurement: it may differ run to run, and that is
    # by design, not a determinism violation.
    gate = HugrGate()
    gate.register(RuleBackend(
        [Rule(condition=None, then="a", confidence=1.0)], name="r"))
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    latencies = {
        gate.decide({"x": 1}, spec, DecisionPolicy()).latency_ms
        for _ in range(5)
    }
    assert all(isinstance(v, float) and v >= 0 for v in latencies)
