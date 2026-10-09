"""Local model packs. Slices 166-168.

A *pack* is a curated, known-good model choice for one fabric job:

- slice 166 — NLI packs: zero-shot entailment models;
- slice 167 — embedding packs: sentence embedding models;
- slice 168 — classifier packs: text-classification models.

Each :class:`ModelPack` records the Hugging Face id, the runtime and
pipeline task that serve it, languages, license, and an honest size
estimate. :func:`runtime_for_pack` builds the serving
:class:`LocalRuntime` (no download happens until first inference —
and a missing ``transformers`` install surfaces as
:class:`BackendUnavailable`, never an import error).

These are *recommendations*, not downloads: the fabric never fetches
weights on its own. Pair with the metadata scanner (161) to confirm
what is actually on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import SpecError
from hugrgate.runtimes import LocalRuntime, ModelRef
from hugrgate.runtimes.transformers_rt import TransformersRuntime

__all__ = [
    "CLASSIFIER_PACKS",
    "EMBEDDING_PACKS",
    "NLI_PACKS",
    "ModelPack",
    "default_pack",
    "describe_packs",
    "find_packs",
    "get_pack",
    "packs_for",
    "runtime_for_pack",
]

#: Pack kinds.
KIND_NLI = "nli"
KIND_EMBEDDING = "embedding"
KIND_CLASSIFIER = "classifier"


@dataclass(frozen=True)
class ModelPack:
    """One curated model choice for a fabric job."""

    kind: str
    name: str
    hf_id: str
    runtime: str = "transformers"
    task: str = ""
    dims: int = 0
    languages: tuple[str, ...] = ()
    license: str = ""
    size_mb: float = 0.0
    description: str = ""
    default: bool = False
    labels: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if self.kind not in (KIND_NLI, KIND_EMBEDDING, KIND_CLASSIFIER):
            raise SpecError(f"unknown pack kind {self.kind!r}")

    def to_model_ref(self) -> ModelRef:
        return ModelRef(runtime=self.runtime, path=self.hf_id,
                        format="hf", alias=self.name)


NLI_PACKS: tuple[ModelPack, ...] = (
    ModelPack(
        kind=KIND_NLI, name="bart-large-mnli",
        hf_id="facebook/bart-large-mnli",
        task="zero-shot-classification",
        languages=("en",), license="mit", size_mb=1600.0,
        description="BART-large fine-tuned on MNLI; the classic "
                    "zero-shot NLI workhorse.",
        default=True),
    ModelPack(
        kind=KIND_NLI, name="deberta-v3-large-mnli",
        hf_id="MoritzLaurer/deberta-v3-large-mnli",
        task="zero-shot-classification",
        languages=("en",), license="mit", size_mb=1700.0,
        description="DeBERTa-v3-large on MNLI + friends; stronger "
                    "than BART on hard entailment."),
    ModelPack(
        kind=KIND_NLI, name="nli-deberta-v3-small",
        hf_id="cross-encoder/nli-deberta-v3-small",
        task="zero-shot-classification",
        languages=("en",), license="apache-2.0", size_mb=550.0,
        description="Small, fast NLI model for high-throughput "
                    "entailment checks."),
)

EMBEDDING_PACKS: tuple[ModelPack, ...] = (
    ModelPack(
        kind=KIND_EMBEDDING, name="all-minilm-l6-v2",
        hf_id="sentence-transformers/all-MiniLM-L6-v2",
        task="feature-extraction", dims=384,
        languages=("en",), license="apache-2.0", size_mb=90.0,
        description="MiniLM-L6-v2; the default sentence embedding — "
                    "tiny, fast, good enough for most retrieval.",
        default=True),
    ModelPack(
        kind=KIND_EMBEDDING, name="bge-small-en-v1.5",
        hf_id="BAAI/bge-small-en-v1.5",
        task="feature-extraction", dims=384,
        languages=("en",), license="mit", size_mb=130.0,
        description="BGE-small; stronger retrieval quality than "
                    "MiniLM at similar size."),
    ModelPack(
        kind=KIND_EMBEDDING, name="e5-small-v2",
        hf_id="intfloat/e5-small-v2",
        task="feature-extraction", dims=384,
        languages=("en",), license="mit", size_mb=130.0,
        description="E5-small-v2; prefix queries with 'query: ' and "
                    "passages with 'passage: ' for best results.",
        extra={"query_prefix": "query: ",
               "passage_prefix": "passage: "}),
    ModelPack(
        kind=KIND_EMBEDDING, name="nomic-embed-text-v1.5",
        hf_id="nomic-ai/nomic-embed-text-v1.5",
        task="feature-extraction", dims=768,
        languages=("en",), license="apache-2.0", size_mb=550.0,
        description="Nomic 8192-context embeddings; long-document "
                    "retrieval."),
)

CLASSIFIER_PACKS: tuple[ModelPack, ...] = (
    ModelPack(
        kind=KIND_CLASSIFIER, name="twitter-roberta-sentiment",
        hf_id="cardiffnlp/twitter-roberta-base-sentiment-latest",
        task="text-classification",
        languages=("en",), license="cc-by-4.0", size_mb=500.0,
        description="RoBERTa sentiment (positive/neutral/negative) "
                    "trained on tweets; robust to informal text.",
        labels=("positive", "neutral", "negative"),
        default=True),
    ModelPack(
        kind=KIND_CLASSIFIER, name="go-emotions",
        hf_id="SamLowe/roberta-base-go_emotions",
        task="text-classification",
        languages=("en",), license="apache-2.0", size_mb=500.0,
        description="RoBERTa on GoEmotions; 27 fine-grained emotion "
                    "labels + neutral.",
        labels=("admiration", "amusement", "anger", "annoyance",
                "approval", "caring", "confusion", "curiosity",
                "desire", "disappointment", "disapproval", "disgust",
                "embarrassment", "excitement", "fear", "gratitude",
                "grief", "joy", "love", "nervousness", "optimism",
                "pride", "realization", "relief", "remorse",
                "sadness", "surprise", "neutral")),
)

_PACKS: dict[str, tuple[ModelPack, ...]] = {
    KIND_NLI: NLI_PACKS,
    KIND_EMBEDDING: EMBEDDING_PACKS,
    KIND_CLASSIFIER: CLASSIFIER_PACKS,
}


def packs_for(kind: str) -> tuple[ModelPack, ...]:
    """All packs of one kind (``"nli"``/``"embedding"``/``"classifier"``)."""
    if kind not in _PACKS:
        raise SpecError(
            f"unknown pack kind {kind!r}; choose from "
            f"{sorted(_PACKS)}")
    return _PACKS[kind]


def get_pack(kind: str, name: str) -> ModelPack:
    """Fetch one pack by kind + name; :class:`SpecError` when unknown."""
    for pack in packs_for(kind):
        if pack.name == name:
            return pack
    known = sorted(p.name for p in packs_for(kind))
    raise SpecError(
        f"unknown {kind} pack {name!r}; known: {known}")


def default_pack(kind: str) -> ModelPack:
    """The default pack for a kind (exactly one is flagged default)."""
    defaults = [p for p in packs_for(kind) if p.default]
    if len(defaults) != 1:
        raise SpecError(
            f"expected exactly one default {kind} pack, found "
            f"{len(defaults)}")
    return defaults[0]


def find_packs(query: str,
               kind: str | None = None) -> list[ModelPack]:
    """Case-insensitive substring search over names, ids, descriptions."""
    query = query.lower()
    kinds = [kind] if kind else list(_PACKS)
    hits = []
    for kind_name in kinds:
        for pack in packs_for(kind_name):
            haystack = f"{pack.name} {pack.hf_id} {pack.description}"
            if query in haystack.lower():
                hits.append(pack)
    return hits


def runtime_for_pack(pack: ModelPack | str,
                     kind: str | None = None,
                     **kwargs: Any) -> LocalRuntime:
    """Build the serving runtime for a pack (no download yet).

    ``pack`` may be a :class:`ModelPack` or a pack name (then ``kind``
    is required unless the name is unambiguous... it isn't — pass
    ``kind``).
    """
    if isinstance(pack, str):
        if kind is None:
            raise SpecError(
                "kind is required when selecting a pack by name")
        pack = get_pack(kind, pack)
    if pack.runtime != "transformers":
        raise SpecError(
            f"pack {pack.name!r} wants runtime {pack.runtime!r}; "
            f"this builder only constructs transformers runtimes")
    return TransformersRuntime(model=pack.to_model_ref(), task=pack.task,
                               **kwargs)


def describe_packs(kind: str | None = None) -> str:
    """Human-readable table of packs (for docs/CLI)."""
    kinds = [kind] if kind else sorted(_PACKS)
    lines = []
    for kind_name in kinds:
        lines.append(f"## {kind_name} packs")
        for pack in packs_for(kind_name):
            star = " [default]" if pack.default else ""
            lines.append(f"- **{pack.name}**{star} (`{pack.hf_id}`)")
            lines.append(f"  {pack.description}")
            details = []
            if pack.dims:
                details.append(f"{pack.dims}d")
            if pack.languages:
                details.append("/".join(pack.languages))
            if pack.license:
                details.append(pack.license)
            if pack.size_mb:
                details.append(f"~{pack.size_mb:.0f} MB")
            if pack.labels:
                details.append(f"{len(pack.labels)} labels")
            lines.append(f"  {' · '.join(details)}")
    return "\n".join(lines)
