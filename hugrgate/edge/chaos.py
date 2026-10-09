"""Edge failure testing — deterministic fault injection. Slice 199.

:class:`ChaosRunner` executes named :class:`FaultScenario`s against
real Campaign VIII components. Each scenario *injects* a fault
(power cut, thermal spike, NPU dropout, memory pressure, flash
exhaustion, watchdog starvation) and then *verifies* the documented
degradation behavior held — the same assertions the unit tests pin,
but exercised as end-to-end failure stories with a report at the end.

Scenarios are deterministic (scripted sensors, fixture memory maps,
tmpdirs) and hermetic: every scenario builds its own components, so
a fault in one cannot leak into the next.
"""

from __future__ import annotations

import json
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import ChaosError

__all__ = [
    "BUILTIN_SCENARIOS",
    "ChaosResult",
    "ChaosRunner",
    "FaultScenario",
    "build_builtin_runner",
]


@dataclass(frozen=True)
class FaultScenario:
    """One inject-then-verify failure story."""

    name: str
    description: str
    run: Callable[[], None]
    """Inject the fault and verify recovery. Raises on failure."""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ChaosError("scenario name must be non-empty")


@dataclass
class ChaosResult:
    """Outcome of one scenario."""

    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed,
                "detail": self.detail}


class ChaosRunner:
    """Registers and executes fault scenarios, collecting results."""

    def __init__(self):
        self._lock = threading.RLock()
        self._scenarios: dict[str, FaultScenario] = {}
        self._results: list[ChaosResult] = []

    def register(self, scenario: FaultScenario) -> ChaosRunner:
        if not isinstance(scenario, FaultScenario):
            raise ChaosError(
                f"can only register FaultScenario, got "
                f"{type(scenario).__name__}")
        with self._lock:
            if scenario.name in self._scenarios:
                raise ChaosError(
                    f"duplicate chaos scenario {scenario.name!r}")
            self._scenarios[scenario.name] = scenario
        return self

    def scenarios(self) -> list[str]:
        with self._lock:
            return sorted(self._scenarios)

    def run_all(self) -> list[ChaosResult]:
        """Execute every scenario; a scenario raising is a failure,
        never an abort — the report must show *all* outcomes."""
        results: list[ChaosResult] = []
        with self._lock:
            scenarios = [self._scenarios[n] for n in sorted(self._scenarios)]
        for scenario in scenarios:
            try:
                scenario.run()
            except Exception as e:  # noqa: BLE001 - recorded per scenario
                results.append(ChaosResult(
                    scenario.name, False, f"{type(e).__name__}: {e}"))
            else:
                results.append(ChaosResult(scenario.name, True))
        with self._lock:
            self._results = results
        return list(results)

    def report(self) -> dict[str, Any]:
        """JSON-serializable report of the last run."""
        with self._lock:
            results = list(self._results)
        failed = [r.name for r in results if not r.passed]
        return {"scenarios": len(results),
                "passed": len(results) - len(failed),
                "failed": failed,
                "results": [r.to_dict() for r in results],
                "all_passed": not failed and bool(results)}


# --- built-in scenarios ---------------------------------------------------------------

def _scenario_power_loss_mid_write() -> None:
    from hugrgate.edge.recovery import CheckpointJournal
    with tempfile.TemporaryDirectory() as tmp:
        journal = CheckpointJournal.open(tmp)
        journal.checkpoint("good", {"offset": 7})
        # power dies mid-write: torn record
        torn = journal._dir / "chk_00000099_torn.json"
        torn.write_bytes(b'{"body": {"magic": "HGCK0001", "seq": 99, '
                         b'"state_id": "torn", "payload": {}}, "crc32": 1'[:40])
        assert journal.recover() == {"offset": 7}, \
            "torn checkpoint must be skipped"


def _scenario_thermal_spike() -> None:
    from hugrgate.backend import Backend
    from hugrgate.edge.routing import EdgeRouter
    from hugrgate.edge.thermal import MockThermalSensor, ThermalGovernor
    from hugrgate.result import DecisionResult

    class Be(Backend):
        def __init__(self, name, tclass):
            self.name = name
            self._tclass = tclass
        def capabilities(self): return {}
        def supports(self, spec): return True
        def evaluate(self, state, spec, context=None):
            return DecisionResult(value="a", probability=0.9)
        def hardware_requirements(self):
            return {"edge": {"thermal_class": self._tclass}}

    router = EdgeRouter(ThermalGovernor(
        MockThermalSensor([45.0, 95.0, 95.0])))
    cands: list[Backend] = [Be("hot-be", "hot"), Be("cool-be", "cool")]
    # 45C: normal — both routable, cool first
    assert [b.name for b in router.route(cands)] == ["cool-be", "hot-be"]
    # 95C: critical — hot backend shed
    assert [b.name for b in router.route(cands)] == ["cool-be"], \
        "thermal spike must shed hot backends"
    assert [b.name for b in router.route(cands)] == ["cool-be"]


def _scenario_npu_dropout() -> None:
    from hugrgate.edge.npu import MockNPUAdapter, NPURegistry
    reg = NPURegistry()
    npu = MockNPUAdapter()
    reg.register(npu)
    assert reg.best_for("int8") is npu
    npu._present = False  # device drops off the bus mid-run
    assert reg.detect_all() == {}
    assert reg.best_for("int8") is None


def _scenario_memory_pressure() -> None:
    from hugrgate.edge.cachetune import EdgeCache
    from hugrgate.edge.memory import MemoryInfo, MemoryManager
    from hugrgate.edge.residency import ModelEntry, ResidencyError, ResidencyManager
    mem = MemoryManager(meminfo_text="MemTotal: 1000000 kB\n"
                                     "MemAvailable: 900000 kB\n")
    cache = EdgeCache(mem)
    full_size = cache.config.max_size
    mgr = ResidencyManager(ram_budget_bytes=2000, memory=mem)
    mgr.register_model(ModelEntry(name="m", size_bytes=500))
    mgr.acquire("m")
    mgr.release("m")  # idle: eligible for shedding
    # pressure spike: available RAM collapses to critical
    mem.refresh(MemoryInfo(1024**3, 100 * 2**20, False, False))
    assert cache.config.max_size < full_size, \
        "cache must shrink under memory pressure"
    assert mgr.resident_models() == [], \
        "idle models must be shed under memory pressure"
    try:
        mgr.acquire("m")
    except ResidencyError:
        pass
    else:
        raise AssertionError("critical memory must refuse non-pinned models")


def _scenario_flash_budget_exhaustion() -> None:
    from hugrgate.edge.storage import StorageError, WearAwareStore
    with tempfile.TemporaryDirectory() as tmp:
        # magic (8) + record (10) = 18 bytes > 10 budget: flush must refuse
        store = WearAwareStore.open(tmp, write_budget_bytes=10)
        store.put("k", b"v")
        try:
            store.flush()
        except StorageError:
            pass  # fail-closed is the correct behavior
        else:
            raise AssertionError("exhausted flash budget must fail closed")
        finally:
            store._closed = True  # budget deliberately exhausted


def _scenario_watchdog_starvation() -> None:
    from hugrgate.edge.watchdog import EdgeWatchdog
    now = [1000.0]
    fired: list[int] = []
    wd = EdgeWatchdog(5.0, clock=lambda: now[0], on_miss=fired.append)
    now[0] += 30.0  # nobody heartbeats for 30s
    assert wd.check() == "missed"
    assert wd.misses == 1 and fired == [1], \
        "starved watchdog must record the miss and fire the policy"


BUILTIN_SCENARIOS: list[FaultScenario] = [
    FaultScenario("power-loss-mid-write",
                  "torn checkpoint is skipped in favor of the last good one",
                  _scenario_power_loss_mid_write),
    FaultScenario("thermal-spike",
                  "95C spike sheds hot backends from routing",
                  _scenario_thermal_spike),
    FaultScenario("npu-dropout",
                  "vanished NPU disappears from detection and selection",
                  _scenario_npu_dropout),
    FaultScenario("memory-pressure",
                  "critical memory sheds cache and idle models, refuses load",
                  _scenario_memory_pressure),
    FaultScenario("flash-budget-exhaustion",
                  "exhausted flash budget fails closed, never silently",
                  _scenario_flash_budget_exhaustion),
    FaultScenario("watchdog-starvation",
                  "un-heartbeated loop records a miss and fires policy",
                  _scenario_watchdog_starvation),
]


def build_builtin_runner() -> ChaosRunner:
    """A runner with all built-in scenarios registered."""
    runner = ChaosRunner()
    for scenario in BUILTIN_SCENARIOS:
        runner.register(scenario)
    return runner


def run_builtin_scenarios() -> dict[str, Any]:
    """Execute all built-in scenarios; returns the JSON-able report."""
    runner = build_builtin_runner()
    runner.run_all()
    report = runner.report()
    json.dumps(report)  # contract: always serializable
    return report
