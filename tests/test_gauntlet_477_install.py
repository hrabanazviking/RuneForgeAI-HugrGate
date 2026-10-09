"""Slice 477 — fresh-clone install gauntlet.

The real gauntlet is ``tools/fresh_clone_install.sh`` (clone → fresh
venv → ``pip install .`` → smoke probe → entry-point check). A full
clone+install needs network and minutes, so it does not run in the
unit suite; these tests pin the gauntlet's machinery instead: the
script is syntactically valid and executable, the smoke probe
compiles and drives the real gate end to end, and the pyproject
entry points resolve to importable callables.
"""

from __future__ import annotations

import importlib
import py_compile
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "fresh_clone_install.sh"
SMOKE = ROOT / "tools" / "install_smoke.py"


def test_install_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & stat.S_IXUSR, "script must be executable"


def test_install_script_passes_bash_syntax_check():
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - CI always has bash
        pytest.skip("bash not available")
    proc = subprocess.run([bash, "-n", str(SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_install_script_covers_the_gauntlet_steps():
    text = SCRIPT.read_text(encoding="utf-8")
    for step in ("git clone", "python3 -m venv", "pip install",
                 "install_smoke.py", "hugrgate", "--help"):
        assert step in text, f"script missing gauntlet step: {step}"
    assert "set -euo pipefail" in text


def test_smoke_probe_compiles():
    py_compile.compile(str(SMOKE), doraise=True)


def test_smoke_probe_main_is_importable():
    # Load by path so we never depend on tools/ being a package.
    import importlib.util

    spec = importlib.util.spec_from_file_location("install_smoke", str(SMOKE))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_smoke_probe_decision_path_end_to_end():
    """The probe's backend + decide() flow works against the live package."""
    from hugrgate import DecisionPolicy, DecisionResult, DecisionSpec, HugrGate
    from hugrgate.backend import Backend

    class SmokeBackend(Backend):
        name = "smoke-test"

        def capabilities(self) -> dict[str, Any]:
            return {"spec_types": ["categorical"]}

        def supports(self, spec: DecisionSpec) -> bool:
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None) -> DecisionResult:
            options = spec.options or ["a"]
            return DecisionResult(
                value=options[0],
                probability=1.0,
                distribution={o: 1.0 if o == options[0] else 0.0
                              for o in options},
            )

    gate = HugrGate()
    gate.register(SmokeBackend())
    result = gate.decide(
        {"q": 1},
        DecisionSpec(type="categorical", options=["yes", "no"]),
        DecisionPolicy(),
    )
    assert result.value == "yes"
    gate.close()


def test_entry_points_resolve():
    """Both console scripts map to importable, callable entry points."""
    for dotted in ("hugrgate.cli:main", "hugrgate.daemon:main"):
        mod_name, attr = dotted.split(":")
        module = importlib.import_module(mod_name)
        assert callable(getattr(module, attr)), dotted


def test_cli_help_runs():
    proc = subprocess.run(
        [sys.executable, "-m", "hugrgate.cli", "--help"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    # argparse exits 0 on --help; a broken entry point would traceback.
    assert proc.returncode == 0, proc.stderr
    assert "usage" in proc.stdout.lower()
