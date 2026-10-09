"""Time-decay weighting. Slice 308.

Old decisions should whisper; new ones should speak. This module is
the single home for exponential time-decay math across the memory
package (slice 306's retrieval used a private copy — now refactored
onto this module):

- :func:`decay_weight` — ``0.5 ** (age / half_life)`` in (0, 1];
- :func:`half_life_for_horizon` — pick a half-life from a horizon and
  a target residual weight;
- :func:`effective_count` — recency-weighted sample size ("how much
  memory do these episodes amount to?");
- :func:`decayed_mean` — recency-weighted mean of values.

Negative ages (clock skew) are clamped to 0 with the weight of a
fresh episode rather than raising: a slightly wrong clock must not
break recall.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = [
    "decay_weight",
    "decayed_mean",
    "effective_count",
    "half_life_for_horizon",
]


def _check_half_life(half_life_seconds: float) -> float:
    if not math.isfinite(half_life_seconds) or half_life_seconds <= 0:
        raise ValueError(
            f"half_life_seconds must be finite and > 0, got "
            f"{half_life_seconds}")
    return half_life_seconds


def decay_weight(age_seconds: float, half_life_seconds: float) -> float:
    """Exponential decay weight for an age; 1.0 when fresh.

    ``weight(half_life) == 0.5`` by construction. Negative ages are
    clamped to 0 (clock-skew tolerance). Astronomically old ages
    underflow to exactly 0.0, so the range is [0, 1].
    """
    _check_half_life(half_life_seconds)
    age = max(0.0, age_seconds)
    return 0.5 ** (age / half_life_seconds)


def half_life_for_horizon(horizon_seconds: float,
                          target_weight: float = 0.01) -> float:
    """Half-life making ``decay_weight(horizon) == target_weight``.

    Lets operators say "a month-old decision should count for ~1%"
    without doing the algebra. ``target_weight`` must be in (0, 1).
    """
    if horizon_seconds <= 0:
        raise ValueError(
            f"horizon_seconds must be > 0, got {horizon_seconds}")
    if not 0.0 < target_weight < 1.0:
        raise ValueError(
            f"target_weight must be in (0, 1), got {target_weight}")
    # 0.5 ** (horizon / half_life) = target  =>  half_life =
    # horizon * ln(0.5) / ln(target)
    return horizon_seconds * math.log(0.5) / math.log(target_weight)


def effective_count(ages_seconds: Sequence[float],
                    half_life_seconds: float) -> float:
    """Sum of decay weights: the recency-weighted sample size."""
    _check_half_life(half_life_seconds)
    return sum(decay_weight(age, half_life_seconds)
               for age in ages_seconds)


def decayed_mean(values: Sequence[float], ages_seconds: Sequence[float],
                 half_life_seconds: float) -> float:
    """Recency-weighted mean of ``values``.

    Raises ``ValueError`` on empty input or mismatched lengths.
    """
    if len(values) != len(ages_seconds):
        raise ValueError(
            f"values and ages must align: {len(values)} != "
            f"{len(ages_seconds)}")
    if not values:
        raise ValueError("decayed_mean needs at least one value")
    _check_half_life(half_life_seconds)
    weights = [decay_weight(age, half_life_seconds)
               for age in ages_seconds]
    total = sum(weights)
    if total == 0.0:  # unreachable for finite ages, but be explicit
        raise ValueError("decay weights summed to zero")
    return sum(v * w for v, w in zip(values, weights, strict=True)) / total
