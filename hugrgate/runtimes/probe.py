"""Model capability probing. Slice 162.

:func:`probe_runtime` exercises a :class:`LocalRuntime` against a
fixed battery of probes and returns a :class:`CapabilityReport` —
per-probe pass/fail/skip, latency, and a human summary. Probes never
raise: a failing probe is recorded with its error message, and probes
for unadvertised capabilities are *skipped* (not failed) so the report
distinguishes "can't" from "broken".

This is the fabric's acceptance test for a model+runtime pairing:
run it after :func:`discover_gguf_models` / :func:`scan_directory`
finds candidates, before promoting one to residency (slices 169-171).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import HugrGateError
from hugrgate.runtimes import (
    CAP_CLASSIFY,
    CAP_EMBED,
    CAP_GENERATE,
    CAP_TOKENIZE,
    GenerationOptions,
    LocalRuntime,
    ModelRef,
)

__all__ = [
    "CapabilityReport",
    "ProbeResult",
    "probe_runtime",
]

#: Probe names run by :func:`probe_runtime`, in order.
PROBE_NAMES = ("load_cycle", "generate", "embed", "classify",
               "tokenize")


@dataclass
class ProbeResult:
    """Outcome of one probe."""

    name: str
    passed: bool
    latency_s: float = 0.0
    detail: str = ""
    skipped: bool = False

    @property
    def status(self) -> str:
        if self.skipped:
            return "skipped"
        return "passed" if self.passed else "failed"


@dataclass
class CapabilityReport:
    """Full probing outcome for one runtime (+ optional model)."""

    runtime: str
    model: ModelRef | None
    results: list[ProbeResult] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results
                   if r.passed and not r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results
                   if not r.passed and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.passed > 0

    def by_name(self, name: str) -> ProbeResult | None:
        for result in self.results:
            if result.name == name:
                return result
        return None

    def summary(self) -> str:
        model = self.model.display if self.model else "no-model"
        lines = [f"{self.runtime} [{model}]: "
                 f"{self.passed} passed, {self.failed} failed, "
                 f"{self.skipped} skipped in {self.elapsed_s:.2f}s"]
        for result in self.results:
            detail = f" — {result.detail}" if result.detail else ""
            lines.append(f"  [{result.status}] {result.name} "
                         f"({result.latency_s * 1000:.1f} ms){detail}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "model": self.model.display if self.model else None,
            "elapsed_s": round(self.elapsed_s, 3),
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "ok": self.ok,
            "results": [
                {"name": r.name, "status": r.status,
                 "latency_s": round(r.latency_s, 4),
                 "detail": r.detail}
                for r in self.results
            ],
        }


def _skip(name: str, detail: str) -> ProbeResult:
    return ProbeResult(name=name, passed=False, skipped=True,
                       detail=detail)


def _run_probe(name: str, fn: Any) -> ProbeResult:
    started = time.monotonic()
    try:
        detail = fn() or ""
    except _SkipProbe:
        raise
    except Exception as e:  # noqa: BLE001 - probes never raise
        return ProbeResult(name=name, passed=False,
                           latency_s=time.monotonic() - started,
                           detail=f"{type(e).__name__}: {e}")
    return ProbeResult(name=name, passed=True,
                       latency_s=time.monotonic() - started,
                       detail=str(detail))


def probe_runtime(runtime: LocalRuntime,
                  model: ModelRef | None = None,
                  probes: tuple[str, ...] = PROBE_NAMES,
                  timeout_s: float = 60.0) -> CapabilityReport:
    """Probe ``runtime`` (optionally with ``model`` loaded first).

    Unknown probe names raise :class:`HugrGateError`; probe *failures*
    never raise — they are recorded in the report.
    """
    unknown = [p for p in probes if p not in PROBE_NAMES]
    if unknown:
        raise HugrGateError(f"unknown probes: {unknown}")
    started = time.monotonic()
    report = CapabilityReport(runtime=runtime.name, model=model)
    info = runtime.info()
    options = GenerationOptions(max_tokens=16, timeout_s=timeout_s)

    def _load_cycle() -> str:
        if model is None:
            return "no model given; lifecycle not exercised"
        runtime.load(model)
        loaded = runtime.info().model
        runtime.unload()
        if loaded is None or loaded.path != model.path:
            raise AssertionError(
                f"load() did not stick: {loaded} != {model.display}")
        return f"load/unload ok for {model.display}"

    def _generate() -> str:
        if not info.supports(CAP_GENERATE):
            raise _SkipProbe("capability not advertised")
        out = runtime.generate("The sky is", options)
        if not out.text.strip():
            raise AssertionError("empty completion")
        return (f"{len(out.text)} chars, finish={out.finish_reason}, "
                f"{out.completion_tokens} tok")

    def _embed() -> str:
        if not info.supports(CAP_EMBED):
            raise _SkipProbe("capability not advertised")
        out = runtime.embed(["hello world", "goodbye world"])
        if len(out.vectors) != 2 or out.dim < 1:
            raise AssertionError(
                f"bad embedding batch: {len(out.vectors)}x{out.dim}")
        return f"2 texts -> dim {out.dim}"

    def _classify() -> str:
        if not info.supports(CAP_CLASSIFY):
            raise _SkipProbe("capability not advertised")
        (res,) = runtime.classify(["I love this"], ["good", "bad"])
        total = sum(res.scores.values())
        if abs(total - 1.0) > 1e-6:
            raise AssertionError(f"scores sum to {total}, not 1.0")
        return f"label={res.label}"

    def _tokenize() -> str:
        if not info.supports(CAP_TOKENIZE):
            raise _SkipProbe("capability not advertised")
        ids = runtime.tokenize("hello world")
        if not ids:
            raise AssertionError("empty token list")
        return f"{len(ids)} tokens"

    handlers = {
        "load_cycle": _load_cycle,
        "generate": _generate,
        "embed": _embed,
        "classify": _classify,
        "tokenize": _tokenize,
    }
    for name in probes:
        try:
            report.results.append(_run_probe(name, handlers[name]))
        except _SkipProbe as e:
            report.results.append(_skip(name, str(e)))
    report.elapsed_s = time.monotonic() - started
    return report


class _SkipProbe(Exception):
    """Internal: a probe whose capability isn't advertised."""
