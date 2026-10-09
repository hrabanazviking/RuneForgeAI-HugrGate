"""Historical similarity search. Slice 305.

"Have we seen a decision like this before?" :func:`featurize_episode`
turns an episode into a sparse feature vector over the decision's
stable attributes (spec shape, backend, model, probability bucket,
acceptance, fallback use, latency band, state keys, domain); cosine
similarity over those vectors powers :func:`most_similar`.

Deliberate limits (Yrsa Execution Law, rule 14):

- Features are symbolic and auditable — no opaque embeddings, no
  third-party vector store. Every hit reports its ``shared_features``
  so a human can see *why* two decisions matched.
- Vectors are sparse dicts; similarity is exact, deterministic, and
  dependency-free.
- Ties break by recency, so repeated queries are stable.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.memory.types import EpisodeLike

__all__ = [
    "SimilarityHit",
    "cosine",
    "featurize_episode",
    "featurize_query",
    "most_similar",
]

#: Cap on state-key features per episode (bounds vector size).
_MAX_STATE_KEYS = 32


def _value_space_size(spec: dict[str, Any]) -> int:
    kind = spec.get("type")
    if kind == "categorical":
        return len(spec.get("options") or [])
    if kind == "binary":
        return 2
    if kind == "ordinal":
        return len(spec.get("levels") or [])
    if kind == "multilabel":
        return len(spec.get("labels") or [])
    if kind == "numeric":
        return 2  # a range, not a set of discrete options
    return 0


def featurize_query(*, spec: dict[str, Any] | None = None,
                    backend: str | None = None,
                    model: str | None = None,
                    probability: float | None = None,
                    accepted: bool | None = None,
                    fallback_used: bool | None = None,
                    latency_ms: float | None = None,
                    state_keys: list[str] | tuple[str, ...] | None = None,
                    domain: str | None = None) -> dict[str, float]:
    """Build a sparse feature vector from raw decision attributes."""
    features: dict[str, float] = {}
    if spec is not None:
        kind = spec.get("type")
        if isinstance(kind, str):
            features[f"spec:type={kind}"] = 1.0
        size = _value_space_size(spec)
        features["spec:value_space"] = min(size, 32) / 32.0
        meta = spec.get("metadata") or {}
        spec_domain = meta.get("domain") if isinstance(meta, dict) else None
        if isinstance(spec_domain, str) and spec_domain:
            features[f"domain={spec_domain}"] = 1.0
    if domain:
        features[f"domain={domain}"] = 1.0
    if backend:
        features[f"backend={backend}"] = 1.0
    if model:
        features[f"model={model}"] = 1.0
    if probability is not None:
        bucket = min(int(probability * 10), 9)
        features[f"prob_bucket={bucket}"] = 1.0
        features["probability"] = max(0.0, min(1.0, probability))
    if accepted:
        features["accepted"] = 1.0
    if fallback_used:
        features["fallback_used"] = 1.0
    if latency_ms is not None and latency_ms >= 0:
        features["latency"] = min(math.log10(1.0 + latency_ms) / 4.0, 1.0)
    if state_keys:
        for key in list(state_keys)[:_MAX_STATE_KEYS]:
            features[f"state_key={key}"] = 1.0
    return features


def featurize_episode(episode: EpisodeLike) -> dict[str, float]:
    """Feature vector for a stored episode (see :func:`featurize_query`)."""
    record = episode.record
    metadata = record.metadata or {}
    state_keys = metadata.get("state_keys")
    domain = metadata.get("domain")
    if not isinstance(domain, str):
        domain = None
    return featurize_query(
        spec=record.spec,
        backend=record.backend,
        model=record.model,
        probability=record.probability,
        accepted=record.accepted,
        fallback_used=record.fallback_used,
        latency_ms=record.latency_ms,
        state_keys=state_keys if isinstance(state_keys, list) else None,
        domain=domain,
    )


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity of two sparse vectors; 0.0 if either is empty."""
    if not a or not b:
        return 0.0
    if len(b) < len(a):
        a, b = b, a
    dot = sum(value * b.get(key, 0.0) for key, value in a.items())
    if dot == 0.0:
        return 0.0
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass(frozen=True)
class SimilarityHit:
    """One similar episode: the episode, its score, and why it matched."""

    episode: EpisodeLike
    score: float
    shared_features: tuple[str, ...] = field(default_factory=tuple)


def most_similar(query_features: dict[str, float],
                 episodes: Sequence[EpisodeLike], *,
                 k: int = 5,
                 exclude_ids: set[str] | frozenset[str] = frozenset()
                 ) -> list[SimilarityHit]:
    """Top-``k`` episodes by cosine similarity to ``query_features``.

    Ties break by recency (newest first) for deterministic results.
    Episodes whose id is in ``exclude_ids`` are skipped.
    """
    if k < 0:
        raise ValueError(f"k must be >= 0, got {k}")
    if k == 0 or not query_features or not episodes:
        return []
    query_keys = set(query_features)
    scored: list[tuple[float, float, EpisodeLike, frozenset[str]]] = []
    for episode in episodes:
        if episode.episode_id in exclude_ids:
            continue
        features = featurize_episode(episode)
        score = cosine(query_features, features)
        shared = frozenset(query_keys & set(features))
        scored.append((score, episode.recorded_at, episode, shared))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        SimilarityHit(episode=episode, score=score,
                      shared_features=tuple(sorted(shared)))
        for score, _, episode, shared in scored[:k]
    ]
