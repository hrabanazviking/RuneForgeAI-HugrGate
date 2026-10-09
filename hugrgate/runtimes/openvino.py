"""OpenVINO runtime adapter. Slice 158.

:class:`OpenVINORuntime` serves OpenVINO IR graphs (``.xml`` + ``.bin``)
for embedding and classifier models through the v2
:class:`LocalRuntime` contract. Same honest scope as the ONNX adapter
(slice 154): a generic graph adapter cannot run autoregressive
generation loops, so :meth:`generate` raises :class:`BackendError`
pointing at generate-capable runtimes.

Text reaches the graph through an injected ``encode_fn`` (e.g. a
Hugging Face tokenizer call). ``openvino`` is optional and imported
lazily; tests inject a compiled-model double — no install, no IR
files required.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
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
from hugrgate.runtimes.onnx import EncodeFn, softmax

__all__ = [
    "OpenVINORuntime",
]


def _import_openvino() -> Any:
    try:
        from openvino.runtime import Core
    except Exception as e:
        raise BackendUnavailable(
            "openvino is not installed; install the 'openvino' extra: "
            "pip install 'hugrgate[openvino]'",
            backend="openvino") from e
    return Core


class OpenVINORuntime(LocalRuntime):
    """OpenVINO IR inference for embedding/classifier graphs.

    Parameters
    ----------
    model: :class:`ModelRef` (or plain path) to the ``.xml`` IR file
        (the ``.bin`` weights must sit beside it).
    device: OpenVINO device string — ``"CPU"``, ``"GPU"``,
        ``"AUTO"``, ... Passed straight to ``Core.compile_model``.
    input_names / output_name: graph port names. When omitted they
        are read from the compiled model (exactly one input/output
        required for auto-detection).
    encode_fn: ``(texts) -> {input_name: values}`` tokenizer callable.
    num_streams: ``compile_model`` streams hint (``0`` = default).
    compiled: injected compiled-model double for tests (duck-types
        the ``compiled_model(inputs_dict) -> {name: values}`` call).
    """

    name = "openvino"

    _CAPABILITIES = frozenset({CAP_EMBED, CAP_CLASSIFY})

    def __init__(self, model: ModelRef | str | None = None,
                 device: str = "CPU",
                 input_names: Sequence[str] | None = None,
                 output_name: str | None = None,
                 encode_fn: EncodeFn | None = None,
                 num_streams: int = 0,
                 compiled: Any = None) -> None:
        if not device or not device.strip():
            raise SpecError("device must be a non-empty string")
        if num_streams < 0:
            raise SpecError("num_streams must be >= 0")
        self._model = (ModelRef(runtime=self.name, path=model,
                                format="openvino-ir")
                       if isinstance(model, str) else model)
        self.device = device
        self.input_names = list(input_names) if input_names else None
        self.output_name = output_name
        self.encode_fn = encode_fn
        self.num_streams = num_streams
        self._compiled = compiled
        self._lock = threading.RLock()

    # -- availability ---------------------------------------------------

    @classmethod
    def available(cls) -> bool:
        try:
            _import_openvino()
            return True
        except BackendUnavailable:
            return False

    def info(self) -> RuntimeInfo:
        try:
            ok = self._compiled is not None or self.available()
        except Exception:  # noqa: BLE001 - info must never raise
            ok = False
        return RuntimeInfo(
            name=self.name,
            engine="openvino",
            engine_version=self._engine_version(),
            available=ok,
            devices=("cpu", "gpu"),
            formats=("openvino-ir",),
            capabilities=self._CAPABILITIES,
            model=self._model,
            remote=False,
            notes="embedding/classifier IR graphs; no generative loops",
        )

    def _engine_version(self) -> str:
        try:
            import openvino
            return str(getattr(openvino, "__version__", "unknown"))
        except Exception:  # noqa: BLE001
            return "not-installed"

    def _require_capability(self, capability: str) -> None:
        if capability not in self._CAPABILITIES:
            raise BackendError(
                f"runtime {self.name!r} does not implement {capability!r}; "
                f"OpenVINO IR graphs served here are embedding/classifier "
                f"graphs, use a generate-capable runtime for text "
                f"generation")

    # -- lifecycle --------------------------------------------------------

    def load(self, model: ModelRef) -> None:
        if model.format not in ("openvino-ir", "unknown"):
            raise SpecError(
                f"OpenVINO runtime loads .xml IR graphs, got format "
                f"{model.format!r} for {model.path!r}")
        with self._lock:
            if self._model is not None and self._model.path == model.path \
                    and self._compiled is not None:
                return  # idempotent
            self.close()
            self._model = model

    def unload(self) -> None:
        with self._lock:
            self.close()
            self._model = None

    def _ensure_compiled(self) -> Any:
        with self._lock:
            if self._compiled is not None:
                return self._compiled
            if self._model is None:
                raise BackendUnavailable(
                    "no model loaded; call load(ModelRef(...)) first",
                    backend=self.name)
            core_cls = _import_openvino()
            try:
                core = core_cls()
                config = {"NUM_STREAMS": str(self.num_streams)} \
                    if self.num_streams else {}
                self._compiled = core.compile_model(
                    self._model.path, self.device, config)
            except Exception as e:
                raise BackendUnavailable(
                    f"could not compile OpenVINO IR "
                    f"{self._model.path!r}: {e}",
                    backend=self.name) from e
            return self._compiled

    # -- inference --------------------------------------------------------

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._require_capability("generate")  # always raises; honest scope
        raise AssertionError("unreachable")

    def _input_feed(self, texts: list[str]) -> dict[str, Any]:
        if self.encode_fn is None:
            raise BackendError(
                "openvino text inference needs encode_fn=(texts) -> "
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
        compiled = self._ensure_compiled()
        feed = self._input_feed(texts)
        if self.input_names is None:
            inputs = list(compiled.inputs)
            if len(inputs) != 1:
                raise BackendError(
                    f"auto-detection needs exactly 1 model input, found "
                    f"{len(inputs)}; pass input_names explicitly")
            sole = getattr(inputs[0], "get_any_name",
                            lambda: str(inputs[0]))()
            feed = {sole: next(iter(feed.values()))}
        output = self.output_name
        if output is None:
            outputs = list(compiled.outputs)
            if len(outputs) != 1:
                raise BackendError(
                    f"auto-detection needs exactly 1 model output, found "
                    f"{len(outputs)}; pass output_name explicitly")
            output = getattr(outputs[0], "get_any_name",
                             lambda: str(outputs[0]))()
        try:
            result = compiled(feed)
        except Exception as e:
            raise BackendError(
                f"openvino inference failed: {e}") from e
        rows = result[output] if isinstance(result, Mapping) \
            else result[0]
        rows = [list(map(float, row)) for row in rows]
        if not rows:
            raise BackendError("openvino returned no rows")
        return rows

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self._require_capability(CAP_EMBED)
        texts = self._check_texts(texts)
        vectors = self._run(texts)
        if len(vectors) != len(texts):
            raise BackendError(
                f"openvino graph returned {len(vectors)} rows for "
                f"{len(texts)} texts")
        return EmbeddingResult(vectors=vectors, dim=len(vectors[0]),
                               model=self._model.path if self._model
                               else "openvino")

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
        if self._compiled is None:
            return  # nothing loaded; warmup is a no-op, not an error

    def health(self) -> dict[str, Any]:
        try:
            engine_ok = self._compiled is not None or self.available()
        except Exception:  # noqa: BLE001 - health must never raise
            engine_ok = False
        if not engine_ok:
            status = "unavailable"
        elif self._model is None:
            status = "degraded"
        else:
            status = "ok"
        return {"status": status, "runtime": self.name,
                "available": engine_ok, "device": self.device,
                "model": self._model.display if self._model else None}

    def close(self) -> None:
        with self._lock:
            self._compiled = None  # compiled models release on GC
