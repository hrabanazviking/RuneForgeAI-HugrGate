"""Local runtime conformance suite. Slice 173.

Runs every local runtime adapter (slices 152-159) against the v2
contract from slice 151, using injected fakes — no engines, models,
or network required:

- **contract checks** (all 8 adapters): ``available()`` returns a
  bool without raising; ``info()`` is well-formed (known
  capabilities, tuple devices/formats); ``health()`` never raises
  with a valid status; ``unload()``/``warmup()``/``close()`` hooks
  are safe; missing engines surface as :class:`HugrGateError`
  (``BackendUnavailable``/``BackendError``), never a foreign
  exception; ``privacy()`` reports ``remote=False``; adapter names
  are unique in the registry;
- **happy-path checks** (adapters with simple fakes): llama.cpp,
  Ollama and transformers generate, ONNX embed — proving the
  adapters' inference paths work when an engine *is* present.

:func:`run_conformance` returns one :class:`ConformanceReport` per
adapter. The pytest module ``tests/test_localrt_173_conformance.py``
runs the suite as part of the normal test run, so contract drift
fails CI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import HugrGateError
from hugrgate.runtimes import (
    CAP_CLASSIFY,
    CAP_EMBED,
    CAP_GENERATE,
    CAP_GRAMMAR,
    CAP_JSON_SCHEMA,
    CAP_STREAM,
    CAP_TOKENIZE,
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
    ModelRef,
    RuntimeRegistry,
)
from hugrgate.runtimes.llama_cpp import LlamaCppRuntime
from hugrgate.runtimes.mlx import MLXRuntime
from hugrgate.runtimes.ollama import OllamaRuntime
from hugrgate.runtimes.onnx import OnnxRuntime
from hugrgate.runtimes.openvino import OpenVINORuntime
from hugrgate.runtimes.tensorrt import TensorRTRuntime
from hugrgate.runtimes.transformers_rt import TransformersRuntime
from hugrgate.runtimes.vllm import VLLMRuntime

__all__ = [
    "ADAPTER_CLASSES",
    "HAPPY_PATHS",
    "HAPPY_PROBES",
    "ConformanceCheck",
    "ConformanceReport",
    "check_adapter",
    "conformance_summary",
    "register_all_adapters",
    "run_conformance",
]

KNOWN_CAPABILITIES = frozenset({
    CAP_GENERATE, CAP_EMBED, CAP_CLASSIFY, CAP_TOKENIZE,
    CAP_GRAMMAR, CAP_JSON_SCHEMA, CAP_STREAM,
})

HEALTH_STATUSES = frozenset({"ok", "degraded", "unavailable"})

ADAPTER_CLASSES: tuple[type[LocalRuntime], ...] = (
    LlamaCppRuntime,
    OllamaRuntime,
    OnnxRuntime,
    TransformersRuntime,
    VLLMRuntime,
    MLXRuntime,
    OpenVINORuntime,
    TensorRTRuntime,
)


@dataclass
class ConformanceCheck:
    """One contract assertion."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class ConformanceReport:
    """All checks for one adapter class."""

    adapter: str
    runtime_name: str
    available: bool
    checks: list[ConformanceCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    @property
    def failed(self) -> list[ConformanceCheck]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "runtime_name": self.runtime_name,
            "available": self.available,
            "passed": self.passed,
            "checks": [{"name": c.name, "passed": c.passed,
                        "detail": c.detail} for c in self.checks],
        }


def _check(name: str, fn: Callable[[], str | None],
           report: ConformanceReport) -> None:
    """Run one check; record pass/fail, never raise."""
    try:
        detail = fn() or ""
        report.checks.append(ConformanceCheck(name, True, detail))
    except Exception as e:  # noqa: BLE001 - conformance records, not raises
        report.checks.append(ConformanceCheck(
            name, False, f"{type(e).__name__}: {e}"))


def check_adapter(cls: type[LocalRuntime],
                  happy_path: Callable[[], LocalRuntime] | None = None,
                  happy_probe: Callable[[LocalRuntime], str] | None = None
                  ) -> ConformanceReport:
    """Run the contract checks against one adapter class."""
    report = ConformanceReport(adapter=cls.__name__, runtime_name="?",
                               available=False)

    def _available() -> str | None:
        value = cls.available()
        if not isinstance(value, bool):
            raise AssertionError(
                f"available() returned {value!r}, not bool")
        report.available = value
        return f"available={value}"

    _check("available-bool", _available, report)

    try:
        # All adapters accept ``model=None``; the base ABC does not
        # declare it, hence the ignore.
        runtime = cls(model=None)  # type: ignore[call-arg]
    except Exception as e:  # noqa: BLE001 - record, keep going
        report.checks.append(ConformanceCheck(
            "construct-default", False, f"{type(e).__name__}: {e}"))
        return report
    report.checks.append(ConformanceCheck("construct-default", True, ""))
    report.runtime_name = runtime.name

    def _info() -> str | None:
        info = runtime.info()
        if not info.name or not isinstance(info.name, str):
            raise AssertionError(f"bad info().name: {info.name!r}")
        unknown = set(info.capabilities) - KNOWN_CAPABILITIES
        if unknown:
            raise AssertionError(f"unknown capabilities: {sorted(unknown)}")
        if not isinstance(info.devices, tuple):
            raise AssertionError("info().devices must be a tuple")
        if not isinstance(info.formats, tuple):
            raise AssertionError("info().formats must be a tuple")
        return (f"name={info.name} caps={sorted(info.capabilities)}")

    _check("info-wellformed", _info, report)

    def _health() -> str | None:
        health = runtime.health()
        status = health.get("status")
        if status not in HEALTH_STATUSES:
            raise AssertionError(f"bad health status: {status!r}")
        return f"status={status}"

    _check("health-safe", _health, report)

    def _hooks() -> str | None:
        runtime.unload()
        runtime.warmup()
        runtime.close()
        return ""

    _check("hooks-safe", _hooks, report)

    def _honest_errors() -> str | None:
        # Missing engines (or missing models) must surface as
        # HugrGateError, never ImportError / foreign exceptions.
        probed: list[str] = []
        try:
            runtime.generate("conformance probe",
                             GenerationOptions(max_tokens=1))
            probed.append("generate=ok")
        except HugrGateError as e:
            probed.append(f"generate={type(e).__name__}")
        try:
            runtime.embed(["conformance probe"])
            probed.append("embed=ok")
        except HugrGateError as e:
            probed.append(f"embed={type(e).__name__}")
        try:
            runtime.classify(["conformance probe"], ["yes", "no"])
            probed.append("classify=ok")
        except HugrGateError as e:
            probed.append(f"classify={type(e).__name__}")
        return "; ".join(probed)

    _check("errors-honest", _honest_errors, report)

    def _privacy() -> str | None:
        privacy = runtime.privacy()
        if privacy.get("remote") is not False:
            raise AssertionError(
                f"local runtime must report remote=False: {privacy!r}")
        return ""

    _check("privacy-local", _privacy, report)

    if happy_path is not None:
        probe = happy_probe or _generate_probe

        def _happy() -> str | None:
            rt = happy_path()
            return probe(rt)

        _check("happy-path", _happy, report)

    return report


def _generate_probe(rt: LocalRuntime) -> str:
    result = rt.generate(
        "conformance probe", GenerationOptions(max_tokens=4))
    if not isinstance(result, GenerationResult):
        raise AssertionError(
            f"expected GenerationResult, got {type(result).__name__}")
    if not result.text:
        raise AssertionError("empty completion text")
    return f"text={result.text[:24]!r}"


# -- happy-path fakes (one per covered adapter) -------------------------------

class _FakeLlama:
    """Duck-types llama_cpp.Llama for generate."""

    def __call__(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [{"text": "conformance ok",
                         "logprobs": {"token_logprobs": [-0.1]}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2},
        }

    def close(self) -> None:
        pass


def _llama_cpp_happy() -> LocalRuntime:
    return LlamaCppRuntime(
        model=ModelRef(runtime="llama-cpp", path="m.gguf", format="gguf"),
        llama=_FakeLlama())


class _FakeTransport:
    """Duck-types the Ollama HTTP transport."""

    def __call__(self, method: str, path: str,
                 payload: dict | None = None) -> Any:
        if (method.upper(), path) == ("POST", "/api/generate"):
            return {"response": "conformance ok", "done_reason": "stop",
                    "prompt_eval_count": 2, "eval_count": 2}
        raise AssertionError(f"unexpected call {(method, path)}")


def _ollama_happy() -> LocalRuntime:
    return OllamaRuntime(model="tiny", transport=_FakeTransport())


class _FakeIONode:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeOnnxSession:
    """Duck-types onnxruntime.InferenceSession for classify."""

    def get_inputs(self) -> list[_FakeIONode]:
        return [_FakeIONode("input_ids")]

    def get_outputs(self) -> list[_FakeIONode]:
        return [_FakeIONode("logits")]

    def run(self, output_names: list[str], feed: dict) -> list:
        return [[[2.0, 1.0, 0.5]]]


def _onnx_happy() -> LocalRuntime:
    return OnnxRuntime(
        model=ModelRef(runtime="onnx", path="m.onnx", format="onnx"),
        encode_fn=lambda texts: {"input_ids": [[1, 2]] * len(texts)},
        session=_FakeOnnxSession())


def _embed_probe(rt: LocalRuntime) -> str:
    result = rt.embed(["conformance probe"])
    if not result.vectors or not result.vectors[0]:
        raise AssertionError("empty embedding vectors")
    return f"dim={result.dim}"


class _FakePipe:
    """Duck-types a transformers text-generation pipeline."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return [{"generated_text": str(args[0]) + " conformance ok"}]


def _transformers_happy() -> LocalRuntime:
    return TransformersRuntime(
        model=ModelRef(runtime="transformers", path="org/tiny",
                       format="hf"),
        task="text-generation", pipe=_FakePipe())


HAPPY_PATHS: dict[str, Callable[[], LocalRuntime]] = {
    "LlamaCppRuntime": _llama_cpp_happy,
    "OllamaRuntime": _ollama_happy,
    "OnnxRuntime": _onnx_happy,
    "TransformersRuntime": _transformers_happy,
}

HAPPY_PROBES: dict[str, Callable[[LocalRuntime], str]] = {
    "OnnxRuntime": _embed_probe,
}


def run_conformance() -> list[ConformanceReport]:
    """Run the suite against every adapter."""
    reports = [check_adapter(cls, HAPPY_PATHS.get(cls.__name__),
                             HAPPY_PROBES.get(cls.__name__))
               for cls in ADAPTER_CLASSES]
    # Cross-adapter: runtime names must be unique.
    names = [r.runtime_name for r in reports]
    dupes = sorted({n for n in names if names.count(n) > 1})
    for report in reports:
        if dupes and report.runtime_name in dupes:
            report.checks.append(ConformanceCheck(
                "name-unique", False, f"duplicate names: {dupes}"))
        else:
            report.checks.append(ConformanceCheck("name-unique", True, ""))
    return reports


def conformance_summary(
        reports: list[ConformanceReport]) -> dict[str, Any]:
    """Aggregate counts over conformance reports."""
    total = sum(len(r.checks) for r in reports)
    failed = sum(len(r.failed) for r in reports)
    return {
        "adapters": len(reports),
        "adapters_passed": sum(1 for r in reports if r.passed),
        "checks": total,
        "checks_passed": total - failed,
        "checks_failed": failed,
        "failed": [
            {"adapter": r.adapter, "check": c.name, "detail": c.detail}
            for r in reports for c in r.failed
        ],
    }


def register_all_adapters(registry: RuntimeRegistry | None = None
                          ) -> RuntimeRegistry:
    """Register one default instance of every adapter.

    Useful for smoke tests and the benchmark matrix (174).
    """
    registry = registry or RuntimeRegistry()
    for cls in ADAPTER_CLASSES:
        try:
            # See check_adapter: all adapters accept ``model=None``.
            registry.register(cls(model=None))  # type: ignore[call-arg]
        except Exception:  # noqa: BLE001 - best effort
            continue
    return registry
