"""Autonomous optimization for HugrGate. Campaign XIX, slices 451-475.

The :mod:`hugrgate.autotune` package lets HugrGate *safely tune itself*:
thresholds, confidence gates, latency budgets, cache policy, batch sizes,
backend order, ensemble weights, and calibration choice can be adjusted
automatically against declared objectives, guarded by constraints, safety
limits, provenance, and rollback triggers.

The pipeline per tuning cycle is::

    tuners propose -> constraints validate -> safety limits check
        -> mode driver (offline/shadow/canary/applied) disposes
        -> provenance records everything

Slices:

- 451 controller (this package's spine): :mod:`hugrgate.autotune.controller`
- 452 objectives: :mod:`hugrgate.autotune.objectives`
- 453 constraints: :mod:`hugrgate.autotune.constraints`
- 454-465 tuners: :mod:`hugrgate.autotune.tuners`
- 466-468 modes: :mod:`hugrgate.autotune.modes`
- 469 rollback: :mod:`hugrgate.autotune.rollback`
- 470 provenance: :mod:`hugrgate.autotune.provenance`
- 471 reproducibility: :mod:`hugrgate.autotune.repro`
- 472 safety limits: :mod:`hugrgate.autotune.limits`
- 473 adversarial harness: :mod:`hugrgate.autotune.adversarial`
- 474 benchmark: :mod:`hugrgate.autotune.benchmark`
- 475 release gate: :mod:`hugrgate.autotune.release`

Local-first: the optimizer never phones home; all data is recorded
telemetry or operator-supplied datasets.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "19.0.0"
