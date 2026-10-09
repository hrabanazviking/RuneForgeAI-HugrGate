"""Energy-aware evaluation — decision quality per joule. Slice 365.

Two energy paths, honest about which is in play:

- *Measured*: when a :class:`hugrgate.edge.power.PowerSource` is
  supplied, power is sampled around every decision and per-decision
  energy is ``avg_mw * latency_s`` (millijoules).  On this VM there is
  no real power sensor — :class:`MockPowerSource` stands in, and the
  report marks the path ``"measured"`` only when every sample
  succeeded.  Real-hardware validation is still needed for the
  measured path (Yrsa Execution Law 13).
- *Model*: :class:`EnergyModel` per-backend millijoule rates, the lab
  fallback (mirrors :class:`CostModel`).

The :class:`EnergyReport` carries accuracy-per-joule, the Pareto
frontier over (energy, accuracy) — reusing
:func:`hugrgate.evlab.costaware.pareto_frontier`, not duplicating it —
and budget queries, plus a documented CO2e estimate helper.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.bench import accuracy as _bench_accuracy
from hugrgate.core import HugrGate
from hugrgate.edge.power import PowerSource
from hugrgate.errors import Abstention, EvalError
from hugrgate.evlab.costaware import pareto_frontier
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "EnergyModel",
    "EnergyReport",
    "co2e_grams",
    "energy_aware_evaluate",
]


@dataclass
class EnergyModel:
    """Lab fallback: millijoules per decision by backend name."""

    rates_mj: dict[str, float] = field(default_factory=dict)
    default_rate_mj: float = 0.0

    def rate_for(self, backend: str) -> float:
        rate = self.rates_mj.get(backend, self.default_rate_mj)
        if rate < 0:
            raise EvalError(
                f"negative energy rate for backend {backend!r}: {rate}"
            )
        return rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "rates_mj": dict(self.rates_mj),
            "default_rate_mj": self.default_rate_mj,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EnergyModel:
        return cls(
            rates_mj=dict(data.get("rates_mj", {})),
            default_rate_mj=data.get("default_rate_mj", 0.0),
        )


def co2e_grams(energy_mj: float,
               grid_intensity_g_per_kwh: float = 400.0) -> float:
    """Documented CO2e estimate: mJ -> kWh * grid intensity.

    The default 400 g/kWh is a rough global average, not a claim
    about any specific grid — callers doing carbon accounting must
    supply their own intensity.
    """
    if energy_mj < 0:
        raise EvalError(f"energy must be >= 0, got {energy_mj}")
    if grid_intensity_g_per_kwh <= 0:
        raise EvalError("grid intensity must be positive")
    kwh = energy_mj / 3_600_000_000.0  # 1 kWh = 3.6e9 mJ
    return kwh * grid_intensity_g_per_kwh


def _sample_mw(source: PowerSource | None) -> float | None:
    """One power sample; None when the source is absent/unreadable."""
    if source is None:
        return None
    try:
        value = source.read_mw()
    except Exception:  # noqa: BLE001 - sensors fail; fall back to the model
        return None
    return value if value is not None and value >= 0 else None


@dataclass
class EnergyReport:
    """Per-backend energy/quality results + queries (slice 365)."""

    backends: dict[str, dict[str, Any]]
    pareto: list[str]
    n_items: int

    def most_efficient(self) -> tuple[str | None, float | None]:
        """(backend, accuracy_per_joule) maximizing efficiency."""
        scored = [
            (b, info["accuracy_per_joule"])
            for b, info in self.backends.items()
            if isinstance(info["accuracy_per_joule"], (int, float))
        ]
        if not scored:
            return None, None
        return max(scored, key=lambda kv: kv[1])

    def best_under_energy_budget(
        self, budget_mj: float
    ) -> tuple[str | None, float | None]:
        """(backend, accuracy) maximizing accuracy within ``budget_mj``."""
        if budget_mj < 0:
            raise EvalError(f"budget must be >= 0, got {budget_mj}")
        candidates = [
            (b, info["accuracy"])
            for b, info in self.backends.items()
            if info["total_energy_mj"] <= budget_mj
            and isinstance(info["accuracy"], (int, float))
        ]
        if not candidates:
            return None, None
        return max(candidates, key=lambda kv: kv[1])

    def _backend(self, backend: str) -> dict[str, Any]:
        try:
            return self.backends[backend]
        except KeyError:
            raise EvalError(f"unknown backend {backend!r}") from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backends": {b: dict(info)
                         for b, info in self.backends.items()},
            "pareto": list(self.pareto),
            "n_items": self.n_items,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EnergyReport:
        return cls(
            backends={b: dict(info)
                      for b, info in data["backends"].items()},
            pareto=list(data["pareto"]),
            n_items=data["n_items"],
        )


def energy_aware_evaluate(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backends: Sequence[str] | None = None,
    energy_model: EnergyModel | None = None,
    power_source: PowerSource | None = None,
    policy: DecisionPolicy | None = None,
    max_items: int | None = None,
) -> EnergyReport:
    """Evaluate backends for quality *and* energy; return an EnergyReport."""
    model = energy_model or EnergyModel()
    policy = policy or DecisionPolicy()
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    if not items:
        raise EvalError("energy-aware evaluation needs at least one item")
    names = list(backends) if backends is not None \
        else [b.name for b in gate.registry.supporting(spec)]
    if not names:
        raise EvalError("no backends available for this dataset's spec")

    results: dict[str, dict[str, Any]] = {}
    for backend in names:
        pairs: list[tuple[Any, DecisionResult]] = []
        energies: list[float] = []
        n_measured = 0
        for item in items:
            expected = item.get("expected")
            before_mw = _sample_mw(power_source)
            try:
                result = gate.decide(dict(item["state"]), spec, policy,
                                     backend_name=backend)
            except Abstention:
                continue
            after_mw = _sample_mw(power_source)
            pairs.append((expected, result))
            if before_mw is not None and after_mw is not None:
                # Measured: average power over the decision's latency.
                energies.append(
                    (before_mw + after_mw) / 2.0
                    * (result.latency_ms / 1000.0)
                )
                n_measured += 1
            else:
                energies.append(model.rate_for(backend))
        accuracy = _bench_accuracy(pairs)
        n = len(pairs)
        total_mj = sum(energies)
        if n_measured == n and n > 0:
            source = "measured"
        elif n_measured == 0:
            source = "model"
        else:
            source = "mixed"
        results[backend] = {
            "accuracy": accuracy,
            "n_decided": n,
            "total_energy_mj": total_mj,
            "energy_per_decision_mj": (total_mj / n) if n else None,
            "energy_source": source,
            "n_measured": n_measured,
            "accuracy_per_joule": (
                accuracy / (total_mj / 1000.0)
                if accuracy is not None and total_mj > 0 else None
            ),
            "co2e_grams": co2e_grams(total_mj),
        }
    frontier = pareto_frontier({
        name: (info["total_energy_mj"], info["accuracy"] or 0.0)
        for name, info in results.items()
    })
    return EnergyReport(backends=results, pareto=frontier,
                        n_items=len(items))
