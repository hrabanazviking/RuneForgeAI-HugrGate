"""TensorRT adapter boundary. Slice 159.

:class:`TensorRTRuntime` is the fabric's boundary with NVIDIA TensorRT:
prebuilt inference engines (``.engine``/``.plan``) executed on CUDA
GPUs. The boundary is explicit and testable:

- :meth:`TensorRTRuntime.cuda_available` reports whether *this*
  machine has a CUDA device, honoring an injected override so tests
  exercise both sides (real detection tries ``torch.cuda`` when
  torch is importable, else ``nvidia-smi``);
- :meth:`available` additionally requires the ``tensorrt`` package
  (the ``tensorrt`` extra), imported lazily;
- every operation names the missing side (no CUDA vs. no package)
  in its :class:`BackendUnavailable`.

Scope mirrors the other graph adapters (embed/classify over named
I/O; text via an injected ``encode_fn``). Engine files are
deserialized with ``trt.Runtime`` for real; execution goes through
an injected ``executor`` in tests, defaulting to
:func:`default_trt_executor` — genuine synchronous buffer management
(``struct``-packed host buffers, ``memcpy_htod``/``dtoh``,
``execute_v2``) written against the TensorRT/pycuda APIs. That path
is **not validated without an NVIDIA GPU** (rule 13); it is real
code awaiting hardware, not a stub.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
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
from hugrgate.runtimes.onnx import EncodeFn, softmax

__all__ = [
    "TensorRTRuntime",
    "default_trt_executor",
]

#: ``(engine, feed, input_names, output_name) -> {output_name: rows}``.
ExecutorFn = Callable[[Any, Mapping[str, Any], Sequence[str], str],
                       dict[str, list[list[float]]]]

#: TensorRT DataType -> struct format character (no numpy needed).
_DTYPE_STRUCT = {
    "FLOAT": "f",
    "HALF": "e",
    "INT32": "i",
    "INT8": "b",
    "BOOL": "?",
}


def _import_tensorrt() -> Any:
    try:
        import tensorrt as trt
    except Exception as e:
        raise BackendUnavailable(
            "tensorrt is not installed; install the 'tensorrt' extra on "
            "an NVIDIA-GPU machine: pip install 'hugrgate[tensorrt]'",
            backend="tensorrt") from e
    return trt


def default_trt_executor(engine: Any, feed: Mapping[str, Any],
                         input_names: Sequence[str],
                         output_name: str) -> dict[str, list[list[float]]]:
    """Synchronous TensorRT execution with explicit buffer management.

    Deserializes nothing — ``engine`` is an ``ICudaEngine``. Host
    buffers are ``struct``-packed bytes (stdlib only); device buffers
    come from pycuda. Requires a real CUDA GPU; validated on hardware
    in the future, per rule 13.
    """
    _import_tensorrt()  # raises BackendUnavailable when not installed
    try:
        import pycuda.autoinit  # noqa: F401 - creates the CUDA context
        import pycuda.driver as cuda
    except Exception as e:
        raise BackendUnavailable(
            "pycuda is not installed; install the 'tensorrt' extra: "
            "pip install 'hugrgate[tensorrt]'",
            backend="tensorrt") from e

    context = engine.create_execution_context()
    bindings: list[int] = []
    host_bufs: dict[str, bytearray] = {}
    dev_bufs: dict[str, Any] = {}
    fmt_of: dict[str, str] = {}

    def _setup(name: str, is_input: bool) -> None:
        shape = tuple(engine.get_tensor_shape(name))
        dtype_name = str(engine.get_tensor_dtype(name)).split(".")[-1]
        fmt = _DTYPE_STRUCT.get(dtype_name)
        if fmt is None:
            raise BackendError(
                f"tensorrt dtype {dtype_name!r} has no struct mapping")
        count = 1
        for dim in shape:
            count *= dim
        nbytes = count * struct.calcsize(fmt)
        host = bytearray(nbytes)
        if is_input:
            flat: list[float] = []
            _flatten(feed[name], flat)
            if len(flat) != count:
                raise BackendError(
                    f"input {name!r}: got {len(flat)} values, engine "
                    f"expects shape {shape} ({count})")
            struct.pack_into(f"<{count}{fmt}", host, 0, *flat)
        dev = cuda.mem_alloc(nbytes)
        if is_input:
            cuda.memcpy_htod(dev, bytes(host))
        bindings.append(int(dev))
        host_bufs[name] = host
        dev_bufs[name] = dev
        fmt_of[name] = fmt

    try:
        for name in input_names:
            _setup(name, True)
        _setup(output_name, False)
        ok = context.execute_v2(bindings)
        if not ok:
            raise BackendError("tensorrt execute_v2 reported failure")
        host = host_bufs[output_name]
        cuda.memcpy_dtoh(host, dev_bufs[output_name])
        shape = tuple(engine.get_tensor_shape(output_name))
        count = 1
        for dim in shape:
            count *= dim
        fmt = fmt_of[output_name]
        flat = struct.unpack_from(f"<{count}{fmt}", bytes(host))
        rows = _unflatten(list(flat), shape)
        return {output_name: rows}
    finally:
        for dev in dev_bufs.values():
            try:
                dev.free()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass


def _flatten(nested: Any, out: list[float]) -> None:
    if isinstance(nested, (list, tuple)):
        for item in nested:
            _flatten(item, out)
    else:
        out.append(float(nested))


def _unflatten(flat: list[float], shape: tuple[int, ...]
               ) -> list[list[float]]:
    if len(shape) == 1:
        return [flat]
    if len(shape) == 2:
        rows, cols = shape
        return [flat[r * cols:(r + 1) * cols] for r in range(rows)]
    raise BackendError(
        f"tensorrt adapter supports 1-D/2-D outputs, got shape {shape}")


class TensorRTRuntime(LocalRuntime):
    """NVIDIA TensorRT inference boundary for prebuilt engines.

    Parameters
    ----------
    model: :class:`ModelRef` (or plain path) to a ``.engine``/``.plan``
        file.
    cuda_override: injected CUDA-availability for tests (``True`` /
        ``False``); when None, real detection runs.
    input_names / output_name: engine tensor names (auto-detection is
        *not* offered — TensorRT engines should name their IO
        explicitly).
    encode_fn: ``(texts) -> {input_name: values}`` tokenizer callable.
    executor: injected ``ExecutorFn`` for tests; defaults to
        :func:`default_trt_executor`.
    engine: injected deserialized engine for tests (skips the
        ``trt.Runtime`` deserialization).
    """

    name = "tensorrt"

    _CAPABILITIES = frozenset({CAP_EMBED, CAP_CLASSIFY})

    def __init__(self, model: ModelRef | str | None = None,
                 cuda_override: bool | None = None,
                 input_names: Sequence[str] | None = None,
                 output_name: str | None = None,
                 encode_fn: EncodeFn | None = None,
                 executor: ExecutorFn | None = None,
                 engine: Any = None) -> None:
        self._model = (ModelRef(runtime=self.name, path=model,
                                format="tensorrt-engine")
                       if isinstance(model, str) else model)
        self._cuda_override = cuda_override
        self.input_names = list(input_names) if input_names else None
        self.output_name = output_name
        self.encode_fn = encode_fn
        self.executor = executor or default_trt_executor
        self._engine = engine
        self._lock = threading.RLock()

    # -- boundary ----------------------------------------------------------

    @classmethod
    def cuda_available(cls, override: bool | None = None) -> bool:
        """Whether a CUDA device is present.

        ``override`` forces the answer (tests). Otherwise: torch's
        ``cuda.is_available()`` when torch imports, else ``nvidia-smi``.
        """
        if override is not None:
            return override
        try:
            import torch
            return bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001 - torch optional
            pass
        if shutil.which("nvidia-smi") is None:
            return False
        try:
            proc = subprocess.run(
                ["nvidia-smi", "-L"], capture_output=True, timeout=10)
            return proc.returncode == 0 and b"GPU" in proc.stdout
        except Exception:  # noqa: BLE001 - absence means no CUDA
            return False

    @classmethod
    def available(cls) -> bool:
        if not cls.cuda_available():
            return False
        try:
            _import_tensorrt()
            return True
        except BackendUnavailable:
            return False

    def _check_cuda(self) -> None:
        if not self.cuda_available(self._cuda_override):
            raise BackendUnavailable(
                "TensorRT needs an NVIDIA CUDA GPU; none detected on "
                "this machine", backend=self.name)

    def _check_boundary(self) -> None:
        self._check_cuda()
        try:
            _import_tensorrt()
        except BackendUnavailable as e:
            raise BackendUnavailable(str(e), backend=self.name) from e

    def info(self) -> RuntimeInfo:
        try:
            ok = self.available()
        except Exception:  # noqa: BLE001 - info must never raise
            ok = False
        return RuntimeInfo(
            name=self.name,
            engine="tensorrt",
            engine_version=self._engine_version(),
            available=ok,
            devices=("cuda",),
            formats=("tensorrt-engine",),
            capabilities=self._CAPABILITIES,
            model=self._model,
            remote=False,
            notes="prebuilt .engine/.plan on CUDA; needs NVIDIA GPU",
        )

    def _engine_version(self) -> str:
        try:
            trt = _import_tensorrt()
            return str(getattr(trt, "__version__", "unknown"))
        except BackendUnavailable:
            return "not-installed"

    def _require_capability(self, capability: str) -> None:
        if capability not in self._CAPABILITIES:
            raise BackendError(
                f"runtime {self.name!r} does not implement {capability!r}; "
                f"TensorRT engines served here are embedding/classifier "
                f"graphs, use a generate-capable runtime for text "
                f"generation")

    # -- lifecycle -----------------------------------------------------------

    def load(self, model: ModelRef) -> None:
        if model.format not in ("tensorrt-engine", "unknown"):
            raise SpecError(
                f"TensorRT runtime loads .engine/.plan files, got format "
                f"{model.format!r} for {model.path!r}")
        with self._lock:
            if self._model is not None and self._model.path == model.path \
                    and self._engine is not None:
                return  # idempotent
            self.close()
            self._model = model

    def unload(self) -> None:
        with self._lock:
            self.close()
            self._model = None

    def _ensure_engine(self) -> Any:
        with self._lock:
            if self._engine is not None:
                # Injected double: honor the CUDA boundary but don't
                # require the tensorrt package for a fake engine.
                self._check_cuda()
                return self._engine
            if self._model is None:
                raise BackendUnavailable(
                    "no model loaded; call load(ModelRef(...)) first",
                    backend=self.name)
        self._check_boundary()
        with self._lock:
            if self._engine is not None:
                return self._engine
            trt = _import_tensorrt()
            try:
                with open(self._model.path, "rb") as fh:
                    blob = fh.read()
                runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
                self._engine = runtime.deserialize_cuda_engine(blob)
            except Exception as e:
                raise BackendUnavailable(
                    f"could not deserialize TensorRT engine "
                    f"{self._model.path!r}: {e}",
                    backend=self.name) from e
            if self._engine is None:
                raise BackendUnavailable(
                    f"tensorrt refused engine file {self._model.path!r}",
                    backend=self.name)
            return self._engine

    # -- inference -------------------------------------------------------------

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._require_capability("generate")  # always raises; honest scope
        raise AssertionError("unreachable")

    def _input_feed(self, texts: list[str]) -> dict[str, Any]:
        if self.encode_fn is None:
            raise BackendError(
                "tensorrt text inference needs encode_fn=(texts) -> "
                "{input_name: values}; inject a tokenizer callable")
        try:
            feed = dict(self.encode_fn(texts))
        except Exception as e:
            raise BackendError(f"encode_fn failed: {e}") from e
        if self.input_names is None:
            raise BackendError(
                "tensorrt engines require explicit input_names")
        missing = [n for n in self.input_names if n not in feed]
        if missing:
            raise BackendError(
                f"encode_fn did not produce inputs {missing}")
        return {n: feed[n] for n in self.input_names}

    def _run(self, texts: list[str]) -> list[list[float]]:
        if self.output_name is None:
            raise BackendError(
                "tensorrt engines require an explicit output_name")
        if self.input_names is None:
            raise BackendError(
                "tensorrt engines require explicit input_names")
        engine = self._ensure_engine()
        feed = self._input_feed(texts)
        try:
            result = self.executor(engine, feed, self.input_names,
                                   self.output_name)
        except (BackendError, BackendUnavailable):
            raise
        except Exception as e:
            raise BackendError(f"tensorrt execution failed: {e}") from e
        rows = result.get(self.output_name)
        if not rows:
            raise BackendError("tensorrt returned no rows")
        return [list(map(float, row)) for row in rows]

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self._require_capability(CAP_EMBED)
        texts = self._check_texts(texts)
        vectors = self._run(texts)
        if len(vectors) != len(texts):
            raise BackendError(
                f"tensorrt engine returned {len(vectors)} rows for "
                f"{len(texts)} texts")
        return EmbeddingResult(vectors=vectors, dim=len(vectors[0]),
                               model=self._model.path if self._model
                               else "tensorrt")

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

    # -- operations --------------------------------------------------------------

    def warmup(self) -> None:
        if self._engine is None:
            return  # nothing loaded; warmup is a no-op, not an error

    def health(self) -> dict[str, Any]:
        cuda = self.cuda_available(self._cuda_override)
        try:
            engine_ok = cuda and (self._engine is not None
                                  or self.available())
        except Exception:  # noqa: BLE001 - health must never raise
            engine_ok = False
        if not cuda:
            status = "unavailable"
        elif self._model is None:
            status = "degraded"
        else:
            status = "ok" if engine_ok else "degraded"
        return {"status": status, "runtime": self.name,
                "available": engine_ok, "cuda": cuda,
                "model": self._model.display if self._model else None}

    def close(self) -> None:
        with self._lock:
            self._engine = None  # TRT engines release on GC; drop ref
