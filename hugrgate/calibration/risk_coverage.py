"""Risk-coverage curves. Slice 087.

The loss-based sibling of slice 086's selective (accuracy) curves.  Given
per-decision confidences and *losses* (0/1 error by default, but any bounded
loss works - e.g. a cost-weighted error), the risk-coverage (RC) curve shows
the mean loss over the kept decisions as coverage shrinks toward the most
confident sliver.

- :func:`risk_coverage_curve` - rows ``{threshold, coverage, risk, n}``;
- :func:`aurc` - area under the RC curve (lower is better), with the oracle
  curve (sorted by true loss) as the reference: ``excess = aurc - aurc*``
  measures how much the confidence ranking leaves on the table;
- :func:`coverage_at_risk` - the abstention-policy lookup: largest coverage
  with risk ≤ target;
- :func:`risk_at_coverage` - interpolated risk at a target coverage.
"""

from __future__ import annotations

from collections.abc import Sequence

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]


def _require_numpy() -> None:
    """Deliberate error when the optional numpy dependency is absent."""
    if np is None:  # pragma: no cover - optional dependency
        raise CalibrationError(
            "numpy is required for calibration; install the 'ml' extra: pip install 'hugrgate[ml]'"
        )

from hugrgate.errors import CalibrationError

__all__ = [
    "aurc",
    "coverage_at_risk",
    "oracle_aurc",
    "risk_at_coverage",
    "risk_coverage_curve",
]


def _check(confidences: Sequence[float],
           losses: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    _require_numpy()
    c = np.asarray(list(confidences), dtype=float)
    la = np.asarray(list(losses), dtype=float)
    if c.shape != la.shape:
        raise CalibrationError("confidences/losses length mismatch")
    if c.size == 0:
        raise CalibrationError("empty inputs")
    if np.any(~np.isfinite(c)) or np.any(~np.isfinite(la)):
        raise CalibrationError("inputs must be finite")
    if np.any((c < 0.0) | (c > 1.0)):
        raise CalibrationError("confidences must be in [0, 1]")
    if np.any(la < 0.0):
        raise CalibrationError("losses must be non-negative")
    return c, la


def risk_coverage_curve(confidences: Sequence[float],
                        losses: Sequence[float],
                        n_points: int = 50) -> list[dict[str, float]]:
    """Risk-coverage curve: mean loss over the top-confidence fraction."""
    c, la = _check(confidences, losses)
    if n_points < 2:
        raise CalibrationError("n_points must be ≥ 2")
    order = np.argsort(-c, kind="stable")
    cs, ls = c[order], la[order]
    n = c.size
    rows: list[dict[str, float]] = []
    for i in range(n_points):
        k = max(1, round(n * (i + 1) / n_points))
        rows.append({
            "threshold": float(cs[k - 1]),
            "coverage": float(k) / float(n),
            "risk": float(ls[:k].mean()),
            "n": float(k),
        })
    return rows


def _area(curve: Sequence[dict[str, float]]) -> float:
    rows = sorted(curve, key=lambda r: r["coverage"])
    xs = np.array([r["coverage"] for r in rows])
    ys = np.array([r["risk"] for r in rows])
    if xs[0] > 0.0:
        xs = np.concatenate([[0.0], xs])
        ys = np.concatenate([[ys[0]], ys])
    return float(np.trapezoid(ys, xs))


def aurc(curve: Sequence[dict[str, float]]) -> float:
    """Area under the risk-coverage curve (lower is better)."""
    _require_numpy()
    rows = list(curve)
    if len(rows) < 2:
        raise CalibrationError("need at least 2 curve points")
    return _area(rows)


def oracle_aurc(losses: Sequence[float], n_points: int = 50) -> float:
    """AURC of the oracle ranking (sorted by true loss ascending).

    No confidence function can beat this; the gap ``aurc - oracle_aurc``
    is the ranking regret.
    """
    _require_numpy()
    la = np.asarray(list(losses), dtype=float)
    if la.size == 0:
        raise CalibrationError("empty inputs")
    if np.any(~np.isfinite(la)) or np.any(la < 0.0):
        raise CalibrationError("losses must be finite and non-negative")
    # Oracle keeps the lowest-loss decisions first at every coverage.
    ranked = np.sort(la)
    n = ranked.size
    rows = [{"coverage": (k := max(1, round(n * (i + 1) / n_points))) / n,
             "risk": float(ranked[:k].mean())}
            for i in range(n_points)]
    return _area(rows)


def risk_at_coverage(curve: Sequence[dict[str, float]],
                     coverage: float) -> float:
    """Interpolated risk at a target coverage."""
    _require_numpy()
    if not 0.0 < coverage <= 1.0:
        raise CalibrationError("coverage must be in (0, 1]")
    rows = sorted(curve, key=lambda r: r["coverage"])
    return float(np.interp(coverage,
                           [r["coverage"] for r in rows],
                           [r["risk"] for r in rows]))


def coverage_at_risk(curve: Sequence[dict[str, float]],
                     risk: float) -> float:
    """Largest coverage whose risk stays ≤ ``risk`` (abstention policy)."""
    if risk < 0.0:
        raise CalibrationError("risk must be non-negative")
    best = 0.0
    for r in curve:
        if r["risk"] <= risk:
            best = max(best, float(r["coverage"]))
    return float(best)
