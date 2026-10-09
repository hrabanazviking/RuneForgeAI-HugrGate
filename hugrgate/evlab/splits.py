"""Dataset split tooling — train/val/test, stratified, k-fold. Slice 355.

All splitting is deterministic for a fixed seed via a dedicated
``random.Random`` instance (never the global RNG, so lab runs do not
perturb each other).  :class:`SplitPlan` records exactly how a split
was produced and serializes to JSON — the reproducibility manifest
(slice 372) embeds it so a split can be re-derived bit-for-bit.
"""

from __future__ import annotations

import copy
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import DatasetError
from hugrgate.evlab.dataset import DatasetManifest, fingerprint_items

__all__ = [
    "SplitPlan",
    "kfold_indices",
    "make_splits",
    "manifest_splits",
]


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


@dataclass
class SplitPlan:
    """An auditable record of how items were split."""

    n_total: int
    splits: list[tuple[str, float]]
    seed: int
    method: str  # "shuffled" | "sequential" | "stratified"
    stratify_key: str | None = None
    created_at: str = ""
    input_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _utc_now()

    def validate(self) -> None:
        if self.n_total < 1:
            raise DatasetError("cannot split an empty item list")
        if self.method not in ("shuffled", "sequential", "stratified"):
            raise DatasetError(
                f"unknown split method {self.method!r}; expected "
                "'shuffled', 'sequential', or 'stratified'"
            )
        if not self.splits:
            raise DatasetError("split plan needs at least one split")
        names = [name for name, _ in self.splits]
        if len(set(names)) != len(names):
            raise DatasetError(f"duplicate split names: {names}")
        if any(not name for name in names):
            raise DatasetError("split names must be non-empty strings")
        total = sum(frac for _, frac in self.splits)
        if abs(total - 1.0) > 1e-9:
            raise DatasetError(
                f"split fractions must sum to 1.0, got {total}",
                fractions=[f for _, f in self.splits],
            )
        if any(frac <= 0.0 for _, frac in self.splits):
            raise DatasetError("split fractions must be positive")
        if self.method == "stratified" and not self.stratify_key:
            raise DatasetError(
                "stratified splits need a stratify_key column name"
            )
        if not isinstance(self.seed, int):
            raise DatasetError("split seed must be an int")

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_total": self.n_total,
            "splits": [[name, frac] for name, frac in self.splits],
            "seed": self.seed,
            "method": self.method,
            "stratify_key": self.stratify_key,
            "created_at": self.created_at,
            "input_fingerprint": self.input_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SplitPlan:
        return cls(
            n_total=data["n_total"],
            splits=[(name, frac) for name, frac in data["splits"]],
            seed=data["seed"],
            method=data["method"],
            stratify_key=data.get("stratify_key"),
            created_at=data.get("created_at", ""),
            input_fingerprint=data.get("input_fingerprint", ""),
        )


def _boundaries(fractions: Sequence[float], n: int) -> list[int]:
    """Cumulative cut points; every item lands in exactly one split."""
    cuts = [0]
    acc = 0.0
    for frac in fractions:
        acc += frac
        cuts.append(round(acc * n))
    cuts[-1] = n  # absorb float dust into the final split
    return cuts


def make_splits(
    items: Sequence[Mapping[str, Any]],
    splits: Sequence[tuple[str, float]] = (
        ("train", 0.7), ("validation", 0.15), ("test", 0.15)),
    seed: int = 0,
    method: str = "shuffled",
    stratify_key: str | None = None,
    key_fn: Callable[[Mapping[str, Any]], Any] | None = None,
) -> tuple[dict[str, list[Mapping[str, Any]]], SplitPlan]:
    """Split ``items`` into named subsets; return (subsets, plan).

    - ``method="shuffled"``: global shuffle under ``seed``, then cut.
    - ``method="sequential"``: cut in input order (no shuffle).
    - ``method="stratified"``: shuffle *within* each group of
      ``key_fn(item)`` (or ``item[stratify_key]``), then allocate each
      group proportionally so every split mirrors the group mix.
    """
    rows = list(items)
    plan = SplitPlan(
        n_total=len(rows),
        splits=list(splits),
        seed=seed,
        method=method,
        # A custom key_fn is recorded honestly as "key_fn".
        stratify_key=stratify_key if stratify_key is not None
        else ("key_fn" if key_fn is not None else None),
        input_fingerprint=fingerprint_items(rows),
    )
    plan.validate()
    if method == "stratified" and key_fn is None:
        # plan.validate() guarantees stratify_key is set here.
        column = stratify_key
        assert column is not None
        key_fn = lambda item: item.get(column)  # noqa: E731

    names = [name for name, _ in plan.splits]
    fracs = [frac for _, frac in plan.splits]
    rng = random.Random(seed)

    if method == "stratified":
        assert key_fn is not None
        groups: dict[Any, list[int]] = {}
        for idx, item in enumerate(rows):
            groups.setdefault(key_fn(item), []).append(idx)
        buckets: dict[str, list[int]] = {name: [] for name in names}
        for gidx in groups.values():
            rng.shuffle(gidx)
            cuts = _boundaries(fracs, len(gidx))
            for name, lo, hi in zip(names, cuts[:-1], cuts[1:], strict=True):
                buckets[name].extend(gidx[lo:hi])
        # Deterministic order within each split: sort by original index.
        result = {
            name: [rows[i] for i in sorted(idxs)]
            for name, idxs in buckets.items()
        }
    else:
        order = list(range(len(rows)))
        if method == "shuffled":
            rng.shuffle(order)
        cuts = _boundaries(fracs, len(rows))
        result = {
            name: [rows[i] for i in order[lo:hi]]
            for name, lo, hi in zip(names, cuts[:-1], cuts[1:], strict=True)
        }
    return result, plan


def kfold_indices(
    n: int, k: int, seed: int = 0, shuffle: bool = True
) -> list[tuple[list[int], list[int]]]:
    """k (train_idx, test_idx) folds; each index tests exactly once.

    Fold sizes differ by at most one.  Deterministic for fixed
    ``seed``/``shuffle``.
    """
    if n < 1:
        raise DatasetError("k-fold needs at least one item")
    if k < 2:
        raise DatasetError(f"k must be >= 2, got {k}")
    if k > n:
        raise DatasetError(f"k={k} exceeds n={n}")
    if not isinstance(seed, int):
        raise DatasetError("k-fold seed must be an int")
    order = list(range(n))
    if shuffle:
        random.Random(seed).shuffle(order)
    # Deal contiguous blocks: fold i tests order[i::k]-style slices via
    # divmod so sizes differ by at most one.
    base, rem = divmod(n, k)
    folds: list[tuple[list[int], list[int]]] = []
    start = 0
    for i in range(k):
        size = base + (1 if i < rem else 0)
        test = order[start:start + size]
        train = order[:start] + order[start + size:]
        folds.append((train, test))
        start += size
    return folds


def manifest_splits(
    manifest: DatasetManifest,
    items: Sequence[Mapping[str, Any]],
    splits: Sequence[tuple[str, float]] = (
        ("train", 0.8), ("test", 0.2)),
    seed: int = 0,
    method: str = "shuffled",
    stratify_key: str | None = None,
) -> tuple[dict[str, DatasetManifest], dict[str, list[Mapping[str, Any]]],
           SplitPlan]:
    """Split items and seal one manifest per split (slice 355).

    Each split manifest is named ``"<name>/<split>"`` and sealed
    against its own items, so downstream runs verify independently.
    The parent manifest must already verify against the full items.
    """
    rows = list(items)
    manifest.verify(rows)
    subsets, plan = make_splits(rows, splits=splits, seed=seed,
                                method=method, stratify_key=stratify_key)
    sealed: dict[str, DatasetManifest] = {}
    for name, part in subsets.items():
        child = copy.deepcopy(manifest)
        child.name = f"{manifest.name}/{name}"
        child.fingerprint = ""
        sealed[name] = child.seal(part)
    return sealed, subsets, plan
