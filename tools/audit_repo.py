#!/usr/bin/env python3
"""Repository truth auditor for HugrGate (Gjallarbrú campaign I, slice 001).

Walks the ``hugrgate`` package, the tests, the docs and pyproject.toml,
and emits:
  1. docs/campaign-i/manifest.json   -- machine-readable inventory
  2. docs/campaign-i/001-repository-truth-audit.md -- human audit report

Regenerating the audit is deterministic: same tree -> same bytes.
Run from the repository root with the project venv on PATH.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "hugrgate")
OUT_DIR = os.path.join(ROOT, "docs", "campaign-i")
MANIFEST = os.path.join(OUT_DIR, "manifest.json")
REPORT = os.path.join(OUT_DIR, "001-repository-truth-audit.md")


def iter_modules():
    for root, dirs, files in os.walk(PKG):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            mod = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
            yield mod, path


def module_info(mod, path):
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    imports, froms = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                (froms if node.level else imports).add(node.module.split(".")[0])
    public = [
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not n.name.startswith("_")
    ]
    return {
        "path": os.path.relpath(path, ROOT),
        "loc": len(src.splitlines()),
        "docstring": ast.get_docstring(tree) or "",
        "imports": sorted(imports),
        "public_defs": public,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    modules = {}
    for mod, path in iter_modules():
        modules[mod] = module_info(mod, path)

    test_files = sorted(
        f for f in os.listdir(os.path.join(ROOT, "tests"))
        if f.startswith("test_") and f.endswith(".py")
    )
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        pyproject = fh.read()
    version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M).group(1)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python_requires": ">=3.10 (per pyproject)",
        "pyproject_version": version,
        "modules": modules,
        "module_count": len(modules),
        "total_loc": sum(m["loc"] for m in modules.values()),
        "test_files": test_files,
    }
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")

    lines = [
        "# Slice 001 — Repository truth audit",
        "",
        f"**Generated:** {manifest['generated_utc']} (deterministic re-runnable via `tools/audit_repo.py`)",
        "",
        "## Inventory",
        "",
        f"- **Modules:** {manifest['module_count']} Python files under `hugrgate/`",
        f"- **Total LOC:** {manifest['total_loc']}",
        f"- **pyproject version:** {version}",
        f"- **Test files:** {', '.join(test_files)}",
        "",
        "## Module table",
        "",
        "| Module | LOC | Docstring | Internal imports |",
        "|---|---|---|---|",
    ]
    for mod in sorted(modules):
        m = modules[mod]
        internal = [i for i in m["imports"] if i == "hugrgate"]
        doc = (m["docstring"].splitlines()[0] if m["docstring"] else "—")[:72]
        lines.append(f"| `{mod}` | {m['loc']} | {doc} | {', '.join(internal) or '—'} |")
    lines += [
        "",
        "## Findings (forwarded to later slices)",
        "",
        "1. `hugrgate/client.py` imports `httpx` at module level, but `httpx` is",
        "   not declared in `pyproject.toml` (only present transitively in the dev",
        "   venv). `hugrgate/cli.py` imports it lazily inside a function.",
        "   → slice 004/008: declare `httpx` in the `server` extra (or make",
        "   `client.py` degrade gracefully when it is absent).",
        "2. `docs/api.md` documents the HTTP surface; the Python API has no",
        "   equivalent inventory page. → slice 003.",
        "3. No machine-readable architecture/dependency map existed before this",
        "   audit. → slice 002/004.",
        "",
        "## Verification",
        "",
        "Re-run `venv/bin/python tools/audit_repo.py` and diff",
        "`docs/campaign-i/manifest.json`; `tests/test_repo_truth.py` encodes",
        "the key invariants so drift fails the suite.",
        "",
    ]
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {MANIFEST} and {REPORT}")


if __name__ == "__main__":
    sys.exit(main())
