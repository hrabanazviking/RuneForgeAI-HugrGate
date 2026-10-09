"""Per-client policies — server-side policy control (Slice 42).

The daemon maps an X-Client-Id header to a server-side DecisionPolicy
loaded from a JSON file. The server-side policy wins over any policy in
the request body: untrusted clients cannot talk themselves into looser
thresholds.

Run:  venv/bin/python examples/client_policies.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from hugrgate.client import policy_to_dict  # noqa: E402
from hugrgate import DecisionPolicy  # noqa: E402
from hugrgate.daemon import DaemonConfig, create_daemon_app  # noqa: E402

SPEC = {"type": "categorical",
        "options": ["ignore", "log", "investigate", "escalate"]}
STATE = {"alert": "something happened somewhere, maybe"}


def main() -> None:
    policies = {
        # This client may only act on near-certain decisions.
        "cautious-etl": policy_to_dict(
            DecisionPolicy(minimum_probability=0.99)),
        # This client gets the permissive default.
        "dashboard": policy_to_dict(DecisionPolicy(minimum_probability=0.0)),
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json",
                                     delete=False) as f:
        json.dump(policies, f)
        path = f.name

    app = create_daemon_app(DaemonConfig(client_policies_path=path,
                                         batch_window_ms=2))
    with TestClient(app) as tc:
        body = {"spec": SPEC, "state": STATE, "backend_name": "keyword",
                # A sneaky client tries to smuggle a loose policy...
                "policy": {"minimum_probability": 0.0}}

        r = tc.post("/decide", json=body,
                    headers={"x-client-id": "cautious-etl"})
        print("cautious-etl :", r.json())

        r = tc.post("/decide", json=body,
                    headers={"x-client-id": "dashboard"})
        print("dashboard    :", r.json()["value"],
              f"(p={r.json()['probability']:.3f})")

        print("known clients:", tc.get("/daemon").json()["client_policies"])
    print("\nThe cautious client's smuggled policy was ignored: "
          "server-side policy wins.")


if __name__ == "__main__":
    main()
