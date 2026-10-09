#!/usr/bin/env python3
"""Static security scan. Slice 423.

Complements the secret-handling audit (slice 421): where that
module audits *secret* mishandling, this tool scans for
*code-execution and sandbox-escape* patterns — ``eval``/``exec``,
unsafe deserialization, ``shell=True``, ``os.system``,
unverified SSL contexts, weak hashes, world-writable chmods, and
insecure tempfiles.

Usage:
    python tools/secscan.py [root] [--format text|json] [--fail-on high]

Exit code is 0 unless ``--fail-on`` severity (default: high)
findings exist. Findings inside ``tests/`` are reported as
informational: fixtures legitimately exercise hostile code.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class SecFinding:
    path: str
    line: int
    rule: str
    severity: str
    message: str


def _downgrade(path: Path, severity: str) -> str:
    if "tests" in path.parts and severity in ("high", "medium"):
        return "info"
    return severity


def _is_hostile_fixture(path: Path) -> bool:
    """Files that are *deliberately* hostile attack fixtures.

    Opt-in via a ``secscan: hostile-fixture`` marker in the first
    five lines (e.g. the slice-415 malicious-backend gauntlet).
    Their findings are reported as informational: the hostility is
    the point.
    """
    try:
        with open(path, encoding="utf-8") as f:
            head = []
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                head.append(line)
    except (OSError, UnicodeDecodeError):
        return False
    return any("secscan: hostile-fixture" in line for line in head)


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[SecFinding] = []
        self._hostile = _is_hostile_fixture(path)

    def _add(self, node: ast.AST, rule: str, severity: str,
             message: str) -> None:
        if self._hostile:
            severity = "info"
            message += " [hostile fixture: hostility is intentional]"
        self.findings.append(SecFinding(
            path=str(self.path),
            line=getattr(node, "lineno", 0),
            rule=rule,
            severity=_downgrade(self.path, severity),
            message=message))

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = ""
        dotted = ""
        if isinstance(func, ast.Name):
            name = dotted = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
            if isinstance(func.value, ast.Name):
                dotted = f"{func.value.id}.{func.attr}"

        # Rule: dynamic code execution. Note: re.compile() is regex
        # compilation, not code execution — only the bare builtin
        # counts.
        if name in ("eval", "exec") or dotted == "compile":
            self._add(node, "dynamic_code_exec", "high",
                      f"{dotted}() executes dynamically built code")
        # Rule: unsafe deserialization.
        if dotted in ("pickle.loads", "pickle.load",
                      "cPickle.loads", "marshal.loads",
                      "shelve.open"):
            self._add(node, "unsafe_deserialization", "high",
                      f"{dotted}() on untrusted data is arbitrary code "
                      "execution (use hugrgate.security.serde_guards)")
        if dotted == "yaml.load" and not any(
                kw.arg == "Loader" for kw in node.keywords):
            self._add(node, "unsafe_deserialization", "high",
                      "yaml.load() without Loader executes arbitrary "
                      "Python objects")
        # Rule: shell execution.
        if dotted == "os.system":
            self._add(node, "shell_execution", "high",
                      "os.system() invokes a shell; use subprocess with "
                      "an argument list")
        if name in ("Popen", "call", "run", "check_output",
                    "check_call") and any(
                kw.arg == "shell" and isinstance(kw.value, ast.Constant)
                and kw.value.value is True for kw in node.keywords):
            self._add(node, "shell_execution", "high",
                      f"subprocess {name}(shell=True) invokes a shell")
        # Rule: unverified TLS contexts.
        if dotted in ("ssl._create_unverified_context",):
            self._add(node, "tls_unverified_context", "high",
                      "unverified SSL context disables certificate "
                      "validation")
        # Rule: weak hashes (non-security use is fine, hence medium).
        if dotted in ("hashlib.md5", "hashlib.sha1"):
            used_for_security = any(
                kw.arg == "usedforsecurity" for kw in node.keywords)
            if not used_for_security:
                self._add(node, "weak_hash", "medium",
                          f"{dotted}() is cryptographically broken; use "
                          "sha256 unless this is a non-security checksum")
        # Rule: world-writable permissions.
        if dotted == "os.chmod":
            for arg in node.args[1:]:
                if (isinstance(arg, ast.Constant)
                        and isinstance(arg.value, int)
                        and arg.value & 0o077):
                    self._add(node, "world_writable_chmod", "medium",
                              f"os.chmod({oct(arg.value)}) grants "
                              "group/other access")
        # Rule: insecure temporary files.
        if dotted == "tempfile.mktemp":
            self._add(node, "insecure_tempfile", "medium",
                      "tempfile.mktemp() is racy; use mkstemp() or "
                      "TemporaryFile()")
        self.generic_visit(node)


def scan_file(path: Path) -> list[SecFinding]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"),
                         filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    visitor = _Visitor(path)
    visitor.visit(tree)
    return visitor.findings


def scan_tree(root: Path,
              exclude: tuple[str, ...] = (".venv", "venv", "__pycache__",
                                          ".git", "node_modules")) \
        -> list[SecFinding]:
    findings: list[SecFinding] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in exclude for part in path.parts):
            continue
        findings.extend(scan_file(path))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(REPO_ROOT))
    parser.add_argument("--format", choices=("text", "json"),
                        default="text")
    parser.add_argument("--fail-on",
                        choices=("high", "medium", "low", "never"),
                        default="high")
    args = parser.parse_args(argv)

    root = Path(args.root)
    findings = scan_file(root) if root.is_file() else scan_tree(root)
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (order[f.severity], f.path, f.line))

    if args.format == "json":
        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        for f in findings:
            print(f"{f.severity:6} {f.path}:{f.line} "
                  f"[{f.rule}] {f.message}")
        print(f"\n{len(findings)} finding(s)")

    threshold = order[args.fail_on] if args.fail_on != "never" else 99
    bad = [f for f in findings if order[f.severity] <= threshold]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
