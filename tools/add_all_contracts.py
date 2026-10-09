#!/usr/bin/env python3
"""Add explicit ``__all__`` contracts to every hugrgate module (slice 003).

Derives the public names from the module AST (top-level classes,
functions, and UPPER_CASE constants not starting with "_") and inserts
``__all__`` immediately after the last top-level import statement
(after ``from __future__`` imports, where present).

Idempotent: modules that already define ``__all__`` are skipped.
Run from the repo root.
"""

from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "hugrgate")


def public_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and not target.id.startswith("_")
                    and target.id.isupper()
                ):
                    names.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if not node.target.id.startswith("_") and node.target.id.isupper():
                names.append(node.target.id)
    return names


def insert_after_imports(path: str, names: list[str]) -> bool:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    if any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)
        for n in tree.body
    ):
        return False
    last_import_end = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_import_end = node.end_lineno
    lines = src.splitlines(keepends=True)
    block = "\n__all__ = [\n" + "".join(f'    "{n}",\n' for n in names) + "]\n"
    lines.insert(last_import_end, block)
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    return True


def main() -> int:
    changed = []
    for root, dirs, files in os.walk(PKG):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            names = public_names(tree)
            if names and insert_after_imports(path, names):
                changed.append(os.path.relpath(path, ROOT))
    print(f"added __all__ to {len(changed)} modules")
    for c in changed:
        print("  ", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
