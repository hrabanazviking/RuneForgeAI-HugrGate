"""Calibration trace spans. Slice 332.

Renders a calibration step as a span: which method ran, on how many
samples, what coverage it claimed, and — where a labeled holdout is
available — what coverage it *achieved*.  The empirical-coverage check
is the statistical heart of this slice: :func:`empirical_coverage`
computes the fraction of prediction sets containing the true label on
controlled data, and :func:`coverage_within_tolerance` judges it
against the nominal level with an exact binomial confidence interval,
so the test never "validates" by eyeballing.

Span attributes carry the method name, nominal level, sample count,
and achieved coverage — never the raw labels or scores.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from hugrgate.errors import TraceError
from hugrgate.observability.trace import Span, SpanContext, Tracer

__all__ = [
    "CALIBRATION_SPAN_NAME",
    "annotate_calibration",
    "calibration_span",
    "coverage_within_tolerance",
    "empirical_coverage",
]

#: Canonical span name for calibration spans.
CALIBRATION_SPAN_NAME = "hugrgate.calibration"


def empirical_coverage(prediction_sets: Sequence[Sequence[Any]],
                       true_labels: Sequence[Any]) -> float:
    """Fraction of prediction sets containing the true label.

    Both sequences must be non-empty and the same length; every set
    must be non-empty.  Raises :class:`~hugrgate.errors.TraceError`
    otherwise — a coverage number computed on malformed input is worse
    than no number.
    """
    if not prediction_sets or not true_labels:
        raise TraceError("empirical_coverage needs non-empty inputs")
    if len(prediction_sets) != len(true_labels):
        raise TraceError(
            f"length mismatch: {len(prediction_sets)} sets vs "
            f"{len(true_labels)} labels")
    hits = 0
    for pred_set, truth in zip(prediction_sets, true_labels, strict=True):
        if not pred_set:
            raise TraceError("prediction sets must be non-empty")
        if truth in pred_set:
            hits += 1
    return hits / len(true_labels)


def _binom_tail(n: int, p: float, k: int, upper: bool) -> float:
    """P(X >= k) if *upper* else P(X <= k), X ~ Bin(n, p).

    Computed in log space with log-sum-exp: the naive
    ``math.comb(n, i) * p**i`` form overflows for large *n* and the
    plain PMF recurrence underflows for moderate *p*.
    """
    if p <= 0.0:
        return 1.0 if (k <= 0 if upper else k >= 0) else 0.0
    if p >= 1.0:
        return 1.0 if (k <= n if upper else k >= n) else 0.0
    log_p = math.log(p)
    log_q = math.log(1.0 - p)
    log_pmf = (math.lgamma(n + 1) - math.lgamma(1) - math.lgamma(n + 1)
               + n * log_q)  # log P(X = 0)
    terms: list[float] = []
    for i in range(n + 1):
        if (upper and i >= k) or (not upper and i <= k):
            terms.append(log_pmf)
        if i < n:
            log_pmf += (math.log(n - i) - math.log(i + 1)
                        + log_p - log_q)
    if not terms:
        return 0.0
    peak = max(terms)
    return sum(math.exp(t - peak) for t in terms) * math.exp(peak)


def _binomial_ci_lower(k: int, n: int, alpha: float) -> float:
    """Clopper-Pearson lower bound for a binomial proportion."""
    if k == 0:
        return 0.0
    lo, hi = 0.0, 1.0
    target = alpha / 2.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _binom_tail(n, mid, k, upper=True) > target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def _binomial_ci_upper(k: int, n: int, alpha: float) -> float:
    if k == n:
        return 1.0
    lo, hi = 0.0, 1.0
    target = alpha / 2.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _binom_tail(n, mid, k, upper=False) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def coverage_within_tolerance(achieved: float, nominal: float, n: int,
                             alpha: float = 0.05) -> dict[str, Any]:
    """Judge an achieved coverage against the nominal level.

    Returns ``{"achieved", "nominal", "n", "ci_lower", "ci_upper",
    "within_tolerance"}`` where the verdict is True when the nominal
    level lies inside the exact (Clopper-Pearson) ``1 - alpha``
    confidence interval of the achieved rate.  No eyeballing, no
    invented thresholds.

    Metric/coverage assumptions (reported per slice 332):

    - samples are treated as i.i.d.; under distribution shift the
      interval is optimistic (see the drift slice 343);
    - ``n`` is the number of *labeled holdout* samples the coverage was
      measured on, never the training count.
    """
    if not 0.0 <= achieved <= 1.0:
        raise TraceError(f"achieved coverage out of bounds: {achieved!r}")
    if not 0.0 < nominal < 1.0:
        raise TraceError(f"nominal coverage must be in (0, 1): {nominal!r}")
    if n < 1:
        raise TraceError(f"n must be positive, got {n!r}")
    if not 0.0 < alpha < 1.0:
        raise TraceError(f"alpha must be in (0, 1): {alpha!r}")
    k = round(achieved * n)
    lower = _binomial_ci_lower(k, n, alpha)
    upper = _binomial_ci_upper(k, n, alpha)
    return {
        "achieved": achieved,
        "nominal": nominal,
        "n": n,
        "ci_lower": lower,
        "ci_upper": upper,
        "within_tolerance": lower <= nominal <= upper,
    }


def annotate_calibration(span: Span, method: str, nominal_coverage: float,
                         n_samples: int,
                         achieved_coverage: float | None = None,
                         extra: dict[str, Any] | None = None) -> Span:
    """Attach calibration metadata to an open span."""
    if not method:
        raise TraceError("calibration method name must be non-empty")
    if not 0.0 < nominal_coverage < 1.0:
        raise TraceError(
            f"nominal_coverage must be in (0, 1): {nominal_coverage!r}")
    if n_samples < 1:
        raise TraceError(f"n_samples must be positive, got {n_samples!r}")
    span.set_attribute("calibration.method", method)
    span.set_attribute("calibration.nominal_coverage",
                       round(nominal_coverage, 4))
    span.set_attribute("calibration.n_samples", n_samples)
    if achieved_coverage is not None:
        if not 0.0 <= achieved_coverage <= 1.0:
            raise TraceError(
                f"achieved_coverage out of bounds: {achieved_coverage!r}")
        span.set_attribute("calibration.achieved_coverage",
                           round(achieved_coverage, 4))
        verdict = coverage_within_tolerance(achieved_coverage,
                                            nominal_coverage, n_samples)
        span.add_event("calibration.coverage_checked", {
            "within_tolerance": verdict["within_tolerance"],
            "ci_lower": round(verdict["ci_lower"], 4),
            "ci_upper": round(verdict["ci_upper"], 4),
        })
    if extra:
        for key, value in extra.items():
            span.set_attribute(f"calibration.{key}", value)
    return span


@contextmanager
def calibration_span(tracer: Tracer, method: str,
                     parent: Span | SpanContext | None = None
                     ) -> Iterator[Span]:
    """Open a calibration span named for the method."""
    with tracer.trace(CALIBRATION_SPAN_NAME,
                      attributes={"calibration.method": method},
                      parent=parent) as span:
        yield span
