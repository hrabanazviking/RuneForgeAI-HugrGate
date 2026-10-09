"""MLX adapter boundary. Slice 157.

:class:`MLXRuntime` is the fabric's boundary with Apple's MLX stack
(``mlx-lm``): it runs on Apple silicon (Darwin/arm64) and nowhere
else. The boundary is explicit and testable:

- :meth:`MLXRuntime.platform_supported` reports whether *this*
  machine is in the supported envelope, honoring an injected
  ``platform_info`` so tests can exercise both sides;
- :meth:`available` additionally requires the ``mlx_lm`` package
  (the ``mlx`` extra), imported lazily;
- every operation raises :class:`BackendUnavailable` with a plain
  message naming the missing side (wrong platform vs. missing
  package) instead of an ``ImportError``.

Generation follows the ``mlx_lm`` calling convention
(``load(repo) -> (model, tokenizer)``,
``generate(model, tokenizer, prompt, ...)``). Tests inject the loaded
pair plus a generate callable — no Apple hardware required.
"""

from __future__ import annotations

import platform
import sys
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
    CAP_GENERATE,
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
    ModelRef,
    RuntimeInfo,
)

__all__ = [
    "SUPPORTED_PLATFORM",
    "MLXRuntime",
]

#: (system, machine) pairs MLX supports. MLX is Apple-silicon only.
SUPPORTED_PLATFORM = ("darwin", "arm64")


def _import_mlx_lm() -> Any:
    try:
        import mlx_lm
    except Exception as e:
        raise BackendUnavailable(
            "mlx_lm is not installed; install the 'mlx' extra on an "
            "Apple-silicon Mac: pip install 'hugrgate[mlx]'",
            backend="mlx") from e
    return mlx_lm


class MLXRuntime(LocalRuntime):
    """Apple MLX inference boundary.

    Parameters
    ----------
    model: :class:`ModelRef` (or ``mlx-community/...`` repo id string).
    platform_info: injected ``(system, machine)`` for tests; defaults
        to the real ``(sys.platform, platform.machine())``.
    engine: injected ``(model, tokenizer, generate_fn)`` triple for
        tests, where ``generate_fn(model, tokenizer, prompt, **kwargs)
        -> str``.
    max_tokens_default: fallback token budget (per-call options win).
    """

    name = "mlx"

    def __init__(self, model: ModelRef | str | None = None,
                 platform_info: tuple[str, str] | None = None,
                 engine: tuple[Any, Any, Any] | None = None) -> None:
        self._model = (ModelRef(runtime=self.name, path=model,
                                format="mlx")
                       if isinstance(model, str) else model)
        self._platform_info = platform_info or (
            sys.platform, platform.machine())
        self._engine = engine
        self._lock = threading.RLock()

    # -- boundary ----------------------------------------------------------

    @classmethod
    def platform_supported(cls,
                           platform_info: tuple[str, str] | None = None
                           ) -> bool:
        """Whether ``platform_info`` is inside the MLX envelope."""
        system, machine = platform_info or (sys.platform,
                                            platform.machine())
        return (system.lower(), machine.lower()) == SUPPORTED_PLATFORM

    @classmethod
    def available(cls) -> bool:
        if not cls.platform_supported():
            return False
        try:
            _import_mlx_lm()
            return True
        except BackendUnavailable:
            return False

    def _check_boundary(self) -> None:
        if not self.platform_supported(self._platform_info):
            system, machine = self._platform_info
            raise BackendUnavailable(
                f"MLX runs on Apple silicon (darwin/arm64) only; this "
                f"machine is {system}/{machine}",
                backend=self.name)

    def info(self) -> RuntimeInfo:
        try:
            ok = self.available()
        except Exception:  # noqa: BLE001 - info must never raise
            ok = False
        return RuntimeInfo(
            name=self.name,
            engine="mlx-lm",
            engine_version=self._engine_version(),
            available=ok,
            devices=("apple-silicon",),
            formats=("mlx", "hf"),
            capabilities=frozenset({CAP_GENERATE}),
            model=self._model,
            remote=False,
            notes="Apple silicon only; boundary checked per call",
        )

    def _engine_version(self) -> str:
        try:
            import mlx_lm
            return str(getattr(mlx_lm, "__version__", "unknown"))
        except Exception:  # noqa: BLE001
            return "not-installed"

    # -- lifecycle -----------------------------------------------------------

    def load(self, model: ModelRef) -> None:
        if model.format not in ("mlx", "hf", "safetensors", "unknown"):
            raise SpecError(
                f"MLX loads mlx-community/HF repos, got format "
                f"{model.format!r}")
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

    def _ensure_engine(self) -> tuple[Any, Any, Any]:
        self._check_boundary()
        with self._lock:
            if self._engine is not None:
                return self._engine
            if self._model is None:
                raise BackendUnavailable(
                    "no model loaded; call load(ModelRef(...)) first",
                    backend=self.name)
            mlx_lm = _import_mlx_lm()
            try:
                model, tokenizer = mlx_lm.load(self._model.path)
            except Exception as e:
                raise BackendUnavailable(
                    f"could not load MLX model {self._model.path!r}: {e}",
                    backend=self.name) from e

            def generate_fn(model: Any, tokenizer: Any, prompt: str,
                            **kwargs: Any) -> str:
                return str(mlx_lm.generate(model, tokenizer, prompt=prompt,
                                           **kwargs))

            self._engine = (model, tokenizer, generate_fn)
            return self._engine

    # -- inference -------------------------------------------------------------

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._require_capability(CAP_GENERATE)
        prompt = self._check_prompt(prompt)
        opts = options or GenerationOptions()
        model, tokenizer, generate_fn = self._ensure_engine()
        started = time.monotonic()
        try:
            text = generate_fn(
                model, tokenizer, prompt,
                max_tokens=opts.max_tokens,
                temp=opts.temperature,
                top_p=opts.top_p,
                seed=opts.seed,
            )
        except (BackendError, BackendUnavailable):
            raise
        except Exception as e:
            raise BackendError(f"mlx generate failed: {e}") from e
        if time.monotonic() - started > opts.timeout_s:
            raise TimeoutError(
                f"mlx generate exceeded timeout ({opts.timeout_s}s); "
                f"checked cooperatively after the blocking call",
                timeout_s=opts.timeout_s)
        return GenerationResult(
            text=str(text).strip(),
            finish_reason="stop",
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=opts.max_tokens,
            latency_s=time.monotonic() - started,
        )

    # -- operations ---------------------------------------------------------------

    def warmup(self) -> None:
        if self._engine is None and self._model is None:
            return
        self.generate("warmup", GenerationOptions(max_tokens=1))

    def health(self) -> dict[str, Any]:
        supported = self.platform_supported(self._platform_info)
        try:
            engine_ok = supported and (
                self._engine is not None or self.available())
        except Exception:  # noqa: BLE001 - health must never raise
            engine_ok = False
        if not supported:
            status = "unavailable"
        elif self._model is None:
            status = "degraded"
        else:
            status = "ok" if engine_ok else "degraded"
        return {"status": status, "runtime": self.name,
                "available": engine_ok,
                "platform": f"{self._platform_info[0]}/"
                            f"{self._platform_info[1]}",
                "platform_supported": supported,
                "model": self._model.display if self._model else None}

    def close(self) -> None:
        with self._lock:
            self._engine = None  # MLX arrays release on GC; drop refs
