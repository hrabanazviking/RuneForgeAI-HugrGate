"""Local Model Fabric — runtime interface v2. Slice 151.

Campaign VII unifies every local inference engine (llama.cpp, Ollama,
ONNX Runtime, Transformers, vLLM, MLX, OpenVINO, TensorRT) behind one
contract: :class:`LocalRuntime`. The older :class:`LLMEngine` interface in
``hugrgate.backends.llm`` was generate-only with a legacy signature;
this interface adds embedding, classification, model lifecycle,
structured/grammar-constrained generation, health, and metadata.

Design rules, carried over from the backend layer:

- Optional third-party engines are imported **lazily**; a module must
  import cleanly when its engine is absent. :meth:`LocalRuntime.available`
  reports whether the engine *could* run here, and every operation raises
  :class:`BackendUnavailable` (never ``ImportError``) when it cannot.
- Capabilities are advertised, never guessed: :meth:`LocalRuntime.info`
  lists the capability strings the runtime truly implements, and
  unsupported operations raise :class:`BackendError` with a clear message.
- Local runtimes are never remote: :meth:`LocalRuntime.privacy` always
  reports ``remote=False``.

:class:`FakeRuntime` is a deterministic in-process runtime used by the
conformance suite (slice 173), the benchmark matrix (slice 174), and
documentation examples. It is a real implementation of the contract —
deterministic, dependency-free, honest about being synthetic — not a stub.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.errors import BackendError, BackendUnavailable, SpecError

__all__ = [
    "CAP_CLASSIFY",
    "CAP_EMBED",
    "CAP_GENERATE",
    "CAP_GRAMMAR",
    "CAP_JSON_SCHEMA",
    "CAP_STREAM",
    "CAP_TOKENIZE",
    "KNOWN_FORMATS",
    "ClassificationResult",
    "EmbeddingResult",
    "FakeRuntime",
    "GenerationOptions",
    "GenerationResult",
    "LocalRuntime",
    "ModelRef",
    "RuntimeInfo",
    "RuntimeRegistry",
    "format_from_path",
]

# Alias: RuntimeRegistry.list() shadows the builtin inside the class
# body, so annotations there cannot spell `list[...]` directly.
_StrList = list[str]
_RuntimeList = list["LocalRuntime"]

#: Capability strings advertised by :meth:`LocalRuntime.info`.
CAP_GENERATE = "generate"
CAP_EMBED = "embed"
CAP_CLASSIFY = "classify"
CAP_GRAMMAR = "grammar"
CAP_JSON_SCHEMA = "json_schema"
CAP_STREAM = "stream"
CAP_TOKENIZE = "tokenize"

#: Model formats the fabric recognises (suffix → canonical format name).
KNOWN_FORMATS = {
    ".gguf": "gguf",
    ".onnx": "onnx",
    ".safetensors": "safetensors",
    ".bin": "pytorch-bin",
    ".pt": "pytorch",
    ".pth": "pytorch",
    ".engine": "tensorrt-engine",
    ".plan": "tensorrt-engine",
    ".xml": "openvino-ir",
    ".mlx": "mlx",
}


def format_from_path(path: str | Path) -> str:
    """Infer the canonical model format from a file suffix.

    Directories are treated as Hugging Face style repos (``"hf"``);
    unknown suffixes map to ``"unknown"`` — never guessed.
    """
    p = Path(path)
    if p.suffix == "" and not p.is_file():
        return "hf"
    return KNOWN_FORMATS.get(p.suffix.lower(), "unknown")


@dataclass(frozen=True)
class ModelRef:
    """A pointer to one loadable model artifact.

    ``runtime`` names the adapter that can load it (``"llama-cpp"``,
    ``"ollama"``, ...), ``path`` is a filesystem path, a Hugging Face
    repo id, or an Ollama model tag, and ``format`` is the canonical
    format from :data:`KNOWN_FORMATS` (``"unknown"`` is allowed but
    runtimes may refuse it).
    """

    runtime: str
    path: str
    format: str = "unknown"
    quant: str = ""
    alias: str = ""
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.runtime or not self.runtime.strip():
            raise SpecError("ModelRef needs a runtime name")
        if not self.path or not self.path.strip():
            raise SpecError("ModelRef needs a path")

    @property
    def display(self) -> str:
        base = self.alias or self.path
        return f"{base} [{self.runtime}/{self.format}]" if self.format \
            else f"{base} [{self.runtime}]"


@dataclass(frozen=True)
class GenerationOptions:
    """Knobs for one generation call."""

    max_tokens: int = 128
    temperature: float = 0.0
    top_p: float = 1.0
    stop: tuple[str, ...] = ()
    seed: int | None = None
    grammar: str | None = None
    json_schema: dict[str, Any] | None = None
    timeout_s: float = 60.0

    def __post_init__(self) -> None:
        if self.max_tokens < 1:
            raise SpecError(
                f"max_tokens must be >= 1, got {self.max_tokens}")
        if not 0.0 <= self.temperature <= 2.0:
            raise SpecError(
                f"temperature must be in [0, 2], got {self.temperature}")
        if not 0.0 < self.top_p <= 1.0:
            raise SpecError(f"top_p must be in (0, 1], got {self.top_p}")
        if self.timeout_s <= 0:
            raise SpecError(
                f"timeout_s must be > 0, got {self.timeout_s}")
        if self.grammar is not None and self.json_schema is not None:
            raise SpecError(
                "grammar and json_schema are mutually exclusive; "
                "pick one constraint")


@dataclass(frozen=True)
class GenerationResult:
    """One completed generation."""

    text: str
    finish_reason: str  # "stop" | "length" | "constrained" | "error"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0

    def __post_init__(self) -> None:
        if self.finish_reason not in ("stop", "length", "constrained",
                                      "error"):
            raise SpecError(
                f"bad finish_reason: {self.finish_reason!r}")


@dataclass(frozen=True)
class EmbeddingResult:
    """One embedding batch."""

    vectors: list[list[float]]
    dim: int
    model: str = ""

    def __post_init__(self) -> None:
        for i, vec in enumerate(self.vectors):
            if len(vec) != self.dim:
                raise SpecError(
                    f"vector {i} has dim {len(vec)}, expected {self.dim}")


@dataclass(frozen=True)
class ClassificationResult:
    """One zero-shot / classifier verdict."""

    label: str
    scores: dict[str, float]

    def __post_init__(self) -> None:
        if self.label not in self.scores:
            raise SpecError(
                f"label {self.label!r} missing from scores")
        for label, score in self.scores.items():
            if not 0.0 <= score <= 1.0:
                raise SpecError(
                    f"score for {label!r} out of range: {score}")


@dataclass(frozen=True)
class RuntimeInfo:
    """Advertised identity and capabilities of a runtime."""

    name: str
    engine: str
    engine_version: str
    available: bool
    devices: tuple[str, ...]
    formats: tuple[str, ...]
    capabilities: frozenset[str]
    model: ModelRef | None = None
    remote: bool = False
    notes: str = ""

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


class LocalRuntime(ABC):
    """v2 contract every local inference runtime implements.

    Implementations must be import-safe without their engine installed
    and thread-safe for concurrent ``generate``/``embed`` calls.
    """

    #: Machine name, e.g. ``"llama-cpp"``. Must be unique in a registry.
    name: str = "unnamed"

    # -- availability ---------------------------------------------------

    @classmethod
    @abstractmethod
    def available(cls) -> bool:
        """Whether this runtime's engine could run in this process."""

    @abstractmethod
    def info(self) -> RuntimeInfo:
        """Advertised identity, devices, formats, and capabilities."""

    # -- model lifecycle -------------------------------------------------

    def load(self, model: ModelRef) -> None:  # noqa: B027 - no-op hook
        """Load ``model`` into this runtime (idempotent)."""

    def unload(self) -> None:  # noqa: B027 - no-op hook
        """Release the loaded model, if any (idempotent)."""

    # -- inference -------------------------------------------------------

    @abstractmethod
    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        """Generate one completion for ``prompt``."""

    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed a batch of texts. Default: unsupported."""
        raise BackendError(
            f"runtime {self.name!r} does not implement 'embed'")

    def classify(self, texts: list[str], labels: list[str]
                 ) -> list[ClassificationResult]:
        """Zero-shot classify each text into ``labels``.

        Default: unsupported.
        """
        raise BackendError(
            f"runtime {self.name!r} does not implement 'classify'")

    def tokenize(self, text: str) -> list[int]:
        """Tokenize ``text`` into token ids. Default: unsupported."""
        raise BackendError(
            f"runtime {self.name!r} does not implement 'tokenize'")

    # -- operations ------------------------------------------------------

    def warmup(self) -> None:  # noqa: B027 - no-op hook
        """Optional: run a cheap inference to warm caches. No-op default."""

    def health(self) -> dict[str, Any]:
        """Liveness report. ``status`` is ok/degraded/unavailable."""
        try:
            available = self.available()
        except Exception:  # noqa: BLE001 - health must never raise
            available = False
        return {
            "status": "ok" if available else "unavailable",
            "runtime": self.name,
            "available": available,
        }

    def privacy(self) -> dict[str, Any]:
        """Local runtimes never send data off-machine."""
        return {"remote": False, "data_retained": False,
                "runtime": self.name}

    def close(self) -> None:  # noqa: B027 - no-op hook
        """Release engine resources (idempotent). No-op default."""

    # -- helpers ----------------------------------------------------------

    def _require_capability(self, capability: str) -> None:
        if not self.info().supports(capability):
            raise BackendError(
                f"runtime {self.name!r} does not advertise "
                f"capability {capability!r}")

    @staticmethod
    def _check_prompt(prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise SpecError("prompt must be a non-empty string")
        return prompt

    @staticmethod
    def _check_texts(texts: list[str], what: str = "texts") -> list[str]:
        if not texts:
            raise SpecError(f"{what} must be a non-empty list")
        for text in texts:
            if not isinstance(text, str):
                raise SpecError(f"{what} must contain only strings")
        return texts


class RuntimeRegistry:
    """Name-keyed registry of :class:`LocalRuntime` instances.

    Mirrors :class:`BackendRegistry` semantics: unique names,
    re-registration requires ``replace=True``, thread-safe.
    """

    def __init__(self) -> None:
        self._runtimes: dict[str, LocalRuntime] = {}
        self._lock = threading.RLock()

    def register(self, runtime: LocalRuntime, *,
                 replace: bool = False) -> None:
        if not isinstance(runtime, LocalRuntime):
            raise TypeError(
                "can only register LocalRuntime instances, got "
                f"{type(runtime).__name__}")
        name = runtime.name
        if not isinstance(name, str) or not name.strip():
            raise SpecError(
                f"runtime name must be a non-empty string, got {name!r}")
        with self._lock:
            if name in self._runtimes and not replace:
                raise SpecError(
                    f"runtime {name!r} is already registered; "
                    f"pass replace=True to overwrite it")
            self._runtimes[name] = runtime

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._runtimes.pop(name, None) is not None

    def get(self, name: str) -> LocalRuntime | None:
        with self._lock:
            return self._runtimes.get(name)

    def get_or_raise(self, name: str) -> LocalRuntime:
        with self._lock:
            runtime = self._runtimes.get(name)
        if runtime is None:
            raise BackendUnavailable(f"unknown runtime: {name}")
        return runtime

    def list(self) -> _StrList:
        with self._lock:
            return list(self._runtimes.keys())

    def available_runtimes(self) -> _RuntimeList:
        """Runtimes whose engine could run in this process."""
        with self._lock:
            runtimes = list(self._runtimes.values())
        return [r for r in runtimes if r.available()]

    def supporting(self, capability: str) -> _RuntimeList:
        with self._lock:
            runtimes = list(self._runtimes.values())
        return [r for r in runtimes if r.info().supports(capability)]

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return name in self._runtimes

    def __len__(self) -> int:
        with self._lock:
            return len(self._runtimes)


class FakeRuntime(LocalRuntime):
    """Deterministic in-process runtime for tests, conformance, and docs.

    Generation echoes a stable, prompt-derived completion; embeddings are
    SHA-256 n-gram hashes (deterministic across processes); zero-shot
    classification scores labels by token overlap with the text. No third
    party, no network, no randomness — a synthetic engine that is honest
    about being one (``notes`` says so).
    """

    name = "fake"

    def __init__(self, dim: int = 64, latency_s: float = 0.0,
                 supports: frozenset[str] | None = None) -> None:
        if dim < 8:
            raise SpecError(f"dim must be >= 8, got {dim}")
        self._dim = dim
        self._latency_s = latency_s
        self._caps = frozenset({
            CAP_GENERATE, CAP_EMBED, CAP_CLASSIFY, CAP_TOKENIZE,
        } if supports is None else supports)
        self._model: ModelRef | None = None
        self._lock = threading.RLock()
        self.generate_calls = 0
        self.embed_calls = 0

    @classmethod
    def available(cls) -> bool:
        return True

    def info(self) -> RuntimeInfo:
        return RuntimeInfo(
            name=self.name,
            engine="fake",
            engine_version="0.0.0",
            available=True,
            devices=("cpu",),
            formats=("unknown",),
            capabilities=self._caps,
            model=self._model,
            remote=False,
            notes="deterministic synthetic engine for tests/conformance",
        )

    def load(self, model: ModelRef) -> None:
        with self._lock:
            self._model = model

    def unload(self) -> None:
        with self._lock:
            self._model = None

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._require_capability(CAP_GENERATE)
        prompt = self._check_prompt(prompt)
        opts = options or GenerationOptions()
        started = time.monotonic()
        if self._latency_s:
            time.sleep(self._latency_s)
        with self._lock:
            self.generate_calls += 1
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        words = prompt.split()
        completion = " ".join(
            f"tok-{digest[i:i + 6]}" for i in range(0, 24, 6))
        if opts.temperature == 0.0 and words:
            completion = f"echo: {' '.join(words[:opts.max_tokens])}"
        for stop in opts.stop:
            if stop and stop in completion:
                completion = completion.split(stop)[0]
        text = completion[: opts.max_tokens * 8]
        if opts.json_schema is not None:
            text = '{"ok": true}'
            finish = "constrained"
        elif opts.grammar is not None:
            finish = "constrained"
        else:
            finish = "stop"
        return GenerationResult(
            text=text,
            finish_reason=finish,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            latency_s=time.monotonic() - started,
        )

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self._require_capability(CAP_EMBED)
        texts = self._check_texts(texts)
        with self._lock:
            self.embed_calls += 1
        vectors = [self._hash_embed(t) for t in texts]
        return EmbeddingResult(vectors=vectors, dim=self._dim,
                               model=self._model.path if self._model
                               else "fake")

    def _hash_embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        grams = [text[i:i + 3] for i in range(max(1, len(text) - 2))]
        for gram in grams or [""]:
            digest = hashlib.sha256(gram.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self._dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def classify(self, texts: list[str], labels: list[str]
                 ) -> list[ClassificationResult]:
        self._require_capability(CAP_CLASSIFY)
        texts = self._check_texts(texts)
        labels = self._check_texts(labels, "labels")
        results = []
        for text in texts:
            tokens = set(text.lower().split())
            raw = {label: 1.0 + sum(
                1 for tok in label.lower().split() if tok in tokens)
                for label in labels}
            total = sum(raw.values())
            scores = {label: value / total for label, value in raw.items()}
            best = max(scores, key=lambda k: scores[k])
            results.append(ClassificationResult(label=best, scores=scores))
        return results

    def tokenize(self, text: str) -> list[int]:
        self._require_capability(CAP_TOKENIZE)
        self._check_prompt(text)
        return [int.from_bytes(
            hashlib.sha256(w.encode()).digest()[:4], "big") % 32000
            for w in text.split()]

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "runtime": self.name, "available": True,
                "model": self._model.display if self._model else None}
