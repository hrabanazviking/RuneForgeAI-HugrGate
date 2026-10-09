"""Decision memory — episodic recall for the HugrGate runtime.

Campaign XIII (Decision Memory) gives the runtime useful historical
context without turning it into an opaque agent. The memory layer is
built on top of :mod:`hugrgate.provenance`, not beside it:

- :class:`~hugrgate.provenance.ProvenanceStore` remains the
  tamper-evident, hash-chained legal record of *what was decided*;
- :class:`~hugrgate.memory.history.DecisionHistory` keeps *episodes* —
  snapshots of decision records annotated with observed outcomes,
  ground truth, privacy classes, and tags — so the runtime can recall,
  compare, and learn from similar past decisions.

Episodes are deep-copied on the way in and on the way out; the memory
never hands out a mutable reference to its own state. All public
behavior is typed, thread-safe, and bounded (see
:mod:`hugrgate.memory.retention`).
"""

from __future__ import annotations

from hugrgate.memory.backend_history import BackendHistory, backend_histories
from hugrgate.memory.conditioned import retrieve_conditioned
from hugrgate.memory.contract_history import (
    ContractHistory,
    contract_histories,
    contract_key_for,
)
from hugrgate.memory.decay import (
    decay_weight,
    decayed_mean,
    effective_count,
    half_life_for_horizon,
)
from hugrgate.memory.frequency import (
    FrequencyEntry,
    FrequencyTable,
    by_backend,
    by_backend_value,
    by_model,
    by_outcome_kind,
    count_by,
)
from hugrgate.memory.groundtruth import GroundTruth, outcome_agrees
from hugrgate.memory.history import DecisionHistory, Episode
from hugrgate.memory.outcomes import OUTCOME_KINDS, Outcome
from hugrgate.memory.policies import (
    MemoryAction,
    MemoryDecision,
    MemoryPolicy,
    MemoryRule,
    drop_backend,
    drop_forbidden,
    drop_unaccepted,
    record_only_backend,
    redact_above,
)
from hugrgate.memory.query import MemoryQuery, find_in_provenance
from hugrgate.memory.recency import RecencyFeatures, recency_features
from hugrgate.memory.retrieval import RetrievalResult, recall, retrieve
from hugrgate.memory.similarity import (
    SimilarityHit,
    cosine,
    featurize_episode,
    featurize_query,
    most_similar,
)

__all__ = [
    "OUTCOME_KINDS",
    "BackendHistory",
    "ContractHistory",
    "DecisionHistory",
    "Episode",
    "FrequencyEntry",
    "FrequencyTable",
    "GroundTruth",
    "MemoryAction",
    "MemoryDecision",
    "MemoryPolicy",
    "MemoryQuery",
    "MemoryRule",
    "Outcome",
    "RecencyFeatures",
    "RetrievalResult",
    "SimilarityHit",
    "backend_histories",
    "by_backend",
    "by_backend_value",
    "by_model",
    "by_outcome_kind",
    "contract_histories",
    "contract_key_for",
    "cosine",
    "count_by",
    "decay_weight",
    "decayed_mean",
    "drop_backend",
    "drop_forbidden",
    "drop_unaccepted",
    "effective_count",
    "featurize_episode",
    "featurize_query",
    "find_in_provenance",
    "half_life_for_horizon",
    "most_similar",
    "outcome_agrees",
    "recall",
    "recency_features",
    "record_only_backend",
    "redact_above",
    "retrieve",
    "retrieve_conditioned",
]
