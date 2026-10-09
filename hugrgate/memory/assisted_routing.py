"""Memory-assisted routing. Slice 321.

Route by track record: given candidate backends and the current
decision's features, :func:`advise_route` compares the backends'
historical success on similar past decisions (via
:func:`~hugrgate.memory.counterfactuals.counterfactual_backends`)
and recommends the best one — or abstains.

Abstention is a first-class outcome: when no candidate has
``min_n`` similar labeled decisions, the advice says so explicitly
(``chosen=None``, ``sufficient_data=False``) instead of crowning a
champion on noise. The caller — not this module — decides what
insufficient history means (fall back, ask, abstain); memory advises,
it does not command.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hugrgate.memory.counterfactuals import (
    BackendCounterfactual,
    counterfactual_backends,
)
from hugrgate.memory.types import HistoryLike

__all__ = [
    "RoutingAdvice",
    "advise_route",
]


@dataclass(frozen=True)
class RoutingAdvice:
    """Memory's routing recommendation for one decision."""

    chosen: str | None
    candidates: tuple[str, ...]
    estimates: tuple[BackendCounterfactual, ...] = ()
    sufficient_data: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen": self.chosen,
            "candidates": list(self.candidates),
            "estimates": [e.to_dict() for e in self.estimates],
            "sufficient_data": self.sufficient_data,
            "reason": self.reason,
        }


def advise_route(history: HistoryLike, query_features: dict[str, float],
                 candidates: list[str] | tuple[str, ...], *,
                 min_similarity: float = 0.5,
                 min_n: int = 5,
                 max_candidates: int = 2000) -> RoutingAdvice:
    """Recommend a backend from historical success on similar decisions.

    The winner is the candidate with the highest success rate among
    those with sufficient data; ties break toward more samples, then
    the tighter Wilson interval (higher lower-bound).
    """
    candidates = tuple(dict.fromkeys(candidates))  # dedupe, keep order
    if not candidates:
        raise ValueError("advise_route needs at least one candidate")
    estimates = counterfactual_backends(
        history, query_features, min_similarity=min_similarity,
        min_n=min_n, max_candidates=max_candidates)
    by_backend = {e.backend: e for e in estimates}
    eligible = [by_backend[c] for c in candidates
                if c in by_backend and by_backend[c].sufficient_data
                and by_backend[c].success_rate is not None]
    if not eligible:
        return RoutingAdvice(
            chosen=None,
            candidates=candidates,
            estimates=tuple(by_backend[c] for c in candidates
                            if c in by_backend),
            sufficient_data=False,
            reason=("no candidate has enough similar labeled history "
                    f"(min_n={min_n})"),
        )
    eligible.sort(key=lambda e: (e.success_rate or 0.0, e.n, e.wilson_lo),
                  reverse=True)
    winner = eligible[0]
    rate = winner.success_rate or 0.0
    return RoutingAdvice(
        chosen=winner.backend,
        candidates=candidates,
        estimates=tuple(by_backend[c] for c in candidates
                        if c in by_backend),
        sufficient_data=True,
        reason=(f"{winner.backend} has the best historical success rate "
                f"({rate:.2f}, n={winner.n}) on similar "
                f"decisions"),
    )
