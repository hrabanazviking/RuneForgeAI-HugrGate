"""Ollama-compatible runtime adapter. Slice 153.

:class:`OllamaRuntime` drives an Ollama server (or any server speaking
the Ollama HTTP API) through the v2 :class:`LocalRuntime` contract. It
uses only the standard library (``urllib``) — Ollama is a *server*, not
a pip package, so there is no optional import to gate on. Availability
is probed with a short ``GET /api/tags`` against the configured host.

Model lifecycle note: :meth:`load` selects a model *tag*
(``"llama3.1:8b"``); it does not pull weights. Pulling gigabytes as a
side effect of ``load()`` would be hostile, so a 404 from the server
surfaces as a :class:`BackendError` telling the operator to run
``ollama pull <tag>`` first. Tests inject a fake transport callable —
no server required.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from hugrgate.errors import (
    BackendError,
    BackendUnavailable,
    SpecError,
)
from hugrgate.errors import (
    TimeoutError as HugrTimeoutError,
)
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
    "DEFAULT_HOST",
    "OllamaRuntime",
    "TransportFn",
]

#: Default Ollama server address.
DEFAULT_HOST = "http://localhost:11434"

#: How long the availability probe may take.
_PROBE_TIMEOUT_S = 2.0

#: ``(method, path, payload) -> decoded JSON response``.
TransportFn = Callable[[str, str, "dict[str, Any] | None"], Any]


def _default_transport(host: str, timeout_s: float) -> TransportFn:
    def transport(method: str, path: str,
                  payload: dict[str, Any] | None = None) -> Any:
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            host.rstrip("/") + path, data=data, headers=headers,
            method=method.upper())
        try:
            with urllib.request.urlopen(request,
                                        timeout=timeout_s) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            raise _http_error(e) from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise BackendUnavailable(
                f"ollama server not reachable at {host}: {e}",
                backend="ollama") from e

    return transport


def _http_error(e: urllib.error.HTTPError) -> BackendError:
    try:
        detail = json.loads(e.read().decode("utf-8")).get("error", "")
    except Exception:  # noqa: BLE001 - best-effort detail extraction
        detail = ""
    if e.code == 404:
        return BackendError(
            f"ollama model not found on server: {detail or e}. "
            f"Run `ollama pull <tag>` first.")
    return BackendError(f"ollama server error {e.code}: {detail or e}")


class OllamaRuntime(LocalRuntime):
    """Inference through an Ollama-compatible HTTP server.

    Parameters
    ----------
    model: model tag (``"llama3.1:8b"``) or :class:`ModelRef`.
    host: server base URL, e.g. ``"http://localhost:11434"``.
    timeout_s: per-request timeout.
    transport: injected ``(method, path, payload) -> response`` callable
        for tests.
    """

    name = "ollama"

    _CAPABILITIES = frozenset({CAP_GENERATE, CAP_EMBED})

    def __init__(self, model: ModelRef | str | None = None,
                 host: str = DEFAULT_HOST, timeout_s: float = 120.0,
                 transport: Any = None) -> None:
        if not host or not host.strip():
            raise SpecError("host must be a non-empty URL")
        if timeout_s <= 0:
            raise SpecError(f"timeout_s must be > 0, got {timeout_s}")
        self._model = (ModelRef(runtime=self.name, path=model,
                                format="ollama")
                       if isinstance(model, str) else model)
        self.host = host.rstrip("/")
        self.timeout_s = timeout_s
        self._injected = transport is not None
        self._transport: TransportFn = (
            transport if transport is not None
            else _default_transport(host, timeout_s))
        self._lock = threading.RLock()

    def _call(self, method: str, path: str,
              payload: dict[str, Any] | None = None,
              timeout_s: float | None = None) -> Any:
        """One API call, honoring a per-call timeout for the default
        transport; injected test transports are called as-is."""
        transport = self._transport
        if not self._injected and timeout_s is not None:
            transport = _default_transport(self.host, timeout_s)
        try:
            return transport(method, path, payload)
        except TimeoutError as e:
            raise HugrTimeoutError(
                f"ollama request timed out after {timeout_s}s",
                timeout_s=timeout_s or self.timeout_s) from e

    def _require_capability(self, capability: str) -> None:
        # Overridden: the base implementation calls info(), which probes
        # the server — too expensive per inference. Capabilities here are
        # static for the Ollama API surface.
        if capability not in self._CAPABILITIES:
            raise BackendError(
                f"runtime {self.name!r} does not advertise "
                f"capability {capability!r}")

    # -- availability ---------------------------------------------------

    @classmethod
    def available(cls) -> bool:
        try:
            _default_transport(DEFAULT_HOST, _PROBE_TIMEOUT_S)(
                "GET", "/api/tags", None)
            return True
        except Exception:  # noqa: BLE001 - any failure means unavailable
            return False

    def info(self) -> RuntimeInfo:
        try:
            ok = self.available()
        except Exception:  # noqa: BLE001 - info must never raise
            ok = False
        return RuntimeInfo(
            name=self.name,
            engine="ollama",
            engine_version=self._server_version(),
            available=ok,
            devices=("cpu", "cuda", "metal"),
            formats=("ollama",),
            capabilities=self._CAPABILITIES,
            model=self._model,
            remote=False,
            notes="HTTP to an Ollama-compatible server; stdlib only",
        )

    def _server_version(self) -> str:
        try:
            data = self._call("GET", "/api/version",
                              timeout_s=_PROBE_TIMEOUT_S)
            return str(data.get("version", "unknown"))
        except Exception:  # noqa: BLE001 - best effort
            return "unknown"

    # -- lifecycle --------------------------------------------------------

    def load(self, model: ModelRef) -> None:
        if model.runtime not in ("ollama", ""):
            raise SpecError(
                f"ollama runtime cannot load a {model.runtime!r} model")
        with self._lock:
            self._model = ModelRef(runtime=self.name, path=model.path,
                                   format="ollama", alias=model.alias,
                                   extra=dict(model.extra))

    def unload(self) -> None:
        with self._lock:
            self._model = None

    def _require_model(self) -> str:
        if self._model is None:
            raise BackendUnavailable(
                "no model selected; call load(ModelRef(...)) with an "
                "ollama tag first", backend=self.name)
        return self._model.path

    # -- inference --------------------------------------------------------

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._require_capability(CAP_GENERATE)
        prompt = self._check_prompt(prompt)
        opts = options or GenerationOptions()
        tag = self._require_model()
        payload: dict[str, Any] = {
            "model": tag,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": opts.max_tokens,
                "temperature": opts.temperature,
                "top_p": opts.top_p,
                "seed": opts.seed if opts.seed is not None else -1,
            },
        }
        if opts.stop:
            payload["options"]["stop"] = list(opts.stop)
        started = time.monotonic()
        data = self._call("POST", "/api/generate", payload,
                          timeout_s=opts.timeout_s)
        done_reason = str(data.get("done_reason", "stop"))
        finish = {"stop": "stop", "length": "length"}.get(done_reason,
                                                         "stop")
        return GenerationResult(
            text=str(data.get("response", "")).strip(),
            finish_reason=finish,
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
            latency_s=time.monotonic() - started,
        )

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self._require_capability(CAP_EMBED)
        texts = self._check_texts(texts)
        tag = self._require_model()
        data = self._call("POST", "/api/embed",
                          {"model": tag, "input": texts},
                          timeout_s=self.timeout_s)
        vectors = [list(map(float, v)) for v in data.get("embeddings", [])]
        if len(vectors) != len(texts):
            raise BackendError(
                f"ollama returned {len(vectors)} embeddings for "
                f"{len(texts)} texts")
        if not vectors:
            raise BackendError("ollama returned no embeddings")
        return EmbeddingResult(vectors=vectors, dim=len(vectors[0]),
                               model=tag)

    # -- operations --------------------------------------------------------

    def list_models(self) -> list[str]:
        """Tags known to the server (from ``GET /api/tags``)."""
        data = self._call("GET", "/api/tags", timeout_s=_PROBE_TIMEOUT_S)
        models = data.get("models", [])
        return [str(m.get("name", m)) for m in models]

    def warmup(self) -> None:
        if self._model is None:
            return
        self.generate("warmup", GenerationOptions(max_tokens=1))

    def health(self) -> dict[str, Any]:
        try:
            tags = self.list_models()
        except Exception as e:  # noqa: BLE001 - health must never raise
            return {"status": "unavailable", "runtime": self.name,
                    "available": False, "error": str(e)}
        if self._model is None:
            status = "degraded"
        elif self._model.path in tags:
            status = "ok"
        else:
            status = "degraded"  # tag not pulled on the server
        return {"status": status, "runtime": self.name, "available": True,
                "model": self._model.display if self._model else None,
                "server_models": len(tags)}

    def close(self) -> None:
        pass  # stateless HTTP — nothing to release
