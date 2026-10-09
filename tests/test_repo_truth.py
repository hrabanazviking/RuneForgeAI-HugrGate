"""Slice 001 — Repository truth audit.

The repository must match its own claims. These tests fail on drift:
a module that stops importing, a version skew, an ``__all__`` name that
no longer resolves, a console-script entry point that breaks, or an HTTP
route that is implemented but undocumented (or documented but missing).
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

import hugrgate

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "hugrgate"


def _package_modules() -> list[str]:
    mods = []
    for path in sorted(PKG.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        mods.append(".".join(path.relative_to(ROOT).with_suffix("").parts))
    return mods


def _code_routes(path: Path) -> set[str]:
    """Extract literal route paths from ``@app.<verb>("<path>")``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routes = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"get", "post", "put", "delete", "patch"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            routes.add(node.args[0].value)
    return routes


# --- success: everything claimed exists ------------------------------------

def test_all_package_modules_import_cleanly():
    mods = _package_modules()
    assert len(mods) >= 30, "module inventory collapsed unexpectedly"
    for mod in mods:
        importlib.import_module(mod)  # must not raise


def test_version_matches_pyproject():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M).group(1)
    assert hugrgate.__version__ == declared


def test_public_api_names_all_resolve():
    for name in hugrgate.__all__:
        assert hasattr(hugrgate, name), f"__all__ name {name!r} missing"


def test_star_import_is_restricted_to_all():
    namespace: dict = {}
    exec("from hugrgate import *", namespace)
    leaked = {k for k in namespace if not k.startswith("_")} - set(hugrgate.__all__)
    assert not leaked, f"names leaked past __all__: {sorted(leaked)}"


def test_console_script_entry_points_importable():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for match in re.finditer(r'^(\S+)\s*=\s*"([^:]+):(\w+)"', pyproject, re.M):
        module_name, attr = match.group(2), match.group(3)
        module = importlib.import_module(module_name)
        assert callable(getattr(module, attr)), f"{module_name}:{attr} not callable"


def test_docs_api_covers_every_http_route():
    api_md = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    missing: dict[str, set[str]] = {}
    for fname in ("server.py", "daemon.py"):
        routes = _code_routes(PKG / fname) - {"/"}
        undocumented = {r for r in routes if r not in api_md}
        if undocumented:
            missing[fname] = undocumented
    assert not missing, f"routes missing from docs/api.md: {missing}"


def test_docs_api_lists_no_phantom_routes():
    api_md = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^###\s+(?:GET|POST|PUT|DELETE|PATCH)\s+(/\S*)", api_md, re.M))
    implemented = _code_routes(PKG / "server.py") | _code_routes(PKG / "daemon.py")
    phantoms = {r for r in documented if r not in implemented}
    assert not phantoms, f"docs/api.md lists routes that do not exist: {phantoms}"


def test_audit_manifest_matches_live_tree():
    import json

    manifest = json.loads((ROOT / "docs" / "campaign-i" / "manifest.json").read_text())
    live = {m for m in _package_modules() if m != "hugrgate"}
    recorded = {m for m in manifest["modules"] if m != "hugrgate"}
    # hugrgate/__init__.py maps to "hugrgate"; normalize both sides
    assert live == recorded, (
        f"manifest drift: only-live={sorted(live - recorded)}, "
        f"only-recorded={sorted(recorded - live)}"
    )
    assert manifest["pyproject_version"] == hugrgate.__version__


# --- failure / boundary ------------------------------------------------------

def test_importing_nonexistent_module_still_raises():
    with pytest.raises(ImportError):
        importlib.import_module("hugrgate.no_such_module_xyz")


def test_route_extractor_handles_empty_file(tmp_path: Path):
    empty = tmp_path / "empty.py"
    empty.write_text("x = 1\n", encoding="utf-8")
    assert _code_routes(empty) == set()
