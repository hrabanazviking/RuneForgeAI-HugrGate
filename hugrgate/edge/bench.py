"""Edge benchmark harness and platform suites. Slices 196-198.

:class:`EdgeBenchmark` measures named cases (warmup + timed iterations,
mean/p50/p99) and persists a JSON artifact carrying the full context
needed to interpret it: schema version, timestamp, host platform, and
— critically — whether the numbers were measured on real edge silicon
or a surrogate host. :meth:`compare` diffs an artifact against a
baseline artifact and flags regressions beyond a threshold, so CI can
say "slower than the Pi 5 baseline" instead of "slower than vibes".

:func:`edge_bench_suite` wires representative Campaign VIII workloads
(decision latency, INT8/INT4 paths, storage round-trip); slices 197
and 198 add the Pi and Jetson suites, which bind the harness to board
baselines and mark surrogate-host runs explicitly.
"""

from __future__ import annotations

import json
import statistics
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hugrgate.edge.platform import (
    EdgeBaseline,
    PlatformInfo,
    PlatformProbe,
)
from hugrgate.errors import BenchmarkError

try:
    import numpy as np
except ImportError:  # optional dependency — the suite needs it
    np = None  # type: ignore[assignment]

__all__ = [
    "ARTIFACT_SCHEMA",
    "BenchmarkCase",
    "BenchmarkError",
    "BenchmarkResult",
    "EdgeBenchmark",
    "compare_artifacts",
    "edge_bench_suite",
    "jetson_baseline",
    "jetson_bench_suite",
    "load_artifact",
    "pi_bench_suite",
]

#: Artifact schema version. Bump when the JSON layout changes.
ARTIFACT_SCHEMA = "edge-bench/1"


@dataclass
class BenchmarkCase:
    """One measurable workload."""

    name: str
    fn: Callable[[], Any]
    iterations: int = 100
    warmup: int = 10

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise BenchmarkError("case name must be non-empty")
        if self.iterations < 1:
            raise BenchmarkError("iterations must be >= 1")
        if self.warmup < 0:
            raise BenchmarkError("warmup must be >= 0")


@dataclass
class BenchmarkResult:
    """Measured timings for one case."""

    name: str
    iterations: int
    mean_s: float
    p50_s: float
    p99_s: float
    min_s: float
    max_s: float

    @property
    def ops_per_s(self) -> float:
        return 1.0 / self.mean_s if self.mean_s > 0 else float("inf")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "iterations": self.iterations,
                "mean_s": self.mean_s, "p50_s": self.p50_s,
                "p99_s": self.p99_s, "min_s": self.min_s,
                "max_s": self.max_s,
                "ops_per_s": self.ops_per_s}


def _percentile(sorted_xs: list[float], pct: float) -> float:
    if not sorted_xs:
        raise BenchmarkError("no samples")
    rank = (len(sorted_xs) - 1) * pct / 100.0
    lo, hi = int(rank), min(int(rank) + 1, len(sorted_xs) - 1)
    frac = rank - lo
    return sorted_xs[lo] * (1 - frac) + sorted_xs[hi] * frac


class EdgeBenchmark:
    """Reproducible measurement harness with baseline comparison."""

    def __init__(self, name: str,
                 platform: PlatformInfo | None = None,
                 baseline_board: EdgeBaseline | None = None,
                 timer: Callable[[], float] | None = None):
        if not name.strip():
            raise BenchmarkError("benchmark name must be non-empty")
        self.name = name
        self.platform = platform or PlatformProbe().probe()
        self.baseline_board = baseline_board
        self._timer = timer or time.perf_counter
        self._lock = threading.RLock()
        self._cases: list[BenchmarkCase] = []
        self._results: dict[str, BenchmarkResult] = {}

    # -- definition ---------------------------------------------------------------

    def add_case(self, case: BenchmarkCase) -> EdgeBenchmark:
        with self._lock:
            if any(c.name == case.name for c in self._cases):
                raise BenchmarkError(
                    f"duplicate benchmark case {case.name!r}")
            self._cases.append(case)
        return self

    def add(self, name: str, fn: Callable[[], Any], *,
            iterations: int = 100, warmup: int = 10) -> EdgeBenchmark:
        return self.add_case(BenchmarkCase(name, fn, iterations, warmup))

    # -- execution --------------------------------------------------------------------

    def run(self) -> dict[str, BenchmarkResult]:
        """Run every case; returns results keyed by case name."""
        results: dict[str, BenchmarkResult] = {}
        with self._lock:
            cases = list(self._cases)
        for case in cases:
            for _ in range(case.warmup):
                case.fn()
            samples = []
            for _ in range(case.iterations):
                start = self._timer()
                case.fn()
                samples.append(self._timer() - start)
            samples.sort()
            results[case.name] = BenchmarkResult(
                name=case.name, iterations=case.iterations,
                mean_s=statistics.fmean(samples),
                p50_s=_percentile(samples, 50),
                p99_s=_percentile(samples, 99),
                min_s=samples[0], max_s=samples[-1])
        with self._lock:
            self._results = results
        return dict(results)

    # -- artifacts ------------------------------------------------------------------------

    def _hardware_note(self) -> str:
        board = self.baseline_board.board if self.baseline_board else None
        if board and self.platform.arch.lower() in ("aarch64", "arm64"):
            return (f"measured on {self.platform.arch}; target board "
                    f"{board} — treat as same-arch reference only")
        if board:
            return (f"SURROGATE HOST ({self.platform.arch}): numbers are "
                    f"not {board} measurements; NEEDS_HARDWARE_VALIDATION "
                    f"on-device")
        return f"measured on {self.platform.arch}; no target board bound"

    def artifact(self) -> dict[str, Any]:
        """The reproducible measurement artifact (JSON-serializable)."""
        with self._lock:
            results = dict(self._results)
        if not results:
            raise BenchmarkError("no results: run() the benchmark first")
        return {
            "schema": ARTIFACT_SCHEMA,
            "name": self.name,
            "timestamp": time.time(),
            "platform": self.platform.to_dict(),
            "baseline_board": (self.baseline_board.to_dict()
                               if self.baseline_board else None),
            "hardware_note": self._hardware_note(),
            "cases": {n: r.to_dict() for n, r in results.items()},
        }

    def save(self, path: str | Path) -> Path:
        """Write the artifact JSON to ``path`` (creates parents)."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.artifact(), indent=2) + "\n",
                          encoding="utf-8")
        return target

    # -- introspection -----------------------------------------------------------------------

    def results(self) -> Mapping[str, BenchmarkResult]:
        with self._lock:
            return dict(self._results)


def load_artifact(path: str | Path) -> dict[str, Any]:
    """Load and validate a benchmark artifact."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BenchmarkError(f"cannot load benchmark artifact: {e}") from e
    if not isinstance(data, dict) or data.get("schema") != ARTIFACT_SCHEMA:
        raise BenchmarkError(
            f"unsupported artifact schema: {data.get('schema')!r}")
    if not isinstance(data.get("cases"), dict) or not data["cases"]:
        raise BenchmarkError("artifact has no cases")
    return data


def compare_artifacts(current: dict[str, Any], baseline: dict[str, Any],
                      *, threshold: float = 0.10,
                      metric: str = "mean_s") -> dict[str, Any]:
    """Diff two artifacts case by case.

    Returns per-case ``{ratio, delta_pct, regressed}`` where
    ``ratio = current / baseline`` and ``regressed`` is True when the
    slowdown exceeds ``threshold``. Cases missing from either side are
    reported, never silently dropped.
    """
    if threshold < 0:
        raise BenchmarkError("threshold must be >= 0")
    cur_cases = current.get("cases", {})
    base_cases = baseline.get("cases", {})
    comparison: dict[str, Any] = {}
    for name in sorted(set(cur_cases) | set(base_cases)):
        if name not in cur_cases:
            comparison[name] = {"status": "missing-in-current"}
            continue
        if name not in base_cases:
            comparison[name] = {"status": "missing-in-baseline"}
            continue
        try:
            cur_v = float(cur_cases[name][metric])
            base_v = float(base_cases[name][metric])
        except (KeyError, TypeError, ValueError):
            comparison[name] = {"status": f"bad-metric-{metric}"}
            continue
        if base_v <= 0 or cur_v < 0:
            comparison[name] = {"status": "non-positive-sample"}
            continue
        ratio = cur_v / base_v
        comparison[name] = {
            "status": "compared",
            "ratio": ratio,
            "delta_pct": (ratio - 1.0) * 100.0,
            "regressed": ratio > 1.0 + threshold,
            "metric": metric,
        }
    regressed = [n for n, c in comparison.items()
                 if c.get("regressed")]
    return {"threshold": threshold, "metric": metric,
            "cases": comparison, "regressed": regressed,
            "passed": not regressed}


# --- representative workload suite ----------------------------------------------------------

def edge_bench_suite(name: str = "edge-suite",
                     baseline_board: EdgeBaseline | None = None,
                     iterations: int = 200) -> EdgeBenchmark:
    """Build the standard Campaign VIII workload suite.

    Cases (all local, all offline):
    - ``decide/rules``: HugrGate decide() through the rules backend;
    - ``quant/int8-matvec``: simulated INT8 inference op;
    - ``quant/int4-roundtrip``: INT4 pack/unpack;
    - ``storage/put-flush``: wear-aware store write cycle;
    - ``telemetry/record``: telemetry event recording.
    """
    import tempfile

    import hugrgate.edge.quant as _quant
    from hugrgate.backends.rules import Rule, RuleBackend
    from hugrgate.core import HugrGate
    from hugrgate.edge.storage import WearAwareStore
    from hugrgate.edge.telemetry import TelemetryLite
    from hugrgate.policy import DecisionPolicy
    from hugrgate.spec import DecisionSpec

    if np is None:
        raise BenchmarkError(
            "the edge benchmark suite requires numpy; install the "
            "'bench' extra: pip install 'hugrgate[bench]'")

    bench = EdgeBenchmark(name, baseline_board=baseline_board)

    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy()
    gate = HugrGate()
    gate.register(RuleBackend(
        rules=[Rule(condition={"field": "x", "eq": 1}, then="a"),
               Rule.from_dict({"default": "b"})],
        name="bench-rules"))

    def decide_rules() -> None:
        gate.decide({"x": 1}, spec, policy)

    bench.add("decide/rules", decide_rules, iterations=iterations)

    rng_w = np.random.default_rng(196)
    w_mat = rng_w.normal(0, 0.5, size=(32, 64))
    x_vec = rng_w.normal(0, 1, size=64)
    w_qt = _quant.QuantizedTensor.from_weights(w_mat, axis=0)

    def int8_matvec() -> None:
        _quant.int8_matvec(w_qt, x_vec)

    bench.add("quant/int8-matvec", int8_matvec, iterations=iterations)

    adapter = _quant.Int4Adapter(group_size=32)
    w4 = rng_w.normal(0, 1, size=(4, 64))

    def int4_roundtrip() -> None:
        adapter.unpack(adapter.pack(w4))

    bench.add("quant/int4-roundtrip", int4_roundtrip, iterations=iterations)

    tmpdir = tempfile.mkdtemp(prefix="edge-bench-")
    store = WearAwareStore.open(tmpdir, write_budget_bytes=1 << 30)
    payload = b"x" * 1024

    def storage_cycle() -> None:
        store.put("k", payload)
        store.flush()

    bench.add("storage/put-flush", storage_cycle, iterations=iterations)

    tel = TelemetryLite()

    def telemetry_record() -> None:
        tel.record("bench", 1.0)

    bench.add("telemetry/record", telemetry_record, iterations=iterations)
    return bench


def pi_bench_suite(board_label: str = "Raspberry Pi 5",
                   iterations: int = 200) -> EdgeBenchmark:
    """Slice 197: Pi-bound benchmark suite.

    The standard edge suite bound to a Pi board baseline, plus two
    Pi-relevant cases: ``platform/audit`` (ARM64 audit cost — paid on
    every bootstrap) and ``memory/refresh`` (mode-derivation cost).
    On non-ARM64 hosts the artifact is explicitly marked SURROGATE
    HOST; the numbers calibrate the harness, not the board.
    """
    from hugrgate.edge.memory import MemoryManager
    from hugrgate.edge.platform import PlatformProbe, audit_arm64, pi_baseline

    baseline = pi_baseline(board_label)
    bench = edge_bench_suite(
        name=f"pi-suite-{baseline.board.lower().replace(' ', '-')}",
        baseline_board=baseline, iterations=iterations)

    probe = PlatformProbe()
    info = probe.probe()

    def platform_audit() -> None:
        audit_arm64(info)

    bench.add("platform/audit", platform_audit, iterations=iterations)

    meminfo = (f"MemTotal:        {baseline.ram_mb * 1024} kB\n"
               f"MemAvailable:    {baseline.ram_mb * 768} kB\n")
    memory = MemoryManager(meminfo_text=meminfo)

    def memory_refresh() -> None:
        memory.refresh()

    bench.add("memory/refresh", memory_refresh, iterations=iterations)
    return bench


#: Jetson board baselines (published figures; NEEDS_HARDWARE_VALIDATION).
_JETSON_BASELINES: dict[str, EdgeBaseline] = {
    "jetson-orin-nano": EdgeBaseline(
        board="Jetson Orin Nano", cpu_count=6,
        cpu_desc="6-core Cortex-A78AE ARMv8.2 @ 1.7 GHz", ram_mb=8192,
        recommended_cache_entries=2000,
        recommended_max_resident_models=4,
        recommended_power_budget_mw=15000,
        notes=("40 INT8 TOPS via Ampere GPU + DLA; JetPack required",
               "power modes (7W/15W) change the envelope at runtime")),
    "jetson-orin-nx": EdgeBaseline(
        board="Jetson Orin NX", cpu_count=8,
        cpu_desc="8-core Cortex-A78AE ARMv8.2 @ 2.0 GHz", ram_mb=16384,
        recommended_cache_entries=4000,
        recommended_max_resident_models=8,
        recommended_power_budget_mw=25000,
        notes=("100 INT8 TOPS; 16 GB variant assumed",
               "NVMe recommended: eMMC wears under model churn")),
    "jetson-xavier-nx": EdgeBaseline(
        board="Jetson Xavier NX", cpu_count=6,
        cpu_desc="6-core Carmel ARMv8.2 @ 1.9 GHz", ram_mb=8192,
        recommended_cache_entries=1500,
        recommended_max_resident_models=3,
        recommended_power_budget_mw=20000,
        notes=("21 INT8 TOPS; older JetPack branch",
               "thermal solution mandatory for sustained inference")),
}


def jetson_baseline(label: str) -> EdgeBaseline:
    """Resolve a Jetson board label; raises listing known boards."""
    norm = label.lower().replace(" ", "-").removeprefix("jetson-")
    for known_key, baseline in _JETSON_BASELINES.items():
        if known_key.removeprefix("jetson-") == norm:
            return baseline
    raise ValueError(
        f"unknown Jetson board {label!r}; known: "
        f"{sorted(_JETSON_BASELINES)}")


def jetson_bench_suite(board_label: str = "jetson-orin-nano",
                       iterations: int = 200) -> EdgeBenchmark:
    """Slice 198: Jetson-bound benchmark suite.

    The standard edge suite bound to a Jetson board baseline, plus an
    ``npu/detect`` case (adapter detection cost — paid on every
    bootstrap and on every NPU reselection). Surrogate-host marking
    follows the same rule as the Pi suite.
    """
    from hugrgate.edge.npu import (
        JetsonAdapter,
        MockNPUAdapter,
        NPURegistry,
    )

    baseline = jetson_baseline(board_label)
    bench = edge_bench_suite(
        name=f"jetson-suite-{baseline.board.lower().replace(' ', '-')}",
        baseline_board=baseline, iterations=iterations)

    registry = NPURegistry()
    registry.register(MockNPUAdapter())
    registry.register(JetsonAdapter(
        model_text="NVIDIA Jetson Orin Nano Developer Kit"))

    def npu_detect() -> None:
        registry.detect_all()

    bench.add("npu/detect", npu_detect, iterations=iterations)
    return bench
