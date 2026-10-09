"""Install smoke probe for the fresh-clone gauntlet (slice 477).

Runs inside the *freshly installed* environment (never the repo
checkout): imports the installed ``hugrgate`` package, verifies it did
not come from a source checkout, registers a minimal deterministic
backend, runs the gate end to end on a categorical spec, and checks
the CLI entry point resolves. Any failure raises — the shell wrapper
reports it.
"""

from __future__ import annotations

import importlib.metadata
import sys
from typing import Any


def main() -> None:
    import hugrgate
    from hugrgate import DecisionPolicy, DecisionResult, DecisionSpec, HugrGate
    from hugrgate.backend import Backend

    # Must be the installed distribution, not a repo checkout on sys.path.
    dist = importlib.metadata.distribution("hugrgate")
    assert dist is not None, "hugrgate distribution metadata missing"
    location = hugrgate.__file__ or ""
    assert "site-packages" in location or "dist-packages" in location, (
        f"hugrgate imported from {location!r}, not from an installed wheel/sdist"
    )

    class SmokeBackend(Backend):
        name = "smoke"

        def capabilities(self) -> dict[str, Any]:
            return {"spec_types": ["categorical"]}

        def supports(self, spec: DecisionSpec) -> bool:
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None) -> DecisionResult:
            options = spec.options or ["a"]
            return DecisionResult(
                value=options[0],
                probability=1.0,
                distribution={o: 1.0 if o == options[0] else 0.0
                              for o in options},
            )

    gate = HugrGate()
    gate.register(SmokeBackend())
    spec = DecisionSpec(type="categorical", options=["yes", "no"])
    result = gate.decide({"q": 1}, spec, DecisionPolicy())
    assert result.value in ("yes", "no"), f"bad value {result.value!r}"
    gate.close()

    # CLI entry point resolves.
    from hugrgate.cli import main as cli_main

    assert callable(cli_main)
    print(f"install smoke OK: hugrgate {dist.version} at {location}")


if __name__ == "__main__":
    sys.exit(main())
