"""Slice 021 — import-cycle elimination.

Regression test for the client<->server cycle eliminated in this
slice: the shared serde helpers now live in the neutral
``hugrgate.serde`` module, so the module-level import graph (lazy
edges included) is a DAG.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "hugrgate"


def _module_graph():
    modmap = {}
    for p in PKG.rglob("*.py"):
        name = "hugrgate." + p.relative_to(PKG).with_suffix(
            "").as_posix().replace("/", ".")
        if name.endswith(".__init__"):
            name = name[:-9]
        modmap[name] = p
    graph: dict[str, set[str]] = {}
    for name, path in modmap.items():
        tree = ast.parse(path.read_text())
        deps = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                m = node.module
                if m in modmap:
                    deps.add(m)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in modmap:
                        deps.add(a.name)
        graph[name] = deps - {name}
    return graph


def _find_cycle(graph):
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {m: WHITE for m in graph}

    def visit(node, stack):
        color[node] = GRAY
        for nxt in sorted(graph[node]):
            if color[nxt] == GRAY:
                return [*stack, node, nxt]
            if color[nxt] == WHITE:
                hit = visit(nxt, [*stack, node])
                if hit:
                    return hit
        color[node] = BLACK
        return None

    for mod in sorted(graph):
        if color[mod] == WHITE:
            hit = visit(mod, [])
            if hit:
                return hit
    return None


def test_full_import_graph_is_acyclic():
    """Every import edge — including function-level lazy ones — must
    form a DAG. (The eager-only variant lives in test_arch_map.py.)"""
    cycle = _find_cycle(_module_graph())
    assert cycle is None, f"import cycle: {' -> '.join(cycle)}"


def test_serde_is_neutral_ground():
    """hugrgate.serde may only depend on contract-layer modules, so it
    can never reintroduce the client<->server tangle."""
    graph = _module_graph()
    allowed = {
        "hugrgate.errors", "hugrgate.policy", "hugrgate.result",
        "hugrgate.spec",
    }
    deps = graph["hugrgate.serde"]
    assert deps <= allowed, f"serde depends on {deps - allowed}"


def test_client_still_reexports_serde_helpers():
    """Backward compatibility: the helpers moved, the import path did not."""
    from hugrgate import serde
    from hugrgate.client import (
        policy_from_dict,
        policy_to_dict,
        result_from_dict,
    )
    assert policy_from_dict is serde.policy_from_dict
    assert policy_to_dict is serde.policy_to_dict
    assert result_from_dict is serde.result_from_dict
