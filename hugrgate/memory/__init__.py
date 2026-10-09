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

from hugrgate.memory.access import (
    GuardedHistory,
    MemoryAccessPolicy,
    RolePermission,
)
from hugrgate.memory.adversarial import AdversarialReport, Finding, scan
from hugrgate.memory.assisted_calibration import (
    CalibrationMap,
    CalibrationValidation,
    assess_calibration,
    brier_score,
    calibrate_from_memory,
    expected_calibration_error,
)
from hugrgate.memory.assisted_routing import RoutingAdvice, advise_route
from hugrgate.memory.backend_history import BackendHistory, backend_histories
from hugrgate.memory.compaction import CompactionSummary, compact
from hugrgate.memory.conditioned import retrieve_conditioned
from hugrgate.memory.contract_history import (
    ContractHistory,
    contract_histories,
    contract_key_for,
)
from hugrgate.memory.counterfactuals import (
    BackendCounterfactual,
    ValueCounterfactual,
    counterfactual_backends,
    counterfactual_value,
    wilson_interval,
)
from hugrgate.memory.decay import (
    decay_weight,
    decayed_mean,
    effective_count,
    half_life_for_horizon,
)
from hugrgate.memory.domain_profiles import (
    DEFAULT_DOMAIN,
    DomainProfile,
    domain_for,
    domain_profiles,
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
from hugrgate.memory.io import ExportReport, ImportReport, export_jsonl, import_jsonl
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
from hugrgate.memory.replay import ReplayReport, ReplayResult, replay
from hugrgate.memory.retention import (
    MemoryQuota,
    QuotaStatus,
    RetentionReport,
    check_quota,
    enforce_quotas,
)
from hugrgate.memory.retrieval import RetrievalResult, recall, retrieve
from hugrgate.memory.similarity import (
    SimilarityHit,
    cosine,
    featurize_episode,
    featurize_query,
    most_similar,
)

__all__ = [
    "DEFAULT_DOMAIN",
    "OUTCOME_KINDS",
    "ROLE_PERMISSIONS",
    "AdversarialReport",
    "BackendCounterfactual",
    "BackendHistory",
    "CalibrationMap",
    "CalibrationValidation",
    "CompactionSummary",
    "ContractHistory",
    "DecisionHistory",
    "DomainProfile",
    "Episode",
    "ExportReport",
    "Finding",
    "FrequencyEntry",
    "FrequencyTable",
    "GroundTruth",
    "GuardedHistory",
    "ImportReport",
    "MemoryAccessPolicy",
    "MemoryAction",
    "MemoryDecision",
    "MemoryPolicy",
    "MemoryQuery",
    "MemoryQuota",
    "MemoryRule",
    "Outcome",
    "QuotaStatus",
    "RecencyFeatures",
    "ReplayReport",
    "ReplayResult",
    "RetentionReport",
    "RetrievalResult",
    "RolePermission",
    "RoutingAdvice",
    "SimilarityHit",
    "ValueCounterfactual",
    "advise_route",
    "assess_calibration",
    "backend_histories",
    "brier_score",
    "by_backend",
    "by_backend_value",
    "by_model",
    "by_outcome_kind",
    "calibrate_from_memory",
    "check_quota",
    "compact",
    "contract_histories",
    "contract_key_for",
    "cosine",
    "count_by",
    "counterfactual_backends",
    "counterfactual_value",
    "decay_weight",
    "decayed_mean",
    "domain_for",
    "domain_profiles",
    "drop_backend",
    "drop_forbidden",
    "drop_unaccepted",
    "effective_count",
    "enforce_quotas",
    "expected_calibration_error",
    "export_jsonl",
    "featurize_episode",
    "featurize_query",
    "find_in_provenance",
    "half_life_for_horizon",
    "import_jsonl",
    "most_similar",
    "outcome_agrees",
    "recall",
    "recency_features",
    "record_only_backend",
    "redact_above",
    "replay",
    "retrieve",
    "retrieve_conditioned",
    "scan",
    "wilson_interval",
]
