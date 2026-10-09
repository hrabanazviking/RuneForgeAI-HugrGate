"""llama.cpp runtime adapter. Slice 152.

Canonical GGUF inference runtime implementing :class:`LocalRuntime`.
This supersedes the first-generation ``LlamaCppEngine`` in
``hugrgate.backends.llm`` (slice 35): same engine, but with the v2
contract — lazy model loading, embedding/tokenize support, GBNF grammar
passthrough, timeouts, lifecycle, and capability advertisement. The old
name survives as a thin legacy-compat subclass (see below) so
``LLMBackend(engine=LlamaCppEngine(...))`` keeps working.

The ``llama_cpp`` dependency is optional and imported lazily; without
it the module imports fine, :meth:`available` reports False, and every
operation raises :class:`BackendUnavailable`. Tests inject a fake engine
object — no model download required.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Any

from hugrgate.errors import (
    BackendError,
    BackendUnavailable,
    SpecError,
    TimeoutError,
)
from hugrgate.runtimes import (
    CAP_EMBED,
    CAP_GENERATE,
    CAP_GRAMMAR,
    CAP_TOKENIZE,
    EmbeddingResult,
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
    ModelRef,
    RuntimeInfo,
)

__all__ = [
    "LlamaCppRuntime",
]


def _import_llama_cpp() -> Any:
    try:
        from llama_cpp import Llama
    except Exception as e:
        raise BackendUnavailable(
            "llama_cpp is not installed; install the 'llm' extra: "
            "pip install 'hugrgate[llm]'",
            backend="llama-cpp") from e
    return Llama


class LlamaCppRuntime(LocalRuntime):
    """GGUF inference through llama.cpp.

    Parameters
    ----------
    model: :class:`ModelRef` (or plain path string) to a ``.gguf`` file.
        Loading is lazy: the file is opened on first inference or on
        :meth:`load`, never at construction.
    n_ctx, n_gpu_layers, n_threads, n_batch, embedding: passed to
        ``llama_cpp.Llama``. ``embedding=True`` switches the instance
        into embedding mode (advertises ``embed`` instead of
        ``generate``).
    llama: injected engine object for tests (duck-types ``Llama``).
    """

    name = "llama-cpp"

    def __init__(self, model: ModelRef | str | None = None,
                 n_ctx: int = 4096, n_gpu_layers: int = 0,
                 n_threads: int | None = None, n_batch: int = 512,
                 embedding: bool = False, llama: Any = None) -> None:
        if n_ctx < 1:
            raise SpecError(f"n_ctx must be >= 1, got {n_ctx}")
        if n_gpu_layers < 0:
            raise SpecError(
                f"n_gpu_layers must be >= 0, got {n_gpu_layers}")
        self._model = (ModelRef(runtime=self.name, path=model,
                                format="gguf")
                       if isinstance(model, str) else model)
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self.n_threads = n_threads
        self.n_batch = n_batch
        self.embedding_mode = embedding
        self._llama = llama
        self._lock = threading.RLock()

    # -- availability ---------------------------------------------------

    @classmethod
    def available(cls) -> bool:
        try:
            _import_llama_cpp()
            return True
        except BackendUnavailable:
            return False

    def info(self) -> RuntimeInfo:
        caps = {CAP_GENERATE, CAP_GRAMMAR, CAP_TOKENIZE}
        if self.embedding_mode:
            caps = {CAP_EMBED, CAP_TOKENIZE}
        try:
            ok = self.available()
        except Exception:  # noqa: BLE001 - info must never raise
            ok = False
        return RuntimeInfo(
            name=self.name,
            engine="llama.cpp",
            engine_version=self._engine_version(),
            available=ok,
            devices=("cpu", "cuda", "metal", "vulkan"),
            formats=("gguf",),
            capabilities=frozenset(caps),
            model=self._model,
            remote=False,
            notes="lazy GGUF loading; GBNF grammar passthrough",
        )

    def _engine_version(self) -> str:
        try:
            import llama_cpp
            return getattr(llama_cpp, "__version__", "unknown")
        except Exception:  # noqa: BLE001
            return "not-installed"

    # -- lifecycle --------------------------------------------------------

    def load(self, model: ModelRef) -> None:
        if model.format not in ("gguf", "unknown"):
            raise SpecError(
                f"llama.cpp loads GGUF models, got format "
                f"{model.format!r} for {model.path!r}")
        with self._lock:
            if self._model is not None and self._model.path == model.path \
                    and self._llama is not None:
                return  # already loaded — idempotent
            self.close()
            self._model = model

    def unload(self) -> None:
        with self._lock:
            self.close()
            self._model = None

    def _ensure_engine(self) -> Any:
        with self._lock:
            if self._llama is not None:
                return self._llama
            if self._model is None:
                raise BackendUnavailable(
                    "no model loaded; call load(ModelRef(...)) first",
                    backend=self.name)
            llama_cls = _import_llama_cpp()
            try:
                self._llama = llama_cls(
                    model_path=self._model.path,
                    n_ctx=self.n_ctx,
                    n_gpu_layers=self.n_gpu_layers,
                    n_threads=self.n_threads,
                    n_batch=self.n_batch,
                    embedding=self.embedding_mode,
                    verbose=False,
                )
            except Exception as e:
                raise BackendUnavailable(
                    f"could not load GGUF model {self._model.path!r}: {e}",
                    backend=self.name) from e
            return self._llama

    # -- inference ----------------------------------------------------------

    def _generate_raw(self, prompt: str, options: GenerationOptions
                      ) -> tuple[str, float, dict[str, Any]]:
        """Return ``(text, confidence, raw_response)``.

        Shared by :meth:`generate` and the legacy ``LLMEngine``
        adapter in ``hugrgate.backends.llm``.
        """
        if self.embedding_mode:
            raise BackendError(
                "this instance was created with embedding=True; "
                "it cannot generate")
        prompt = self._check_prompt(prompt)
        llm = self._ensure_engine()
        deadline = time.monotonic() + options.timeout_s
        try:
            out = llm(
                prompt,
                max_tokens=options.max_tokens,
                temperature=options.temperature,
                top_p=options.top_p,
                stop=list(options.stop) or None,
                seed=options.seed if options.seed is not None else -1,
                grammar=options.grammar,
                logprobs=2,
            )
        except (BackendError, BackendUnavailable):
            raise
        except Exception as e:
            raise BackendError(f"llama.cpp generation failed: {e}") from e
        if time.monotonic() > deadline:
            raise TimeoutError("llama.cpp generation exceeded timeout",
                               timeout_s=options.timeout_s)
        choice = out["choices"][0]
        text = str(choice["text"])
        logprobs = choice.get("logprobs") or {}
        token_logprobs = logprobs.get("token_logprobs") or []
        confidence = 1.0
        if token_logprobs:
            first = token_logprobs[:2]
            confidence = float(math.exp(sum(first) / len(first)))
            confidence = max(0.0, min(1.0, confidence))
        return text.strip(), confidence, out

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._require_capability(CAP_GENERATE)
        opts = options or GenerationOptions()
        started = time.monotonic()
        text, _confidence, out = self._generate_raw(prompt, opts)
        usage = out.get("usage") or {}
        return GenerationResult(
            text=text,
            finish_reason="stop",
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_s=time.monotonic() - started,
        )

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self._require_capability(CAP_EMBED)
        texts = self._check_texts(texts)
        llm = self._ensure_engine()
        try:
            out = llm.create_embedding(texts)
        except Exception as e:
            raise BackendError(
                f"llama.cpp embedding failed: {e}") from e
        vectors = [list(item["embedding"]) for item in out["data"]]
        if not vectors:
            raise BackendError("llama.cpp returned no embeddings")
        return EmbeddingResult(vectors=vectors, dim=len(vectors[0]),
                               model=self._model.path if self._model
                               else "llama-cpp")

    def tokenize(self, text: str) -> list[int]:
        self._require_capability(CAP_TOKENIZE)
        self._check_prompt(text)
        llm = self._ensure_engine()
        try:
            return [int(t) for t in llm.tokenize(text.encode("utf-8"))]
        except Exception as e:
            raise BackendError(f"llama.cpp tokenize failed: {e}") from e

    # -- operations -----------------------------------------------------------

    def warmup(self) -> None:
        if self._model is None:
            return  # nothing loaded; warmup is a no-op, not an error
        if self.embedding_mode:
            self.embed(["warmup"])
        else:
            self.generate("warmup",
                          GenerationOptions(max_tokens=1, timeout_s=30.0))

    def health(self) -> dict[str, Any]:
        engine_present = self._llama is not None or self.available()
        if not engine_present:
            status = "unavailable"
        elif self._model is None:
            status = "degraded"  # engine present, no model loaded
        else:
            status = "ok"
        return {"status": status, "runtime": self.name,
                "available": engine_present,
                "model": self._model.display if self._model else None}

    def close(self) -> None:
        with self._lock:
            llm, self._llama = self._llama, None
        if llm is not None:
            close = getattr(llm, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 - best effort
                    pass

