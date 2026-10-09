"""ONNX Runtime adapter. Slice 154.

:class:`OnnxRuntime` serves ONNX graphs (embedding and classifier
models) through the v2 :class:`LocalRuntime` contract. Scope is
deliberate and honest: a generic adapter cannot run autoregressive
* generation* loops without model-specific I/O handling, so
:meth:`generate` raises :class:`BackendError` directing the caller to
a generate-capable runtime. What this adapter does really well:

- ``embed``: single-vector-output graphs (mean-pooled sentence
  embeddings and the like);
- ``classify``: single-logits-output graphs with a softmax over the
  caller-supplied labels (label count must match the logits dim).

Text must be tokenized before it reaches the graph: pass
``encode_fn(texts) -> {input_name: values}`` (e.g. a Hugging Face
tokenizer ``__call__``), or inject a ready ``session`` in tests.
``onnxruntime`` is optional and imported lazily.

This slice also retires the ``RESERVED_EXTRAS`` reservation for the
``onnx`` extra in ``tests/test_dependency_rules.py`` — the future
ONNX backend it was reserved for is this one.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import (
    CAP_CLASSIFY,
    CAP_EMBED,
    ClassificationResult,
    EmbeddingResult,
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
    ModelRef,
    RuntimeInfo,
)

__all__ = [
    "OnnxRuntime",
    "softmax",
]

#: ``texts -> {session_input_name: nested sequences}``.
EncodeFn = Callable[[Sequence[str]], Mapping[str, Any]]


def softmax(logits: Sequence[float]) -> list[float]:
    """Numerically stable softmax (pure python, no numpy needed)."""
    if not logits:
        raise SpecError("softmax needs at least one logit")
    peak = max(logits)
    exps = [math.exp(v - peak) for v in logits]
    total = sum(exps)
    return [v / total for v in exps]


def _import_ort() -> Any:
    try:
        import onnxruntime as ort
    except Exception as e:
        raise BackendUnavailable(
            "onnxruntime is not installed; install the 'onnx' extra: "
            "pip install 'hugrgate[onnx]'",
            backend="onnx") from e
    return ort


class OnnxRuntime(LocalRuntime):
    """ONNX Runtime inference for embedding/classifier graphs.

    Parameters
    ----------
    model: :class:`ModelRef` (or plain path) to a ``.onnx`` file.
    providers: execution providers, e.g.
        ``["CUDAExecutionProvider", "CPUExecutionProvider"]``.
        Defaults to ``["CPUExecutionProvider"]``; unknown providers
        raise :class:`SpecError` at session build time.
    input_names: session input names in order. When omitted, they are
        read from the loaded session (exactly one input required for
        auto-detection).
    output_name: session output name. When omitted, the session must
        have exactly one output.
    encode_fn: ``(texts) -> {input_name: values}`` tokenizer callable.
        Required for real inference; tests inject a ``session`` and a
        trivial ``encode_fn``.
    intra_op_num_threads: ORT session thread knob (``0`` = default).
    session: injected session object for tests (duck-types
        ``onnxruntime.InferenceSession``).
    """

    name = "onnx"

    _CAPABILITIES = frozenset({CAP_EMBED, CAP_CLASSIFY})

    def __init__(self, model: ModelRef | str | None = None,
                 providers: Sequence[str] | None = None,
                 input_names: Sequence[str] | None = None,
                 output_name: str | None = None,
                 encode_fn: EncodeFn | None = None,
                 intra_op_num_threads: int = 0,
                 session: Any = None) -> None:
        if intra_op_num_threads < 0:
            raise SpecError("intra_op_num_threads must be >= 0")
        self._model = (ModelRef(runtime=self.name, path=model,
                                format="onnx")
                       if isinstance(model, str) else model)
        self.providers = list(providers) if providers \
            else ["CPUExecutionProvider"]
        self.input_names = list(input_names) if input_names else None
        self.output_name = output_name
        self.encode_fn = encode_fn
        self.intra_op_num_threads = intra_op_num_threads
        self._session = session
        self._lock = threading.RLock()

    # -- availability ---------------------------------------------------

    @classmethod
    def available(cls) -> bool:
        try:
            _import_ort()
            return True
        except BackendUnavailable:
            return False

    def info(self) -> RuntimeInfo:
        try:
            ok = self._session is not None or self.available()
        except Exception:  # noqa: BLE001 - info must never raise
            ok = False
        return RuntimeInfo(
            name=self.name,
            engine="onnxruntime",
            engine_version=self._engine_version(),
            available=ok,
            devices=("cpu", "cuda"),
            formats=("onnx",),
            capabilities=self._CAPABILITIES,
            model=self._model,
            remote=False,
            notes="embedding/classifier graphs; no generative loops",
        )

    def _engine_version(self) -> str:
        try:
            import onnxruntime as ort
            return str(getattr(ort, "__version__", "unknown"))
        except Exception:  # noqa: BLE001
            return "not-installed"

    def _require_capability(self, capability: str) -> None:
        if capability not in self._CAPABILITIES:
            raise BackendError(
                f"runtime {self.name!r} does not implement {capability!r}; "
                f"ONNX graphs served here are embedding/classifier graphs, "
                f"use a generate-capable runtime for text generation")

    # -- lifecycle --------------------------------------------------------

    def load(self, model: ModelRef) -> None:
        if model.format not in ("onnx", "unknown"):
            raise SpecError(
                f"ONNX runtime loads .onnx graphs, got format "
                f"{model.format!r} for {model.path!r}")
        with self._lock:
            if self._model is not None and self._model.path == model.path \
                    and self._session is not None:
                return  # idempotent
            self.close()
            self._model = model

    def unload(self) -> None:
        with self._lock:
            self.close()
            self._model = None

    def _ensure_session(self) -> Any:
        with self._lock:
            if self._session is not None:
                return self._session
            if self._model is None:
                raise BackendUnavailable(
                    "no model loaded; call load(ModelRef(...)) first",
                    backend=self.name)
            ort = _import_ort()
            available = ort.get_available_providers()
            for provider in self.providers:
                if provider not in available:
                    raise SpecError(
                        f"provider {provider!r} not available; "
                        f"available: {available}")
            options = ort.SessionOptions()
            options.intra_op_num_threads = self.intra_op_num_threads
            options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL)
            try:
                self._session = ort.InferenceSession(
                    self._model.path, sess_options=options,
                    providers=self.providers)
            except Exception as e:
                raise BackendUnavailable(
                    f"could not load ONNX graph {self._model.path!r}: {e}",
                    backend=self.name) from e
            return self._session

    # -- inference --------------------------------------------------------

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._require_capability("generate")  # always raises; honest scope
        raise AssertionError("unreachable")

    def _input_feed(self, texts: list[str]) -> dict[str, Any]:
        if self.encode_fn is None:
            raise BackendError(
                "onnx text inference needs encode_fn=(texts) -> "
                "{input_name: values}; inject a tokenizer callable")
        try:
            feed = dict(self.encode_fn(texts))
        except Exception as e:
            raise BackendError(f"encode_fn failed: {e}") from e
        names = self.input_names or sorted(feed)
        missing = [n for n in names if n not in feed]
        if missing:
            raise BackendError(
                f"encode_fn did not produce inputs {missing}")
        return {n: feed[n] for n in names}

    def _run(self, texts: list[str]) -> list[list[float]]:
        session = self._ensure_session()
        feed = self._input_feed(texts)
        if self.input_names is None:
            inputs = session.get_inputs()
            if len(inputs) != 1:
                raise BackendError(
                    f"auto-detection needs exactly 1 session input, "
                    f"found {len(inputs)}; pass input_names explicitly")
            feed = {inputs[0].name: next(iter(feed.values()))}
        output = self.output_name
        if output is None:
            outputs = session.get_outputs()
            if len(outputs) != 1:
                raise BackendError(
                    f"auto-detection needs exactly 1 session output, "
                    f"found {len(outputs)}; pass output_name explicitly")
            output = outputs[0].name
        try:
            raw = session.run([output], feed)
        except Exception as e:
            raise BackendError(f"onnxruntime inference failed: {e}") from e
        rows = raw[0]
        if not isinstance(rows, (list, tuple)) or not rows:
            raise BackendError(
                f"unexpected onnx output shape: {type(rows).__name__}")
        return [list(map(float, row)) for row in rows]

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self._require_capability(CAP_EMBED)
        texts = self._check_texts(texts)
        vectors = self._run(texts)
        if len(vectors) != len(texts):
            raise BackendError(
                f"onnx graph returned {len(vectors)} rows for "
                f"{len(texts)} texts")
        return EmbeddingResult(vectors=vectors, dim=len(vectors[0]),
                               model=self._model.path if self._model
                               else "onnx")

    def classify(self, texts: list[str], labels: list[str]
                 ) -> list[ClassificationResult]:
        self._require_capability(CAP_CLASSIFY)
        texts = self._check_texts(texts)
        labels = self._check_texts(labels, "labels")
        logits = self._run(texts)
        results = []
        for row in logits:
            if len(row) != len(labels):
                raise BackendError(
                    f"logits dim {len(row)} != {len(labels)} labels; "
                    f"pass exactly one label per output logit")
            scores = dict(zip(labels, softmax(row), strict=True))
            best = max(scores, key=lambda k: scores[k])
            results.append(ClassificationResult(label=best, scores=scores))
        return results

    # -- operations --------------------------------------------------------

    def warmup(self) -> None:
        if self._session is None:
            return  # nothing loaded; warmup is a no-op, not an error

    def health(self) -> dict[str, Any]:
        session_present = self._session is not None
        try:
            engine_ok = session_present or self.available()
        except Exception:  # noqa: BLE001 - health must never raise
            engine_ok = False
        if not engine_ok:
            status = "unavailable"
        elif self._model is None:
            status = "degraded"
        else:
            status = "ok"
        return {"status": status, "runtime": self.name,
                "available": engine_ok,
                "model": self._model.display if self._model else None}

    def close(self) -> None:
        with self._lock:
            self._session = None  # ORT sessions release on GC; drop ref
