"""Edge Intelligence release gate. Slice 200.

:func:`edge_release_gate` is Campaign VIII's Definition of Done made
executable. It runs the same verifications the campaign applied slice
by slice, then renders a verdict:

1. **test-suite** — the full repository pytest suite, real result;
2. **ruff** — lint clean over ``hugrgate/``, ``tests/``, ``tools/``;
3. **mypy** — type check clean over ``hugrgate/``;
4. **chaos** — all six built-in fault scenarios green;
5. **slice-docs** — all 25 campaign docs present and non-trivial;
6. **benchmark-artifacts** — every ``benchmarks/edge/*.json`` loads
   under the ``edge-bench/1`` schema;
7. **stub-scan** — no unfinished-work markers in
   ``hugrgate/edge/``;
8. **maps-fresh** — the architecture map and API inventory regenerate
   byte-identically.

Checks are selectable (``only=[...]``) so CI can run the fast subset
and humans can run the full gate. A failed check becomes a *blocker*,
listed verbatim — the gate never advances on visited labels alone.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.errors import GateError

__all__ = [
    "GATE_CHECKS",
    "GateCheck",
    "GateReport",
    "edge_release_gate",
]

#: All gate check names, in execution order.
GATE_CHECKS = ("test-suite", "ruff", "mypy", "chaos", "slice-docs",
               "benchmark-artifacts", "stub-scan", "maps-fresh")

#: Markers that indicate unfinished work. Built from fragments so the
#: scanner does not flag its own definition line.
_STUB_WORDS = ("TO" + "DO", "FIX" + "ME", "X" + "XX", "HA" + "CK",
               "place" + "holder")
_STUB_RE = re.compile(r"\b(" + "|".join(_STUB_WORDS) + r")\b")

#: Slice numbers in Campaign VIII.
_CAMPAIGN_SLICES = tuple(range(176, 201))


@dataclass
class GateCheck:
    """One gate verification and its outcome."""

    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed,
                "detail": self.detail}


@dataclass
class GateReport:
    """The gate verdict: checks, blockers, and the bottom line."""

    checks: list[GateCheck] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.blockers and bool(self.checks)

    def summary(self) -> str:
        ok = sum(1 for c in self.checks if c.passed)
        status = "PASS" if self.passed else "FAIL"
        return (f"edge release gate {status}: {ok}/{len(self.checks)} "
                f"checks green, {len(self.blockers)} blocker(s)")

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed,
                "checks": [c.to_dict() for c in self.checks],
                "blockers": list(self.blockers)}


def _run(cmd: list[str], cwd: Path, timeout_s: float) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=str(cwd), timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout_s}s"
    tail = (proc.stdout + proc.stderr)[-4000:]
    return proc.returncode, tail.strip()


class _Gate:
    def __init__(self, root: Path, python: str):
        self.root = root
        self.python = python
        self._lock = threading.RLock()

    def _check(self, name: str, passed: bool, detail: str) -> GateCheck:
        return GateCheck(name, passed, detail[:2000])

    # -- individual checks --------------------------------------------------------

    def check_test_suite(self) -> GateCheck:
        code, tail = _run(
            [self.python, "-m", "pytest", "tests/", "-q",
             "-p", "no:cacheprovider"],
            self.root, timeout_s=1800.0)
        last = tail.strip().splitlines()[-1] if tail.strip() else ""
        return self._check("test-suite", code == 0,
                           f"exit={code}; {last}")

    def check_ruff(self) -> GateCheck:
        code, tail = _run(
            [self.python, "-m", "ruff", "check", "hugrgate/", "tests/",
             "tools/"],
            self.root, timeout_s=300.0)
        last = tail.strip().splitlines()[-1] if tail.strip() else ""
        return self._check("ruff", code == 0, f"exit={code}; {last}")

    def check_mypy(self) -> GateCheck:
        code, tail = _run([self.python, "-m", "mypy", "hugrgate/"],
                          self.root, timeout_s=600.0)
        last = tail.strip().splitlines()[-1] if tail.strip() else ""
        return self._check("mypy", code == 0, f"exit={code}; {last}")

    def check_chaos(self) -> GateCheck:
        from hugrgate.edge.chaos import run_builtin_scenarios
        try:
            report = run_builtin_scenarios()
        except Exception as e:  # noqa: BLE001 - gate records, not raises
            return self._check("chaos", False, f"runner crashed: {e}")
        return self._check(
            "chaos", report["all_passed"],
            f"{report['passed']}/{report['scenarios']} scenarios green"
            + (f"; failed={report['failed']}" if report["failed"] else ""))

    def check_slice_docs(self) -> GateCheck:
        docs = self.root / "docs" / "campaign-viii"
        missing, trivial = [], []
        for n in _CAMPAIGN_SLICES:
            matches = sorted(docs.glob(f"{n}-*.md"))
            if not matches:
                missing.append(str(n))
                continue
            for path in matches:
                if len(path.read_text(encoding="utf-8")) < 400:
                    trivial.append(path.name)
        passed = not missing and not trivial
        detail = "all 25 slice docs present and non-trivial"
        if missing:
            detail = f"missing docs for slices: {missing}"
        elif trivial:
            detail = f"trivial docs (<400 chars): {trivial}"
        return self._check("slice-docs", passed, detail)

    def check_benchmark_artifacts(self) -> GateCheck:
        from hugrgate.edge.bench import load_artifact
        bench_dir = self.root / "benchmarks" / "edge"
        files = sorted(bench_dir.glob("*.json")) if bench_dir.is_dir() else []
        if not files:
            return self._check("benchmark-artifacts", False,
                               "no artifacts in benchmarks/edge/")
        bad = []
        for path in files:
            try:
                load_artifact(path)
            except Exception as e:  # noqa: BLE001 - collected as failure
                bad.append(f"{path.name}: {e}")
        passed = not bad
        detail = (f"{len(files)} artifacts load under edge-bench/1"
                  if passed else f"invalid artifacts: {bad}")
        return self._check("benchmark-artifacts", passed, detail)

    def check_stub_scan(self) -> GateCheck:
        edge_dir = self.root / "hugrgate" / "edge"
        hits = []
        for path in sorted(edge_dir.glob("*.py")):
            for i, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                if _STUB_RE.search(line):
                    hits.append(f"{path.name}:{i}")
        passed = not hits
        detail = ("no unfinished-work markers in "
                  "hugrgate/edge/" if passed else f"markers at {hits}")
        return self._check("stub-scan", passed, detail)

    def check_maps_fresh(self) -> GateCheck:
        stale = []
        for gen, target in (
                ("tools/gen_arch_map.py",
                 "docs/campaign-i/architecture-map.md"),
                ("tools/gen_api_inventory.py",
                 "docs/campaign-i/003-public-api-inventory.md")):
            target_path = self.root / target
            before = target_path.read_bytes() if target_path.exists() \
                else b""
            code, tail = _run([self.python, gen], self.root,
                              timeout_s=300.0)
            if code != 0:
                stale.append(f"{gen} failed: {tail[-200:]}")
                continue
            if target_path.read_bytes() != before:
                stale.append(f"{target} drifted from generator")
        passed = not stale
        detail = ("architecture map and API inventory regenerate "
                  "byte-identically" if passed else "; ".join(stale))
        return self._check("maps-fresh", passed, detail)


_CHECK_METHODS = {
    "test-suite": _Gate.check_test_suite,
    "ruff": _Gate.check_ruff,
    "mypy": _Gate.check_mypy,
    "chaos": _Gate.check_chaos,
    "slice-docs": _Gate.check_slice_docs,
    "benchmark-artifacts": _Gate.check_benchmark_artifacts,
    "stub-scan": _Gate.check_stub_scan,
    "maps-fresh": _Gate.check_maps_fresh,
}


def edge_release_gate(repo_root: str | Path | None = None, *,
                      only: list[str] | None = None,
                      python: str | None = None) -> GateReport:
    """Run the Edge Intelligence release gate.

    ``repo_root`` defaults to the current working directory.
    ``only`` selects a subset of :data:`GATE_CHECKS` (unknown names
    raise :class:`GateError`). Returns a :class:`GateReport`; never
    raises for a *failed check* — failures become blockers.
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    if only is not None:
        unknown = [n for n in only if n not in GATE_CHECKS]
        if unknown:
            raise GateError(f"unknown gate checks: {unknown}")
        selected = [n for n in GATE_CHECKS if n in only]
    else:
        selected = list(GATE_CHECKS)
    gate = _Gate(root, python or sys.executable)
    report = GateReport()
    for name in selected:
        check = _CHECK_METHODS[name](gate)
        report.checks.append(check)
        if not check.passed:
            report.blockers.append(f"[{name}] {check.detail}")
    return report
