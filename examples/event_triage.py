"""Event triage — the deterministic reference runtime (Slice 20 milestone).

Zero ML: YAML rule set -> DecisionPolicy -> FallbackChain -> Provenance,
all through HugrGate.decide(). Security events are triaged into
ignore / log / inspect / escalate.

Run:  venv/bin/python examples/event_triage.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate import (  # noqa: E402
    Backend,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
    HugrGate,
)
from hugrgate.backends.rules import RuleBackend  # noqa: E402
from hugrgate.errors import BackendError  # noqa: E402
from hugrgate.fallback import FallbackChain  # noqa: E402

TRIAGE_RULES_YAML = """
name: security-event-triage
rules:
  - name: critical-malware
    priority: 100
    if:
      all:
        - {field: severity, gte: 8}
        - {field: category, eq: malware}
    then: escalate
    confidence: 0.97

  - name: critical-anything
    priority: 90
    if: {field: severity, gte: 9}
    then: escalate
    confidence: 0.95

  - name: known-false-positive
    priority: 80
    if: {field: signature, eq: FP-HEARTBEAT}
    then: ignore
    confidence: 0.99

  - name: suspicious-high
    priority: 70
    if:
      any:
        - {field: severity, gte: 6}
        - {field: category, in: [phishing, intrusion]}
    then: inspect
    confidence: 0.88

  - name: noisy-low
    priority: 60
    if: {field: severity, lte: 2}
    then: ignore
    confidence: 0.92

  - name: default-log
    default: log
    confidence: 0.60
"""


class LegacyScorer(Backend):
    """A stand-in for the old scoring service, currently decommissioned.

    Always raises BackendError, so the fallback chain deterministically
    fails over to the rule backend on every event. In production this
    would be conditional (dead sensors, timeouts, 5xx responses).
    """

    name = "legacy-scorer"

    def capabilities(self):
        return {"spec_types": ["categorical"], "deterministic": True}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        raise BackendError("legacy scorer decommissioned",
                           sensor=state.get("sensor"))


def build_gate() -> HugrGate:
    """Assemble the milestone runtime: rules + policy + fallback."""
    spec_options = ["ignore", "log", "inspect", "escalate"]

    policy = DecisionPolicy(
        minimum_probability=0.5,
        maximum_latency_ms=500.0,
        fallback_behavior="safe_default",
    )

    rules = RuleBackend.from_yaml_text(TRIAGE_RULES_YAML)
    chain = FallbackChain(
        [LegacyScorer(), rules],
        policy=policy,
        safe_default="log",
    )

    gate = HugrGate()
    gate.register(chain)
    # Stash the shared objects for the demo/tests.
    gate.triage_spec = DecisionSpec(type="categorical", options=spec_options)  # type: ignore[attr-defined]
    gate.triage_policy = policy  # type: ignore[attr-defined]
    return gate


def triage(gate: HugrGate, event: Mapping[str, Any]) -> DecisionResult:
    """Triage one security event through the gate."""
    return gate.decide(event, gate.triage_spec, gate.triage_policy)  # type: ignore[attr-defined]


SAMPLE_EVENTS = [
    {"id": "e1", "severity": 9, "category": "malware",
     "sensor": "ids-01", "signature": "TROJAN-X"},
    {"id": "e2", "severity": 1, "category": "heartbeat",
     "sensor": "ids-02", "signature": "FP-HEARTBEAT"},
    {"id": "e3", "severity": 7, "category": "phishing",
     "sensor": "dead", "signature": "PHISH-221"},
    {"id": "e4", "severity": 4, "category": "auth",
     "sensor": "ids-03", "signature": "LOGIN-OK"},
]


def main() -> None:
    gate = build_gate()
    print("HugrGate deterministic milestone: event triage (zero ML)\n")
    for event in SAMPLE_EVENTS:
        result = triage(gate, event)
        trace = result.metadata.get("fallback_trace", [])
        print(f"event {event['id']}: severity={event['severity']} "
              f"category={event['category']} sensor={event['sensor']}")
        print(f"  -> {result.value}  (p={result.probability:.2f}, "
              f"backend={result.backend}, fallback_used={result.fallback_used})")
        for step in trace:
            detail = step.get("error", step.get("reason", ""))
            print(f"     chain: {step['backend']}: {step['outcome']} {detail}")
    print("\nProvenance records:")
    for record in gate.provenance.recent(10):
        print(f"  {record.request_hash} {record.value} "
              f"p={record.probability:.2f} fallback={record.fallback_used}")
    # Machine-readable dump of the last decision for good measure.
    last = gate.provenance.recent(1)[0]
    print("\nLast record:", json.dumps(
        {"value": last.value, "backend": last.backend,
         "fallback_used": last.fallback_used}, indent=2))


if __name__ == "__main__":
    main()
