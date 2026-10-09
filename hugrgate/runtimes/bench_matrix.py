"""Local runtime benchmark matrix. Slice 174.

Measures per-operation latency (generate/embed/classify) for every
runtime in a registry and writes a JSON artifact to
``benchmarks/localrt-matrix.json``. Numbers are *measured*, never
invented:

- :func:`bench_runtime` runs ``warmup_rounds`` untimed iterations
  then ``rounds`` timed iterations per advertised capability;
- unavailable adapters are recorded as ``ok: false`` results with
  the honest error — they are not silently dropped;
- the artifact carries full provenance: config, timestamp,
  platform, and an explicit note about what was actually measured.

In CI (no engines installed) the matrix is a **synthetic baseline**:
only :class:`FakeRuntime` produces timings, and the artifact says
so. Re-run :func:`main` on a host with engines installed to produce
a real matrix — the schema is identical.

Tests for this module write artifacts to ``tmp_path`` only and must
never rewrite ``benchmarks/localrt-matrix.json``; regenerate the
real artifact with ``python -m hugrgate.runtimes.bench_matrix``
after the final test run.
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hugrgate.errors import HugrGateError, SpecError
from hugrgate.runtimes import (
    CAP_CLASSIFY,
    CAP_EMBED,
    CAP_GENERATE,
    FakeRuntime,
    GenerationOptions,
    LocalRuntime,
    RuntimeRegistry,
)
from hugrgate.runtimes.conformance import register_all_adapters

__all__ = [
    "ARTIFACT_PATH",
    "BenchConfig",
    "BenchMatrix",
    "BenchResult",
    "bench_all",
    "bench_runtime",
    "build_default_registry",
    "main",
    "write_artifact",
]

ARTIFACT_PATH = Path("benchmarks/localrt-matrix.json")


@dataclass(frozen=True)
class BenchConfig:
    """How to measure."""

    rounds: int = 10
    warmup_rounds: int = 2
    prompt: str = "The capital of Assyria was"
    max_tokens: int = 8
    classify_labels: tuple[str, ...] = ("yes", "no")

    def __post_init__(self) -> None:
        if self.rounds < 1:
            raise SpecError(f"rounds must be >= 1, got {self.rounds}")
        if self.warmup_rounds < 0:
            raise SpecError(
                f"warmup_rounds must be >= 0, got {self.warmup_rounds}")


@dataclass
class BenchResult:
    """Measured latencies for one (runtime, operation)."""

    runtime: str
    operation: str
    ok: bool
    latencies_s: list[float] = field(default_factory=list)
    error: str | None = None

    @property
    def n(self) -> int:
        return len(self.latencies_s)

    def _percentile(self, pct: float) -> float | None:
        if not self.latencies_s:
            return None
        ordered = sorted(self.latencies_s)
        idx = min(len(ordered) - 1, int(len(ordered) * pct))
        return ordered[idx]

    @property
    def p50_s(self) -> float | None:
        return self._percentile(0.50)

    @property
    def p95_s(self) -> float | None:
        return self._percentile(0.95)

    @property
    def mean_s(self) -> float | None:
        if not self.latencies_s:
            return None
        return sum(self.latencies_s) / len(self.latencies_s)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "operation": self.operation,
            "ok": self.ok,
            "n": self.n,
            "p50_s": self.p50_s,
            "p95_s": self.p95_s,
            "mean_s": self.mean_s,
            "min_s": min(self.latencies_s) if self.latencies_s else None,
            "max_s": max(self.latencies_s) if self.latencies_s else None,
            "error": self.error,
        }


def _timed(fn: Any) -> float:
    started = time.monotonic()
    fn()
    return time.monotonic() - started


def bench_runtime(runtime: LocalRuntime,
                  config: BenchConfig) -> list[BenchResult]:
    """Benchmark each advertised capability of one runtime.

    Never raises: failures become ``ok: false`` results.
    """
    try:
        caps = runtime.info().capabilities
    except Exception as e:  # noqa: BLE001 - recorded, not raised
        return [BenchResult(runtime=runtime.name, operation="info",
                            ok=False,
                            error=f"{type(e).__name__}: {e}")]
    results: list[BenchResult] = []
    operations: list[tuple[str, Any]] = []
    if CAP_GENERATE in caps:
        def _gen() -> None:
            runtime.generate(config.prompt,
                             GenerationOptions(
                                 max_tokens=config.max_tokens))
        operations.append(("generate", _gen))
    if CAP_EMBED in caps:
        def _emb() -> None:
            runtime.embed([config.prompt])
        operations.append(("embed", _emb))
    if CAP_CLASSIFY in caps:
        def _cls() -> None:
            runtime.classify([config.prompt],
                             list(config.classify_labels))
        operations.append(("classify", _cls))

    for op_name, op_fn in operations:
        try:
            for _ in range(config.warmup_rounds):
                op_fn()
            latencies = [_timed(op_fn) for _ in range(config.rounds)]
            results.append(BenchResult(
                runtime=runtime.name, operation=op_name, ok=True,
                latencies_s=latencies))
        except HugrGateError as e:
            results.append(BenchResult(
                runtime=runtime.name, operation=op_name, ok=False,
                error=f"{type(e).__name__}: {e}"))
        except Exception as e:  # noqa: BLE001 - foreign errors recorded
            results.append(BenchResult(
                runtime=runtime.name, operation=op_name, ok=False,
                error=f"UNEXPECTED {type(e).__name__}: {e}"))
    return results


@dataclass
class BenchMatrix:
    """All results plus provenance."""

    results: list[BenchResult] = field(default_factory=list)
    config: BenchConfig = field(default_factory=BenchConfig)
    note: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(
        timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "hugrgate.localrt-matrix/1",
            "timestamp": self.timestamp,
            "config": {
                "rounds": self.config.rounds,
                "warmup_rounds": self.config.warmup_rounds,
                "prompt": self.config.prompt,
                "max_tokens": self.config.max_tokens,
            },
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "git_sha": _git_sha(),
            },
            "note": self.note,
            "results": [r.to_dict() for r in self.results],
        }


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001 - provenance is best effort
        return None


def bench_all(registry: RuntimeRegistry,
              config: BenchConfig) -> BenchMatrix:
    """Benchmark every runtime in ``registry``."""
    matrix = BenchMatrix(config=config)
    for name in registry.list():
        runtime = registry.get(name)
        if runtime is not None:
            matrix.results.extend(bench_runtime(runtime, config))
    return matrix


def write_artifact(path: str | Path, matrix: BenchMatrix) -> Path:
    """Write the matrix JSON artifact (creating parent dirs)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(matrix.to_dict(), indent=2) + "\n",
                    encoding="utf-8")
    return path


def build_default_registry() -> tuple[RuntimeRegistry, str]:
    """Registry for the artifact: synthetic fakes + all adapters.

    Returns ``(registry, note)`` describing what was measured.
    """
    registry = RuntimeRegistry()
    fast = FakeRuntime()
    fast.name = "fake"
    registry.register(fast)
    slow = FakeRuntime(latency_s=0.05)
    slow.name = "fake-delayed-50ms"
    registry.register(slow)
    register_all_adapters(registry)
    note = (
        "Synthetic baseline: only the FakeRuntime rows contain measured "
        "timings (in-process, deterministic). All engine adapters report "
        "ok:false because no engines are installed in this environment. "
        "Re-run `python -m hugrgate.runtimes.bench_matrix` on a host "
        "with engines installed for a real matrix; the schema is "
        "identical.")
    return registry, note


def main() -> Path:
    """Generate ``benchmarks/localrt-matrix.json`` with full rounds."""
    config = BenchConfig()  # full rounds; tests use small configs
    registry, note = build_default_registry()
    matrix = bench_all(registry, config)
    matrix.note = note
    path = write_artifact(ARTIFACT_PATH, matrix)
    ok_rows = sum(1 for r in matrix.results if r.ok)
    print(f"wrote {path} "
          f"({len(matrix.results)} rows, {ok_rows} ok)")
    return path


if __name__ == "__main__":
    main()
