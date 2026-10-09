#!/usr/bin/env python3
"""Architecture map generator for HugrGate (Gjallarbrú slice 002).

Parses every module's AST, records internal ``hugrgate.*`` import edges
(marking imports that happen inside functions as LAZY), assigns each
module to an explicit architectural layer, and writes a deterministic
Markdown map (Mermaid diagram + layer table + edge list) to
``docs/campaign-i/architecture-map.md``.

Deterministic: same tree -> same bytes. Run from the repo root.
"""

from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "hugrgate")
OUT = os.path.join(ROOT, "docs", "campaign-i", "architecture-map.md")

# Explicit, auditable layer assignment. Every module must appear here;
# the generator fails loudly on an unmapped module (see slice-002 test).
LAYERS: dict[str, list[str]] = {
    "foundation": ["hugrgate.errors"],
    "contracts": [
        "hugrgate.spec", "hugrgate.result", "hugrgate.backend",
        "hugrgate.policy", "hugrgate.validation",
    ],
    "runtime": [
        "hugrgate.core", "hugrgate.abstain", "hugrgate.threshold",
        "hugrgate.negotiate", "hugrgate.fallback", "hugrgate.timeout",
        "hugrgate.circuit", "hugrgate.privacy", "hugrgate.ladder",
    ],
    "state": [
        "hugrgate.provenance", "hugrgate.health", "hugrgate.drift",
        "hugrgate.cache", "hugrgate.models", "hugrgate.features",
        "hugrgate.bench", "hugrgate.bench_report", "hugrgate.log",
    ],
    "backends": [
        "hugrgate.backends.rules", "hugrgate.backends.logreg",
        "hugrgate.backends.forest", "hugrgate.backends.boosting",
        "hugrgate.backends.embedding", "hugrgate.backends.llm",
        "hugrgate.backends.nli",
    ],
    "calibration": [
        "hugrgate.calibration", "hugrgate.calibration._base",
        "hugrgate.calibration.isotonic",
        "hugrgate.calibration.metrics", "hugrgate.calibration.platt",
        "hugrgate.calibration.profiles", "hugrgate.calibration.temperature",
    ],
    "service": [
        "hugrgate.server", "hugrgate.daemon", "hugrgate.client",
        "hugrgate.cli",
    ],
    "api": ["hugrgate"],
}

LAYER_OF = {m: layer for layer, mods in LAYERS.items() for m in mods}


class EdgeVisitor(ast.NodeVisitor):
    """Collect internal imports; flag those nested inside functions."""

    def __init__(self) -> None:
        self.edges: dict[str, bool] = {}  # target -> is_lazy
        self._depth = 0

    def visit_FunctionDef(self, node):  # noqa: N802
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def _record(self, module: str | None) -> None:
        if module and module.startswith("hugrgate"):
            lazy = self._depth > 0
            self.edges[module] = self.edges.get(module, False) or lazy
            # keep the eager bit if ANY import site is eager
            if not lazy:
                self.edges[module] = False

    def visit_Import(self, node):  # noqa: N802
        for a in node.names:
            if a.name.startswith("hugrgate"):
                self._record(a.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):  # noqa: N802
        if node.module and node.module.startswith("hugrgate"):
            self._record(node.module)
        self.generic_visit(node)


def resolve(dep: str, modules: set[str]) -> str | None:
    while dep not in modules and "." in dep:
        dep = dep.rsplit(".", 1)[0]
    return dep if dep in modules else None


def _scan_modules(pkg_dir: str = PKG) -> dict[str, dict]:
    """Parse every module under *pkg_dir*; returns mod -> {path, edges}."""
    modules: dict[str, dict] = {}
    for root, dirs, files in os.walk(pkg_dir):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
            mod = rel[: -len(".__init__")] if rel.endswith(".__init__") else rel
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            visitor = EdgeVisitor()
            visitor.visit(tree)
            modules[mod] = {"path": path, "edges": visitor.edges}
    return modules


# Backwards-compatible alias used by tests.
def _walk_for_tests() -> dict[str, dict]:
    return _scan_modules()


def _unmapped(modules: dict[str, dict]) -> list[str]:
    """Modules with no explicit layer assignment."""
    return sorted(set(modules) - set(LAYER_OF))


def main() -> int:
    modules = _scan_modules()

    unmapped = _unmapped(modules)
    if unmapped:
        print(f"ERROR: unmapped modules: {unmapped}", file=sys.stderr)
        return 1

    names = set(modules)
    edges: dict[str, dict[str, bool]] = {}
    for mod, info in modules.items():
        resolved: dict[str, bool] = {}
        for target, lazy in info["edges"].items():
            r = resolve(target, names)
            if r and r != mod:
                resolved[r] = resolved.get(r, True) and lazy
        edges[mod] = resolved

    short = lambda m: m.replace("hugrgate.", "")  # noqa: E731

    lines = [
        "# HugrGate architecture map",
        "",
        "Generated by `tools/gen_arch_map.py` (slice 002). Deterministic:",
        "re-running the generator on an unchanged tree yields byte-identical",
        "output. Edges marked `(lazy)` are imports deferred inside functions",
        "rather than at module top level.",
        "",
        "## Layers",
        "",
        "```mermaid",
        "flowchart TD",
    ]
    for layer, mods in LAYERS.items():
        node_ids = [short(m).replace(".", "_") for m in mods]
        lines.append(f"    subgraph {layer}[{layer}]")
        for m, nid in zip(mods, node_ids):
            lines.append(f"        {nid}[{short(m)}]")
        lines.append("    end")
    lines.append("")
    for mod in sorted(edges):
        src = short(mod).replace(".", "_")
        for tgt in sorted(edges[mod]):
            dst = short(tgt).replace(".", "_")
            style = " -.-> " if edges[mod][tgt] else " --> "
            lines.append(f"    {src}{style}{dst}")
    lines += [
        "```",
        "",
        "## Layer membership",
        "",
        "| Layer | Modules |",
        "|---|---|",
    ]
    for layer, mods in LAYERS.items():
        lines.append(f"| {layer} | {', '.join(f'`{short(m)}`' for m in mods)} |")
    lines += [
        "",
        "## Internal dependency edges",
        "",
        "| From | To | Lazy |",
        "|---|---|---|---|",
    ]
    for mod in sorted(edges):
        for tgt in sorted(edges[mod]):
            lazy = "yes" if edges[mod][tgt] else "no"
            lines.append(f"| `{short(mod)}` | `{short(tgt)}` | {lazy} |")
    lines.append("")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {OUT} ({sum(len(e) for e in edges.values())} edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
