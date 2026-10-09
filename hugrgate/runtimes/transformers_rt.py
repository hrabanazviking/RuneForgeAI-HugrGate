"""Transformers runtime adapter. Slice 155.

:class:`TransformersRuntime` serves Hugging Face ``transformers``
pipelines through the v2 :class:`LocalRuntime` contract, one pipeline
*task* per instance:

- ``"text-generation"`` → :meth:`generate` (prompt prefix is stripped
  from the pipeline output, honestly);
- ``"feature-extraction"`` → :meth:`embed` (token vectors are
  mean-pooled and L2-normalized into one vector per text);
- ``"zero-shot-classification"`` → :meth:`classify` (candidate labels
  scored per text);
- ``"text-classification"`` → :meth:`classify` (model's own labels).

``transformers`` is optional and imported lazily. Timeouts are
cooperative — a blocking pipeline call cannot be interrupted, so a
late return surfaces as :class:`TimeoutError` after the fact rather
than as a silent overrun. :meth:`as_nli_fn` adapts a zero-shot
instance to the ``(premise, statement) -> float`` callable that
``hugrgate.backends.nli.NLIBackend`` accepts, so the existing NLI
backend can run on this runtime without duplication.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Any

from hugrgate.errors import (
    BackendError,
    BackendUnavailable,
    SpecError,
    TimeoutError,
)
from hugrgate.runtimes import (
    CAP_CLASSIFY,
    CAP_EMBED,
    CAP_GENERATE,
    ClassificationResult,
    EmbeddingResult,
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
    ModelRef,
    RuntimeInfo,
)

__all__ = [
    "GENERATION_TASKS",
    "TransformersRuntime",
]

#: Tasks that implement generation.
GENERATION_TASKS = frozenset({"text-generation"})

#: Tasks that implement embedding.
EMBEDDING_TASKS = frozenset({"feature-extraction"})

#: Tasks that implement classification.
CLASSIFICATION_TASKS = frozenset(
    {"zero-shot-classification", "text-classification"})

_SUPPORTED_TASKS = (GENERATION_TASKS | EMBEDDING_TASKS
                    | CLASSIFICATION_TASKS)


def _import_pipeline() -> Any:
    try:
        from transformers import pipeline
    except Exception as e:
        raise BackendUnavailable(
            "transformers is not installed; install the 'nli' extra: "
            "pip install 'hugrgate[nli]'",
            backend="transformers") from e
    return pipeline


class TransformersRuntime(LocalRuntime):
    """Hugging Face transformers pipelines as a local runtime.

    Parameters
    ----------
    model: :class:`ModelRef` (or HF repo id / local path string).
    task: one of ``"text-generation"``, ``"feature-extraction"``,
        ``"zero-shot-classification"``, ``"text-classification"``.
    device: ``-1`` for CPU, ``>= 0`` for a CUDA device index.
    trust_remote_code: passed through to the pipeline (default False —
        safer).
    pipe_kwargs: extra kwargs forwarded to ``transformers.pipeline``.
    pipe: injected pipeline callable for tests (duck-types the task
        pipeline's ``__call__``).
    """

    name = "transformers"

    def __init__(self, model: ModelRef | str | None = None,
                 task: str = "text-generation", device: int = -1,
                 trust_remote_code: bool = False,
                 pipe_kwargs: dict[str, Any] | None = None,
                 pipe: Any = None) -> None:
        if task not in _SUPPORTED_TASKS:
            raise SpecError(
                f"unsupported task {task!r}; choose from "
                f"{sorted(_SUPPORTED_TASKS)}")
        if device < -1:
            raise SpecError(f"device must be >= -1, got {device}")
        self._model = (ModelRef(runtime=self.name, path=model,
                                format="hf")
                       if isinstance(model, str) else model)
        self.task = task
        self.device = device
        self.trust_remote_code = trust_remote_code
        self.pipe_kwargs = dict(pipe_kwargs or {})
        self._pipe = pipe
        self._lock = threading.RLock()

    # -- availability ---------------------------------------------------

    @classmethod
    def available(cls) -> bool:
        try:
            _import_pipeline()
            return True
        except BackendUnavailable:
            return False

    def _capabilities(self) -> frozenset[str]:
        caps = set()
        if self.task in GENERATION_TASKS:
            caps.add(CAP_GENERATE)
        if self.task in EMBEDDING_TASKS:
            caps.add(CAP_EMBED)
        if self.task in CLASSIFICATION_TASKS:
            caps.add(CAP_CLASSIFY)
        return frozenset(caps)

    def info(self) -> RuntimeInfo:
        try:
            ok = self._pipe is not None or self.available()
        except Exception:  # noqa: BLE001 - info must never raise
            ok = False
        devices = ("cpu",) if self.device < 0 else ("cuda",)
        return RuntimeInfo(
            name=self.name,
            engine="transformers",
            engine_version=self._engine_version(),
            available=ok,
            devices=devices,
            formats=("hf", "safetensors", "pytorch-bin"),
            capabilities=self._capabilities(),
            model=self._model,
            remote=False,
            notes=f"pipeline task={self.task}; timeouts are cooperative",
        )

    def _engine_version(self) -> str:
        try:
            import transformers
            return str(getattr(transformers, "__version__", "unknown"))
        except Exception:  # noqa: BLE001
            return "not-installed"

    def _require_capability(self, capability: str) -> None:
        if capability not in self._capabilities():
            raise BackendError(
                f"transformers task {self.task!r} does not implement "
                f"{capability!r}; build a TransformersRuntime with a "
                f"matching task")

    # -- lifecycle --------------------------------------------------------

    def load(self, model: ModelRef) -> None:
        if model.format not in ("hf", "safetensors", "pytorch-bin",
                                "unknown"):
            raise SpecError(
                f"transformers loads HF repos/safetensors, got format "
                f"{model.format!r}")
        with self._lock:
            if self._model is not None and self._model.path == model.path \
                    and self._pipe is not None:
                return  # idempotent
            self.close()
            self._model = model

    def unload(self) -> None:
        with self._lock:
            self.close()
            self._model = None

    def _ensure_pipe(self) -> Any:
        with self._lock:
            if self._pipe is not None:
                return self._pipe
            if self._model is None:
                raise BackendUnavailable(
                    "no model loaded; call load(ModelRef(...)) first",
                    backend=self.name)
            pipeline = _import_pipeline()
            try:
                self._pipe = pipeline(
                    self.task,
                    model=self._model.path,
                    device=self.device,
                    trust_remote_code=self.trust_remote_code,
                    **self.pipe_kwargs,
                )
            except Exception as e:
                raise BackendUnavailable(
                    f"could not build {self.task} pipeline for "
                    f"{self._model.path!r}: {e}",
                    backend=self.name) from e
            return self._pipe

    def _check_deadline(self, started: float, timeout_s: float,
                        what: str) -> None:
        elapsed = time.monotonic() - started
        if elapsed > timeout_s:
            raise TimeoutError(
                f"transformers {what} exceeded timeout "
                f"({elapsed:.2f}s > {timeout_s}s); timeouts are "
                f"cooperative and checked after the blocking call",
                timeout_s=timeout_s)

    # -- inference --------------------------------------------------------

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._require_capability(CAP_GENERATE)
        prompt = self._check_prompt(prompt)
        opts = options or GenerationOptions()
        pipe = self._ensure_pipe()
        started = time.monotonic()
        try:
            out = pipe(
                prompt,
                max_new_tokens=opts.max_tokens,
                temperature=opts.temperature,
                top_p=opts.top_p,
                do_sample=opts.temperature > 0.0,
                truncation=True,
            )
        except Exception as e:
            raise BackendError(
                f"transformers generation failed: {e}") from e
        self._check_deadline(started, opts.timeout_s, "generate")
        text = str(out[0].get("generated_text", ""))
        # Pipelines return prompt + completion; strip the prompt prefix
        # so GenerationResult.text is the completion only.
        if text.startswith(prompt):
            text = text[len(prompt):]
        return GenerationResult(
            text=text.strip(),
            finish_reason="stop",
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            latency_s=time.monotonic() - started,
        )

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self._require_capability(CAP_EMBED)
        texts = self._check_texts(texts)
        pipe = self._ensure_pipe()
        try:
            token_vectors = pipe(texts)
        except Exception as e:
            raise BackendError(
                f"transformers feature extraction failed: {e}") from e
        vectors = [_mean_pool_l2(tv) for tv in token_vectors]
        return EmbeddingResult(
            vectors=vectors,
            dim=len(vectors[0]) if vectors else 0,
            model=self._model.path if self._model else "transformers")

    def classify(self, texts: list[str], labels: list[str]
                 ) -> list[ClassificationResult]:
        self._require_capability(CAP_CLASSIFY)
        texts = self._check_texts(texts)
        labels = self._check_texts(labels, "labels")
        pipe = self._ensure_pipe()
        results = []
        try:
            if self.task == "zero-shot-classification":
                for text in texts:
                    out = pipe(text, candidate_labels=labels)
                    scores = {str(label): float(score) for label, score
                              in zip(out["labels"], out["scores"],
                                     strict=True)}
                    best = str(out["labels"][0])
                    results.append(ClassificationResult(label=best,
                                                        scores=scores))
            else:  # text-classification: the model owns its label set
                for text in texts:
                    out = pipe(text)
                    top = out[0]
                    scores = {str(top["label"]): float(top["score"])}
                    results.append(ClassificationResult(
                        label=str(top["label"]), scores=scores))
        except (BackendError, SpecError):
            raise
        except Exception as e:
            raise BackendError(
                f"transformers classification failed: {e}") from e
        return results

    # -- NLI bridge --------------------------------------------------------

    def as_nli_fn(self) -> Callable[[str, str], float]:
        """Adapt to ``nli_fn(premise, statement) -> float``.

        For ``zero-shot-classification`` runtimes: probability the
        ``statement`` label wins against a neutral ``"other"`` label
        for ``premise`` — the standard entailment proxy. Drop the
        result straight into ``NLIBackend(nli_fn=...)``.
        """
        if self.task != "zero-shot-classification":
            raise BackendError(
                f"as_nli_fn needs task 'zero-shot-classification', "
                f"got {self.task!r}")

        def nli_fn(premise: str, statement: str) -> float:
            (result,) = self.classify([premise], [statement, "other"])
            return float(result.scores.get(statement, 0.0))

        return nli_fn

    # -- operations --------------------------------------------------------

    def warmup(self) -> None:
        if self._pipe is None:
            return
        if self.task in GENERATION_TASKS:
            self.generate("warmup", GenerationOptions(max_tokens=1))
        elif self.task in EMBEDDING_TASKS:
            self.embed(["warmup"])
        else:
            self.classify(["warmup"], ["warmup", "other"])

    def health(self) -> dict[str, Any]:
        try:
            engine_ok = self._pipe is not None or self.available()
        except Exception:  # noqa: BLE001 - health must never raise
            engine_ok = False
        if not engine_ok:
            status = "unavailable"
        elif self._model is None:
            status = "degraded"
        else:
            status = "ok"
        return {"status": status, "runtime": self.name,
                "available": engine_ok, "task": self.task,
                "model": self._model.display if self._model else None}

    def close(self) -> None:
        with self._lock:
            self._pipe = None  # pipelines release on GC; drop the ref


def _mean_pool_l2(token_vectors: list[list[float]]) -> list[float]:
    if not token_vectors:
        raise BackendError(
            "feature-extraction returned no token vectors")
    dim = len(token_vectors[0])
    pooled = [0.0] * dim
    for vec in token_vectors:
        if len(vec) != dim:
            raise BackendError("ragged token vectors from pipeline")
        for i, value in enumerate(vec):
            pooled[i] += value
    count = len(token_vectors)
    pooled = [v / count for v in pooled]
    norm = math.sqrt(sum(v * v for v in pooled)) or 1.0
    return [v / norm for v in pooled]
