"""Policy playbook — thresholds, review bands, privacy (Slices 5/40/41).

Shows what DecisionPolicy actually does at runtime:
- minimum_probability → abstention instead of a guess,
- review_band → a "review" verdict distinct from accept/abstain,
- privacy_class="strict" → raw input redacted from provenance,
- allowed_backends → policy-level backend selection.

Run:  venv/bin/python examples/policy_playbook.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate import (  # noqa: E402
    Abstention,
    DecisionPolicy,
    DecisionSpec,
)
from hugrgate.server import build_gate  # noqa: E402

SPEC = DecisionSpec(type="categorical",
                    options=["ignore", "log", "investigate", "escalate"])
STATE = {"alert": "ESCALATE: ransomware signature detected "
                  "on web-01 — isolate now."}
VAGUE = {"alert": "something happened somewhere, maybe"}


def main() -> None:
    gate = build_gate()

    # 1. Strict threshold → honest abstention.
    try:
        gate.decide(VAGUE, SPEC, DecisionPolicy(minimum_probability=0.99),
                    backend_name="keyword")
        print("1. strict threshold : decided (unexpected)")
    except Abstention as e:
        print(f"1. strict threshold : abstained ({e.reason})")

    # 2. Review band → accepted but flagged for human review.
    policy = DecisionPolicy(minimum_probability=0.2,
                            review_band=(0.2, 0.6))
    result = gate.decide(STATE, SPEC, policy, backend_name="keyword")
    print(f"2. review band     : value={result.value} "
          f"verdict={result.metadata['policy_verdict']} "
          f"(p={result.probability:.3f})")

    # 3. Privacy strict → provenance carries no raw input.
    gate.decide(STATE, SPEC, DecisionPolicy(privacy_class="strict"),
                backend_name="keyword")
    record = gate.provenance.recent(1)[0]
    print(f"3. privacy=strict  : provenance metadata={record.metadata} "
          "(no state keys)")

    gate.decide(STATE, SPEC, DecisionPolicy(), backend_name="keyword")
    record = gate.provenance.recent(1)[0]
    print(f"   privacy=standard: provenance metadata={record.metadata}")

    # 4. Backend allow-list.
    blocked = DecisionPolicy(allowed_backends=["uniform"])
    result = gate.decide(STATE, SPEC, blocked)
    print(f"4. allow-list      : backend={result.backend} "
          f"(keyword was available but not allowed)")


if __name__ == "__main__":
    main()
