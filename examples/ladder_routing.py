"""Milestone — the intelligence ladder end to end (Slice 39).

"Least expensive sufficient intelligence" on a mixed triage workload::

    rules  ->  logreg-stub  ->  embedding prototype  ->  abstain

Cheap deterministic rules answer the easy cases; a tiny learned model takes
the medium ones; a hash-embedding prototype classifier reads the texty
ones; anything left over abstains instead of guessing. Every routing
decision is auditable rung-by-rung.

Run:  ./venv/bin/python examples/ladder_routing.py
"""

from __future__ import annotations

import math
import sys
from typing import Dict, Mapping, Optional

sys.path.insert(0, ".")

from hugrgate import (
    Backend, BackendRegistry, DecisionPolicy, DecisionResult, DecisionSpec,
)
from hugrgate.backends.embedding import HashEmbedder, PrototypeBackend
from hugrgate.errors import Abstention
from hugrgate.ladder import LadderRouter, LadderRung
from hugrgate.provenance import ProvenanceStore

SPEC = DecisionSpec(type="categorical",
                    options=["ignore", "log", "inspect", "escalate"])


# --------------------------------------------------------------------------
# Stand-in rungs. (Batch B/C ship the real RuleBackend/logreg; these tiny
# in-example stand-ins keep the milestone runnable on the Batch A contract.)

class SimpleRulesBackend(Backend):
    """Deterministic triage rules. High confidence on match, meek off-match."""

    name = "rules"

    def capabilities(self) -> Dict:
        return {"spec_types": ["categorical"], "rules": 3}

    def supports(self, spec) -> bool:
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None) -> DecisionResult:
        sev = float(state.get("severity", 0))
        msg = str(state.get("message", "")).lower()
        match = None
        if sev >= 9:
            match = ("escalate", 0.98)
        elif "breach" in msg:
            match = ("escalate", 0.95)
        elif sev <= 2:
            match = ("ignore", 0.97)
        if match:
            value, conf = match
        else:
            value, conf = "log", 0.30  # no rule fired: not confident
        n = len(spec.options)
        rest = (1.0 - conf) / (n - 1)
        return DecisionResult(
            value=value, probability=conf,
            distribution={o: (conf if o == value else rest)
                          for o in spec.options},
            uncertainty=1.0 - conf, backend=self.name,
            model="triage-rules-v1")

    def estimated_latency(self) -> float:
        return 1.0


class LogRegStub(Backend):
    """Hand-rolled logistic-weights stand-in for the Batch C logreg backend."""

    name = "logreg-stub"
    WEIGHTS = {  # (severity_w, keyword_w, bias) per class
        "ignore": (-2.0, -1.0, 0.8),
        "log": (-0.5, 0.0, 0.4),
        "inspect": (1.0, 1.5, -0.6),
        "escalate": (2.5, 2.0, -1.2),
    }
    KEYWORDS = ("unauthorized", "malware", "breach", "intrusion")

    def capabilities(self) -> Dict:
        return {"spec_types": ["categorical"], "model": "stub-weights-v1"}

    def supports(self, spec) -> bool:
        return spec.type == "categorical"

    def _features(self, state: Mapping) -> tuple:
        sev = float(state.get("severity", 0)) / 10.0
        msg = str(state.get("message", "")).lower()
        kw = 1.0 if any(k in msg for k in self.KEYWORDS) else 0.0
        return sev, kw

    def evaluate(self, state, spec, context=None) -> DecisionResult:
        sev, kw = self._features(state)
        logits = {c: ws * sev + wk * kw + b
                  for c, (ws, wk, b) in self.WEIGHTS.items()}
        mx = max(logits.values())
        exps = {c: math.exp(v - mx) for c, v in logits.items()}
        total = sum(exps.values())
        dist = {c: exps[c] / total for c in spec.options}
        value = max(dist, key=dist.get)
        return DecisionResult(
            value=value, probability=dist[value], distribution=dist,
            uncertainty=1.0 - dist[value], backend=self.name,
            model="stub-weights-v1",
            metadata={"logits": {c: round(v, 3)
                                 for c, v in logits.items()}})

    def estimated_latency(self) -> float:
        return 8.0


def build_router() -> LadderRouter:
    registry = BackendRegistry()
    registry.register(SimpleRulesBackend())
    registry.register(LogRegStub())
    proto = PrototypeBackend(HashEmbedder(dim=256), temperature=0.25)
    proto.fit([
        ("server rebooted cleanly nightly job ok", "ignore"),
        ("heartbeat normal all systems nominal", "ignore"),
        ("disk usage at 72 percent within threshold", "log"),
        ("user login failed three times unusual hour", "inspect"),
        ("unauthorized access attempt from foreign ip", "escalate"),
        ("malware signature detected on endpoint", "escalate"),
    ])
    registry.register(proto)

    return LadderRouter(
        registry,
        rungs=[
            LadderRung("rules", min_confidence=0.90,
                       latency_budget_ms=5.0),
            LadderRung("logreg-stub", min_confidence=0.70,
                       latency_budget_ms=30.0),
            LadderRung("prototype-embedder", min_confidence=0.55,
                       latency_budget_ms=200.0),
        ],
        provenance=ProvenanceStore())


WORKLOAD = [
    # Easy: rules fire with high confidence -> rung 1.
    {"severity": 10, "message": "critical breach detected on db host"},
    {"severity": 1, "message": "routine heartbeat all nominal"},
    # Medium: no rule fires; learned weights are confident -> rung 2.
    {"severity": 8, "message": "intrusion signature matched on dmz host"},
    # Texty: weights unsure; near-verbatim prototype match -> rung 3.
    {"severity": 4,
     "message": "unauthorized access attempt from foreign ip blocked"},
    # Hopeless: nothing knows this -> abstain.
    {"severity": 5, "message": "ambiguous telemetry anomaly"},
]


def show(router: LadderRouter, state: dict,
         policy: Optional[DecisionPolicy] = None) -> None:
    print(f"state: severity={state['severity']!r} "
          f"message={state['message']!r}")
    try:
        result = router.decide(state, SPEC, policy or DecisionPolicy())
        print(f"  => {result.value!r} p={result.probability:.3f} "
              f"via {result.metadata['ladder_backend']} "
              f"(rung {result.metadata['ladder_rung'] + 1})")
    except Abstention as e:
        print(f"  => ABSTAIN ({e.reason})")
    for entry in router.last_audit:
        mark = {"accepted": "WIN", "below_confidence": "low-conf",
                "skipped_latency_budget": "skipped-budget"}.get(
                    entry.outcome, entry.outcome)
        prob = (f" p={entry.probability:.3f}"
                if entry.probability is not None else "")
        print(f"     rung {entry.rung_index + 1} "
              f"{entry.backend_name:18s} [{mark}]{prob} {entry.detail}")
    print()


def main() -> int:
    router = build_router()
    print("=== HugrGate intelligence ladder: rules -> logreg -> "
          "embedding -> abstain ===\n")
    for state in WORKLOAD:
        show(router, dict(state))

    print("=== Act 2: latency budget prunes the slow rung ===")
    print("policy: maximum_latency_ms=10 (prototype needs ~15ms)\n")
    tight = DecisionPolicy(maximum_latency_ms=10.0)
    show(router, {"severity": 4,
                  "message": "unauthorized access attempt from foreign ip"},
         tight)

    print(f"provenance records kept: {router.provenance.count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
