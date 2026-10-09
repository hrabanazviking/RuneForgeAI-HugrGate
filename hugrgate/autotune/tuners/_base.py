"""Shared tuner machinery. Slice 454.

Every Campaign XIX tuner is a small deterministic optimizer over one
piece of HugrGate configuration. This module holds what they share:

- :class:`BaseTuner`: the :class:`Tuner` protocol plus seeded RNG,
  proposal construction, and a ``min_delta`` significance gate (no
  proposal for noise-level wins);
- :func:`seeded_rng`: deterministic ``random.Random`` from an int seed;
- :func:`kfold_indices`: stratified k-fold splits for honest
  held-out evaluation;
- :func:`linspace`: candidate grids without numpy.
"""

from __future__ import annotations

import random
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.errors import TunerError

__all__ = [
    "BaseTuner",
    "kfold_indices",
    "linspace",
    "seeded_rng",
]


def seeded_rng(seed: int) -> random.Random:
    return random.Random(seed)


def linspace(lo: float, hi: float, n: int) -> list[float]:
    if n < 1:
        raise TunerError("grid size must be >= 1", grid=n)
    if n == 1:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]


def kfold_indices(n: int, labels: Sequence[int], n_folds: int,
                  seed: int) -> list[tuple[list[int], list[int]]]:
    """Stratified k-fold (train_idx, test_idx) splits, seeded."""
    if n_folds < 2:
        raise TunerError("n_folds must be >= 2", n_folds=n_folds)
    if n != len(labels):
        raise TunerError("labels length mismatch", n=n,
                         labels=len(labels))
    if n < n_folds:
        raise TunerError("fewer samples than folds", n=n, n_folds=n_folds)
    rng = seeded_rng(seed)
    by_label: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        by_label.setdefault(lab, []).append(i)
    for idxs in by_label.values():
        rng.shuffle(idxs)
    folds: list[list[int]] = [[] for _ in range(n_folds)]
    for _lab, idxs in sorted(by_label.items()):
        for k, i in enumerate(idxs):
            folds[k % n_folds].append(i)
    out = []
    for k in range(n_folds):
        test = folds[k]
        train = [i for j, f in enumerate(folds) if j != k for i in f]
        out.append((train, test))
    return out


@dataclass
class BaseTuner:
    """Common tuner behavior: seeding, proposal building, min-delta gate."""

    name: str = "base_tuner"
    param: str = ""
    objective_id: str = ""
    seed: int = 0
    min_delta: float = 0.005

    def _rng(self, ctx: TuningContext) -> random.Random:
        return seeded_rng((self.seed * 1_000_003 + ctx.seed) & 0x7FFFFFFF)

    def _propose(self, ctx: TuningContext, changes: dict[str, Any],
                 baseline: float, estimate: float,
                 evidence: dict[str, Any] | None = None) -> Proposal | None:
        """Build a proposal, or None when the win is below min_delta."""
        if estimate - baseline < self.min_delta:
            return None
        return Proposal(
            proposal_id=f"prop-{uuid.uuid4().hex[:10]}",
            tuner=self.name,
            changes=dict(changes),
            objective_id=self.objective_id,
            baseline=baseline,
            estimate=estimate,
            seed=ctx.seed,
            created_at=time.time(),
            evidence=dict(evidence or {}),
        )

    def tune(self, ctx: TuningContext) -> Proposal | None:
        raise NotImplementedError
