"""Slice 003 — Public API inventory.

Every module must declare an explicit ``__all__`` contract, every listed
name must resolve, star-imports must stay inside the contract, the
package surface must be append-only, and the generated inventory document
must match the live code.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

import hugrgate

pytestmark = pytest.mark.gate
ROOT = Path(__file__).resolve().parent.parent
INV = ROOT / "docs" / "campaign-i" / "003-public-api-inventory.md"
GEN = ROOT / "tools" / "gen_api_inventory.py"

# Append-only snapshot of the top-level public surface (slice 003).
# Additions require updating this snapshot AND the inventory doc.
PACKAGE_API_SNAPSHOT = frozenset({
    "DecisionSpec", "DecisionResult", "DecisionPolicy",
    "Backend", "BackendRegistry", "HugrGate",
    "HugrGateError", "SpecError", "PolicyError", "BackendError",
    "BackendUnavailable", "CalibrationError", "TimeoutError",
    "PrivacyViolation", "QueueFull", "Abstention",
})


def _modules() -> list[str]:
    mods = []
    for path in sorted((ROOT / "hugrgate").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        mods.append(rel[: -len(".__init__")] if rel.endswith(".__init__") else rel)
    return mods


def test_every_module_declares_all():
    missing = []
    for mod_name in _modules():
        module = importlib.import_module(mod_name)
        if not isinstance(getattr(module, "__all__", None), list):
            missing.append(mod_name)
    assert not missing, f"modules without an __all__ contract: {missing}"


def test_all_contract_names_resolve():
    bad = []
    for mod_name in _modules():
        module = importlib.import_module(mod_name)
        for name in module.__all__:
            if not hasattr(module, name):
                bad.append(f"{mod_name}.{name}")
    assert not bad, f"__all__ names that do not resolve: {bad}"


def test_all_contract_names_are_unique():
    dupes = []
    for mod_name in _modules():
        names = importlib.import_module(mod_name).__all__
        if len(set(names)) != len(names):
            dupes.append(mod_name)
    assert not dupes, f"modules with duplicate __all__ entries: {dupes}"


def test_package_surface_is_append_only():
    live = set(hugrgate.__all__)
    removed = PACKAGE_API_SNAPSHOT - live
    assert not removed, f"public API names removed: {sorted(removed)}"


def test_package_snapshot_matches_live():
    assert set(hugrgate.__all__) == PACKAGE_API_SNAPSHOT, (
        "package __all__ changed: update PACKAGE_API_SNAPSHOT, "
        "the inventory doc, and CHANGELOG.md"
    )


def test_star_imports_stay_inside_contracts():
    leaks = []
    for mod_name in _modules():
        ns: dict = {}
        exec(f"from {mod_name} import *", ns)
        module = importlib.import_module(mod_name)
        leaked = {k for k in ns if not k.startswith("_")} - set(module.__all__)
        if leaked:
            leaks.append(f"{mod_name}: {sorted(leaked)}")
    assert not leaks, f"star-import leaks: {leaks}"


def test_inventory_doc_is_fresh():
    before = INV.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(GEN)], capture_output=True, text=True, cwd=ROOT
    )
    assert proc.returncode == 0, proc.stderr
    assert INV.read_bytes() == before, "API inventory drifted from live code"


def test_inventory_doc_covers_every_module():
    text = INV.read_text(encoding="utf-8")
    missing = [m for m in _modules() if f"### `{m}`" not in text]
    assert not missing, f"modules missing from inventory: {missing}"


# --- failure / boundary --------------------------------------------------------

def test_contract_rejects_unknown_name():
    module = importlib.import_module("hugrgate.errors")
    assert "NoSuchErrorXYZ" not in module.__all__
    assert not hasattr(module, "NoSuchErrorXYZ")
