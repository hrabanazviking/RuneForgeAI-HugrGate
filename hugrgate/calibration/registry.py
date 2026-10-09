"""Calibration registry (rich catalog). Slice 091.

The legacy :class:`~hugrgate.calibration._base.CalibratorRegistry` maps
names to classes and nothing more — enough to rebuild a calibrator, not
enough to *choose* one.  This module layers a metadata catalog on top:

- :class:`CalibratorSpec` — per-calibrator metadata: family (parametric /
  nonparametric / bayesian / streaming / fallback), monotonicity, whether
  both classes are required to fit, streaming support, deprecation status;
- :func:`catalog` / :func:`spec` / :func:`find` — inspect and filter the
  catalog (e.g. "monotone streaming calibrators");
- :func:`describe` — human-readable summary for docs and the auto-selector
  (slice 092).

The legacy registry is untouched (backward compatibility); this catalog
syncs from it at import time and overlays the metadata table below.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from hugrgate.calibration._base import Calibrator, CalibratorRegistry
from hugrgate.errors import CalibrationError

__all__ = [
    "CalibratorSpec",
    "catalog",
    "describe",
    "find",
    "register_spec",
    "spec",
]


@dataclass
class CalibratorSpec:
    """Metadata describing one registered calibrator."""

    name: str
    cls: type[Calibrator]
    family: str  # parametric | nonparametric | bayesian | streaming | fallback
    monotone: bool
    needs_both_classes: bool
    streaming: bool
    description: str = ""
    deprecated: bool = False
    replaced_by: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cls"] = f"{self.cls.__module__}.{self.cls.__qualname__}"
        return d


_CATALOG: dict[str, CalibratorSpec] = {}

_METADATA: dict[str, dict[str, Any]] = {
    "platt": {
        "family": "parametric", "monotone": True,
        "needs_both_classes": True, "streaming": False,
        "description": "Platt scaling: sigmoid fit on scores (Newton).",
    },
    "isotonic": {
        "family": "nonparametric", "monotone": True,
        "needs_both_classes": False, "streaming": False,
        "description": "Isotonic regression via PAV; flexible, data-hungry.",
    },
    "temperature": {
        "family": "parametric", "monotone": True,
        "needs_both_classes": True, "streaming": False,
        "description": "Single-parameter temperature scaling on logits.",
    },
    "online": {
        "family": "streaming", "monotone": True,
        "needs_both_classes": False, "streaming": True,
        "description": "Incremental binned calibration with forgetting.",
    },
    "sliding-window": {
        "family": "streaming", "monotone": False,  # depends on inner
        "needs_both_classes": False, "streaming": True,
        "description": "Refits any batch calibrator on a recent window.",
        "extra": {"monotone": "inherits from inner calibrator"},
    },
    "beta-binomial": {
        "family": "bayesian", "monotone": False,
        "needs_both_classes": False, "streaming": False,
        "description": "Research adapter: per-bin Beta-Binomial posterior.",
    },
    "constant-prior": {
        "family": "fallback", "monotone": True,
        "needs_both_classes": False, "streaming": False,
        "description": "Fallback: always emits the class prior.",
    },
    "ensemble": {
        "family": "nonparametric", "monotone": False,
        "needs_both_classes": False, "streaming": False,
        "description": "Weighted average of member calibrator maps.",
        "extra": {"monotone": "iff all members are monotone"},
    },
}


def register_spec(spec_: CalibratorSpec) -> None:
    """Register (or override) a catalog spec."""
    if spec_.family not in ("parametric", "nonparametric", "bayesian",
                            "streaming", "fallback"):
        raise CalibrationError(f"unknown family {spec_.family!r}")
    _CATALOG[spec_.name] = spec_


def _sync() -> None:
    for name, cls in CalibratorRegistry.list().items():
        if name in _CATALOG:
            continue
        meta = _METADATA.get(name, {})
        register_spec(CalibratorSpec(
            name=name,
            cls=cls,
            family=meta.get("family", "nonparametric"),
            monotone=bool(meta.get("monotone", False)),
            needs_both_classes=bool(meta.get("needs_both_classes", True)),
            streaming=bool(meta.get("streaming", False)),
            description=meta.get("description", ""),
            extra=dict(meta.get("extra", {})),
        ))


def catalog() -> dict[str, CalibratorSpec]:
    """The full name → spec catalog (synced from the legacy registry)."""
    _sync()
    return dict(_CATALOG)


def spec(name: str) -> CalibratorSpec:
    """Spec for one calibrator; raises on unknown names."""
    _sync()
    try:
        return _CATALOG[name]
    except KeyError:
        raise CalibrationError(
            f"unknown calibrator {name!r}; known: {sorted(_CATALOG)}") from None


def find(family: str | None = None,
         monotone: bool | None = None,
         streaming: bool | None = None,
         needs_both_classes: bool | None = None,
         include_deprecated: bool = False) -> list[CalibratorSpec]:
    """Filter the catalog by metadata attributes."""
    out = []
    for s in catalog().values():
        if not include_deprecated and s.deprecated:
            continue
        if family is not None and s.family != family:
            continue
        if monotone is not None and s.monotone != monotone:
            continue
        if streaming is not None and s.streaming != streaming:
            continue
        if (needs_both_classes is not None
                and s.needs_both_classes != needs_both_classes):
            continue
        out.append(s)
    return sorted(out, key=lambda s: s.name)


def describe() -> list[dict[str, Any]]:
    """JSON-serializable summary of the whole catalog."""
    return [s.as_dict() for s in find(include_deprecated=True)]
