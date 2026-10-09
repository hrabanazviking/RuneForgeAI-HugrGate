"""vLLM local adapter. Slice 156.

:class:`VLLMRuntime` serves vLLM through the v2 :class:`LocalRuntime`
contract in two modes:

- **server mode** (primary): talks to a ``vllm serve`` OpenAI-compatible
  endpoint (``POST /v1/completions``) with only the standard library —
  no vLLM install needed in *this* process;
- **in-process mode**: drives an injected ``vllm.LLM``-compatible
  object, or builds one via :meth:`VLLMRuntime.in_process` (lazily
  imports ``vllm``; install the ``vllm`` extra).

``load()`` selects the served model id; it never starts a server.
``embed`` is supported in server mode against ``/v1/embeddings`` when
the instance is created with ``embedding=True`` (a vLLM server started
with ``--task embed``).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import (
    CAP_EMBED,
    CAP_GENERATE,
    EmbeddingResult,
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
    ModelRef,
    RuntimeInfo,
)

__all__ = [
    "DEFAULT_VLLM_HOST",
    "VLLMRuntime",
]

#: Default ``vllm serve`` address.
DEFAULT_VLLM_HOST = "http://localhost:8000"

_PROBE_TIMEOUT_S = 2.0


@dataclass
class _SamplingParamsShim:
    """Transparent stand-in for ``vllm.SamplingParams``.

    Used only when ``vllm`` is not installed and an llm-like test
    double was injected. Never meets a real ``vllm.LLM``.
    """

    max_tokens: int = 16
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = -1
    stop: list[str] | None = None


def _import_vllm() -> Any:
    try:
        import vllm
    except Exception as e:
        raise BackendUnavailable(
            "vllm is not installed; install the 'vllm' extra: "
            "pip install 'hugrgate[vllm]'",
            backend="vllm") from e
    return vllm


def _post_json(url: str, payload: dict[str, Any],
               timeout_s: float) -> Any:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8"))
            message = detail.get("message", detail)
        except Exception:  # noqa: BLE001 - best effort
            message = str(e)
        raise BackendError(f"vllm server error: {message}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise BackendUnavailable(
            f"vllm server not reachable at {url}: {e}",
            backend="vllm") from e


def _get_json(url: str, timeout_s: float) -> Any:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except Exception as e:
        raise BackendUnavailable(
            f"vllm server not reachable at {url}: {e}",
            backend="vllm") from e


class VLLMRuntime(LocalRuntime):
    """vLLM inference, server-side or in-process.

    Parameters
    ----------
    model: :class:`ModelRef` (or HF id string) served by vLLM.
    host: OpenAI-compatible base URL for server mode
        (``"http://localhost:8000"``).
    llm: injected ``vllm.LLM``-compatible object for in-process mode
        (tests). When given, server mode is disabled.
    embedding: talk to ``/v1/embeddings`` instead of completions
        (server must run with ``--task embed``).
    timeout_s: per-request timeout.
    transport: injected ``(path, payload) -> response`` callable for
        server-mode tests (``path`` like ``"/v1/completions"``).
    """

    name = "vllm"

    def __init__(self, model: ModelRef | str | None = None,
                 host: str = DEFAULT_VLLM_HOST,
                 llm: Any = None, embedding: bool = False,
                 timeout_s: float = 120.0, transport: Any = None) -> None:
        if timeout_s <= 0:
            raise SpecError(f"timeout_s must be > 0, got {timeout_s}")
        self._model = (ModelRef(runtime=self.name, path=model,
                                format="hf")
                       if isinstance(model, str) else model)
        self.host = host.rstrip("/")
        self._llm = llm
        self.embedding_mode = embedding
        self.timeout_s = timeout_s
        self._transport = transport
        self._lock = threading.RLock()

    @classmethod
    def in_process(cls, model: ModelRef | str,
                   tensor_parallel_size: int = 1,
                   gpu_memory_utilization: float = 0.9,
                   max_model_len: int | None = None,
                   quantization: str | None = None,
                   **kwargs: Any) -> VLLMRuntime:
        """Build an in-process runtime around ``vllm.LLM``.

        Lazily imports ``vllm`` — raises :class:`BackendUnavailable`
        without it. ``kwargs`` are forwarded to :class:`VLLMRuntime`.
        """
        vllm = _import_vllm()
        model_id = model.path if isinstance(model, ModelRef) else model
        llm_kwargs: dict[str, Any] = {
            "model": model_id,
            "tensor_parallel_size": tensor_parallel_size,
            "gpu_memory_utilization": gpu_memory_utilization,
        }
        if max_model_len is not None:
            llm_kwargs["max_model_len"] = max_model_len
        if quantization is not None:
            llm_kwargs["quantization"] = quantization
        try:
            llm = vllm.LLM(**llm_kwargs)
        except Exception as e:
            raise BackendUnavailable(
                f"could not start vllm.LLM for {model_id!r}: {e}",
                backend="vllm") from e
        return cls(model=model, llm=llm, **kwargs)

    # -- availability ---------------------------------------------------

    @classmethod
    def available(cls) -> bool:
        try:
            _import_vllm()
            return True
        except BackendUnavailable:
            pass
        try:
            _get_json(DEFAULT_VLLM_HOST + "/v1/models", _PROBE_TIMEOUT_S)
            return True
        except BackendUnavailable:
            return False

    def _capabilities(self) -> frozenset[str]:
        if self.embedding_mode:
            return frozenset({CAP_EMBED})
        return frozenset({CAP_GENERATE})

    def info(self) -> RuntimeInfo:
        try:
            ok = (self._llm is not None or self._transport is not None
                  or self.available())
        except Exception:  # noqa: BLE001 - info must never raise
            ok = False
        mode = "in-process" if self._llm is not None else "server"
        return RuntimeInfo(
            name=self.name,
            engine="vllm",
            engine_version=self._engine_version(),
            available=ok,
            devices=("cuda",),
            formats=("hf", "vllm"),
            capabilities=self._capabilities(),
            model=self._model,
            remote=False,
            notes=f"{mode} mode; OpenAI-compatible completions API",
        )

    def _engine_version(self) -> str:
        try:
            vllm = _import_vllm()
            return str(getattr(vllm, "__version__", "unknown"))
        except BackendUnavailable:
            return "not-installed"

    def _require_capability(self, capability: str) -> None:
        if capability not in self._capabilities():
            raise BackendError(
                f"vllm runtime does not implement {capability!r} "
                f"(embedding_mode={self.embedding_mode})")

    # -- lifecycle --------------------------------------------------------

    def load(self, model: ModelRef) -> None:
        if model.format not in ("hf", "vllm", "safetensors", "unknown"):
            raise SpecError(
                f"vllm serves HF-style models, got format "
                f"{model.format!r}")
        with self._lock:
            self._model = model

    def unload(self) -> None:
        with self._lock:
            self._model = None

    def _require_model(self) -> str:
        if self._model is None:
            raise BackendUnavailable(
                "no model selected; call load(ModelRef(...)) first",
                backend=self.name)
        return self._model.path

    def _server_call(self, path: str, payload: dict[str, Any],
                     timeout_s: float) -> Any:
        if self._transport is not None:
            return self._transport(path, payload)
        return _post_json(self.host + path, payload, timeout_s)

    # -- inference --------------------------------------------------------

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._require_capability(CAP_GENERATE)
        prompt = self._check_prompt(prompt)
        opts = options or GenerationOptions()
        model_id = self._require_model()
        started = time.monotonic()
        if self._llm is not None:
            text, finish = self._generate_in_process(prompt, opts)
            prompt_tokens = completion_tokens = 0
        else:
            payload: dict[str, Any] = {
                "model": model_id,
                "prompt": prompt,
                "max_tokens": opts.max_tokens,
                "temperature": opts.temperature,
                "top_p": opts.top_p,
                "seed": opts.seed if opts.seed is not None else -1,
                "stream": False,
            }
            if opts.stop:
                payload["stop"] = list(opts.stop)
            data = self._server_call("/v1/completions", payload,
                                     opts.timeout_s)
            choice = (data.get("choices") or [{}])[0]
            text = str(choice.get("text", "")).strip()
            finish = {"stop": "stop", "length": "length"}.get(
                str(choice.get("finish_reason", "stop")), "stop")
            usage = data.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
        return GenerationResult(
            text=text, finish_reason=finish,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_s=time.monotonic() - started)

    def _generate_in_process(self, prompt: str,
                             opts: GenerationOptions) -> tuple[str, str]:
        params_kwargs: dict[str, Any] = {
            "max_tokens": opts.max_tokens,
            "temperature": opts.temperature,
            "top_p": opts.top_p,
            "seed": opts.seed if opts.seed is not None else -1,
            "stop": list(opts.stop) or None,
        }
        try:
            vllm = _import_vllm()
            params = vllm.SamplingParams(**params_kwargs)
        except BackendUnavailable:
            # vllm is not installed but an llm-like test double was
            # injected: hand it a transparent shim. A real vllm.LLM always
            # implies an installed vllm, so the shim never meets one.
            params = _SamplingParamsShim(**params_kwargs)
        try:
            outputs = self._llm.generate([prompt], params)
        except Exception as e:
            raise BackendError(
                f"vllm in-process generate failed: {e}") from e
        if not outputs:
            raise BackendError("vllm returned no outputs")
        out = outputs[0].outputs[0]
        finish = {"stop": "stop", "length": "length"}.get(
            str(out.finish_reason), "stop")
        return out.text.strip(), finish

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self._require_capability(CAP_EMBED)
        texts = self._check_texts(texts)
        model_id = self._require_model()
        if self._llm is not None:
            raise BackendError(
                "in-process vllm embedding is not supported; use server "
                "mode against a vLLM server started with --task embed")
        data = self._server_call("/v1/embeddings",
                                 {"model": model_id, "input": texts},
                                 self.timeout_s)
        items = data.get("data", [])
        vectors = [list(map(float, item["embedding"])) for item in items]
        if len(vectors) != len(texts) or not vectors:
            raise BackendError(
                f"vllm returned {len(vectors)} embeddings for "
                f"{len(texts)} texts")
        return EmbeddingResult(vectors=vectors, dim=len(vectors[0]),
                               model=model_id)

    # -- operations --------------------------------------------------------

    def warmup(self) -> None:
        if self._model is None:
            return
        if self.embedding_mode:
            self.embed(["warmup"])
        else:
            self.generate("warmup", GenerationOptions(max_tokens=1))

    def health(self) -> dict[str, Any]:
        serving: bool | None
        if self._llm is not None:
            engine_ok, serving = True, None
        else:
            try:
                if self._transport is not None:
                    data: Any = self._transport("/v1/models", {})
                else:
                    data = _get_json(self.host + "/v1/models",
                                     _PROBE_TIMEOUT_S)
                ids = [m.get("id") for m in data.get("data", [])]
                serving = self._model is not None and \
                    self._model.path in ids
                engine_ok = True
            except Exception as e:  # noqa: BLE001 - health never raises
                return {"status": "unavailable", "runtime": self.name,
                        "available": False, "error": str(e)}
        if self._model is None:
            status = "degraded"
        elif serving is False:
            status = "degraded"
        else:
            status = "ok"
        return {"status": status, "runtime": self.name,
                "available": engine_ok,
                "model": self._model.display if self._model else None}

    def close(self) -> None:
        with self._lock:
            self._llm = None  # vLLM engines release on GC; drop the ref
