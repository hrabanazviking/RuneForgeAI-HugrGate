"""Embedding backend — prototype classifier. Slice 33.

:class:`Embedder` turns texts into vectors. :class:`PrototypeBackend` is a
nearest-prototype classifier: each class prototype is the mean embedding of
its labeled examples, and a new text is classified by cosine similarity to
the prototypes passed through a temperature-scaled softmax.

Ships with :class:`HashEmbedder`, a tiny deterministic char-n-gram hashing
embedder. No model download, no network, works fully offline — the ladder's
"good enough" rung between classical ML and heavy neural models.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]

from hugrgate.backend import Backend
from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def _require_numpy() -> None:
    """Deliberate error when the optional numpy dependency is absent."""
    if np is None:  # pragma: no cover - optional dependency
        raise BackendError(
            "the embedding backend requires numpy; install the 'ml' extra: "
            "pip install 'hugrgate[ml]'"
        )


__all__ = [
    "TEXT_FIELDS",
    "Embedder",
    "HashEmbedder",
    "PrototypeBackend",
]

#: State keys inspected (in order) for the text to classify.
TEXT_FIELDS = ("text", "message", "content", "statement", "premise", "input")


class Embedder(ABC):
    """Turns a batch of texts into a row-normalized embedding matrix."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """Embedding dimensionality."""

    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return an ``(len(texts), dim)`` float array, rows L2-normalized."""


class HashEmbedder(Embedder):
    """Deterministic char-n-gram hashing embedder (offline, no downloads).

    Each character n-gram (n in ``ngram_range``) is hashed with SHA-1 into
    one of ``dim`` buckets with a hashed sign, exactly like the classic
    hashing trick. Rows are L2-normalized so cosine similarity is a dot
    product. Deterministic across processes and machines.
    """

    def __init__(self, dim: int = 256,
                 ngram_range: Tuple[int, int] = (3, 5)):
        if dim < 8:
            raise SpecError(f"dim must be >= 8, got {dim}")
        lo, hi = ngram_range
        if not (1 <= lo <= hi):
            raise SpecError(f"bad ngram_range: {ngram_range}")
        self._dim = dim
        self.ngram_range = (lo, hi)
        self._ws = re.compile(r"\s+")

    @property
    def dim(self) -> int:
        return self._dim

    def _ngrams(self, text: str) -> Iterable[str]:
        text = self._ws.sub(" ", text.lower().strip())
        text = f" {text} "  # boundary markers catch affixes
        lo, hi = self.ngram_range
        for n in range(lo, hi + 1):
            for i in range(len(text) - n + 1):
                yield text[i:i + n]

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        _require_numpy()
        mat = np.zeros((len(texts), self._dim), dtype=np.float64)
        for r, text in enumerate(texts):
            vec = mat[r]
            for gram in self._ngrams(text or ""):
                digest = hashlib.sha1(gram.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "big") % self._dim
                sign = 1.0 if (digest[4] & 1) else -1.0
                vec[idx] += sign
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec /= norm
        return mat


def _softmax(scores: np.ndarray, temperature: float) -> np.ndarray:
    _require_numpy()
    if temperature <= 0:
        raise SpecError(f"temperature must be > 0, got {temperature}")
    z = scores / temperature
    z = z - z.max()
    exp = np.exp(z)
    return exp / exp.sum()


class PrototypeBackend(Backend):
    """Nearest-prototype classifier over an :class:`Embedder`.

    Fit on ``(text, label)`` pairs; each class prototype is the mean of its
    examples' embeddings (re-normalized). At decision time the input text's
    cosine similarities to the prototypes become a softmax distribution.

    Supports ``categorical`` and ``binary`` specs. For binary specs the
    prototype labels must be the spec's ``"true"``/``"false"`` values.
    """

    name = "prototype-embedder"

    def __init__(self, embedder: Optional[Embedder] = None,
                 temperature: float = 0.25,
                 text_fields: Sequence[str] = TEXT_FIELDS):
        _require_numpy()
        self.embedder = embedder or HashEmbedder()
        if temperature <= 0:
            raise SpecError(f"temperature must be > 0, got {temperature}")
        self.temperature = temperature
        self.text_fields = tuple(text_fields)
        self._prototypes: Dict[str, np.ndarray] = {}
        self._classes: List[str] = []
        self._n_examples = 0

    # -- training ------------------------------------------------------

    def fit(self, examples: Iterable[Tuple[str, str]]) -> "PrototypeBackend":
        """Build class prototypes from ``(text, label)`` pairs."""
        _require_numpy()
        by_class: Dict[str, List[str]] = {}
        for text, label in examples:
            if not isinstance(text, str) or not text.strip():
                raise SpecError("prototype examples need non-empty text")
            if not isinstance(label, str) or not label:
                raise SpecError("prototype examples need non-empty labels")
            by_class.setdefault(label, []).append(text)
        if len(by_class) < 2:
            raise SpecError("prototype backend needs ≥2 classes to fit")
        texts = [t for label in by_class for t in by_class[label]]
        mat = self.embedder.embed(texts)
        self._prototypes = {}
        offset = 0
        for label, bucket in by_class.items():
            block = mat[offset:offset + len(bucket)]
            mean = block.mean(axis=0)
            norm = float(np.linalg.norm(mean))
            self._prototypes[label] = mean / norm if norm > 0 else mean
            offset += len(bucket)
        self._classes = sorted(by_class)
        self._n_examples = len(texts)
        return self

    @property
    def fitted(self) -> bool:
        return bool(self._prototypes)

    @property
    def classes(self) -> List[str]:
        return list(self._classes)

    # -- Backend contract ----------------------------------------------

    def capabilities(self) -> Dict:
        return {
            "spec_types": ["categorical", "binary"],
            "embedder": self.embedder.name,
            "dim": self.embedder.dim,
            "fitted": self.fitted,
            "classes": self.classes,
            "n_examples": self._n_examples,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type in ("categorical", "binary")

    def _extract_text(self, state: Mapping) -> str:
        for key in self.text_fields:
            value = state.get(key)
            if isinstance(value, str) and value.strip():
                return value
        # Fall back to the whole state rendered as text.
        return " ".join(str(v) for v in state.values())

    def _class_order(self, spec: DecisionSpec) -> List[str]:
        if spec.type == "categorical":
            order = list(spec.options)
        else:
            order = ["true", "false"]
        missing = [c for c in order if c not in self._prototypes]
        if missing:
            raise BackendUnavailable(
                f"prototype backend has no examples for class(es): {missing}",
                missing_classes=missing)
        return order

    def evaluate(self, state: Mapping, spec: DecisionSpec,
                 context: Optional[Mapping] = None) -> DecisionResult:
        _require_numpy()
        if not self.fitted:
            raise BackendUnavailable(
                "prototype backend is not trained — call fit(examples) first")
        order = self._class_order(spec)
        text = self._extract_text(state)
        vec = self.embedder.embed([text])[0]
        protos = np.stack([self._prototypes[c] for c in order])
        sims = protos @ vec  # cosine: rows are unit length
        probs = _softmax(sims, self.temperature)
        best = int(np.argmax(probs))
        distribution = {c: float(p) for c, p in zip(order, probs)}
        return DecisionResult(
            value=order[best],
            probability=float(probs[best]),
            distribution=distribution,
            uncertainty=float(1.0 - probs[best]),
            backend=self.name,
            model=f"{self.embedder.name}-prototypes-v1",
            metadata={
                "cosine_similarities": {c: round(float(s), 4)
                                        for c, s in zip(order, sims)},
                "temperature": self.temperature,
                "n_examples": self._n_examples,
            })

    def health(self) -> Dict:
        return {"status": "ok" if self.fitted else "untrained",
                "backend": self.name}

    def estimated_latency(self) -> float:
        return 15.0  # ms: hashing embedder, no model

    def calibration_info(self) -> Dict:
        return {"calibrated": False,
                "note": "softmax over cosine similarities is not calibrated"}
