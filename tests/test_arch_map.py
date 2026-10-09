"""Slice 002 — architecture map regeneration.

The architecture map in ``docs/campaign-i/architecture-map.md`` is
machine-generated and must stay in sync with the tree:
every module must appear, regeneration must be byte-deterministic,
and the eager import graph must be acyclic (lazy edges excluded).
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "docs" / "campaign-i" / "architecture-map.md"
GEN = ROOT / "tools" / "gen_arch_map.py"


def _load_gen():
    spec = importlib.util.spec_from_file_location("gen_arch_map", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _package_modules() -> set[str]:
    mods = set()
    for path in sorted((ROOT / "hugrgate").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        mods.add(rel[: -len(".__init__")] if rel.endswith(".__init__") else rel)
    return mods


# --- success -----------------------------------------------------------------

def test_map_file_exists_and_names_every_module():
    text = MAP.read_text(encoding="utf-8")
    missing = [m for m in _package_modules() if m.replace("hugrgate.", "") not in text]
    assert not missing, f"modules missing from architecture map: {missing}"


def test_map_regeneration_is_deterministic():
    before = MAP.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(GEN)], capture_output=True, text=True, cwd=ROOT
    )
    assert proc.returncode == 0, proc.stderr
    assert MAP.read_bytes() == before, "regeneration changed the map -> nondeterministic"


def test_every_module_has_an_explicit_layer():
    gen = _load_gen()
    unmapped = sorted(_package_modules() - set(gen.LAYER_OF))
    assert not unmapped, f"modules without an explicit layer: {unmapped}"


def test_eager_import_graph_is_acyclic():
    """Import-time edges (lazy edges excluded) must form a DAG.

    The known client<->server tangle is safe only because the
    client->server edge is lazy; this test fails if anyone makes it eager.
    """
    gen = _load_gen()
    edges: dict[str, set[str]] = {}
    for mod, info in gen._walk_for_tests().items():
        edges[mod] = {t for t, lazy in info["edges"].items() if not lazy}

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {m: WHITE for m in edges}

    def visit(node: str, stack: list[str]) -> None:
        color[node] = GRAY
        for nxt in sorted(edges[node]):
            if color[nxt] == GRAY:
                cycle = " -> ".join(stack + [node, nxt])
                raise AssertionError(f"eager import cycle: {cycle}")
            if color[nxt] == WHITE:
                visit(nxt, stack + [node])
        color[node] = BLACK

    for mod in sorted(edges):
        if color[mod] == WHITE:
            visit(mod, [])


# --- failure / boundary ------------------------------------------------------

def test_generator_rejects_unmapped_module():
    gen = _load_gen()
    fake = {"hugrgate.ghost": {"path": "x", "edges": {}}}
    assert gen._unmapped(fake) == ["hugrgate.ghost"]
    assert gen._unmapped({"hugrgate.errors": {}}) == []


def test_cycle_detector_catches_a_cycle():
    gen = _load_gen()
    graph = {"a": {"b": False}, "b": {"a": False}}

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {m: WHITE for m in graph}
    found = []

    def visit(node, stack):
        color[node] = GRAY
        for nxt in graph[node]:
            if color[nxt] == GRAY:
                found.append(" -> ".join(stack + [node, nxt]))
            elif color[nxt] == WHITE:
                visit(nxt, stack + [node])
        color[node] = BLACK

    for m in graph:
        if color[m] == WHITE:
            visit(m, [])
    assert found, "cycle detector failed to flag a->b->a"
    assert "a" in found[0] and "b" in found[0]
