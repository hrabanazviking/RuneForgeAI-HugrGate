"""HugrGate observability (Campaign XIV) — make every important decision
path measurable, inspectable, and explainable.

Campaign VI's :mod:`hugrgate.adaptive.telemetry` keeps a routing-decision
dataset for learning; this package is the *operations* layer around it:
metrics (:mod:`metrics`), distributed traces (:mod:`trace`), OpenTelemetry
interop (:mod:`otel`), structured logging (:mod:`logschema`), Prometheus
export (:mod:`prometheus`), dashboards (:mod:`dashboard`), SLOs
(:mod:`slo`, :mod:`slo_eval`), alerts (:mod:`alerts`), and explanation
reports (:mod:`explain`, :mod:`replay`).

The package is stdlib-only (the OTel SDK itself is an optional extra)
and sits above ``spec`` / ``result`` / ``backend`` / ``policy``,
provenance, privacy, and drift detection — it never reaches into the
service layer.  Submodules are imported individually
(``from hugrgate.observability import metrics``); this ``__init__``
stays empty so importing the package never pulls the whole layer in.
"""

from __future__ import annotations

__all__: list[str] = []
