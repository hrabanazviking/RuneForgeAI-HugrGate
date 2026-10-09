"""Secret-handling audit. Slice 421.

Slice 234 catches secrets in *outbound data*. This module audits
the *codebase itself*: hardcoded credentials, secrets in log
calls, secrets in URLs, disabled TLS verification, secrets in
exception messages, weak randomness for secret material, and
default secrets in environment lookups.

The auditor is AST-based (:func:`audit_file`, :func:`audit_tree`)
and returns :class:`SecretAuditFinding` records with rule,
severity, and location. It is deliberately conservative — every
rule names a concrete mishandling pattern — and findings inside
``tests/`` are downgraded to informational (fixtures legitimately
use fake secrets).

The companion test runs the auditor over the real ``hugrgate/``
tree and asserts zero high-severity findings: the audit is a
standing gate, not a one-off report.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "SECRET_NAME_RE",
    "SecretAuditFinding",
    "audit_file",
    "audit_tree",
    "run_secret_audit",
]

#: Variable/argument names that suggest secret material. Deliberately
#: narrow: bare ``key``/``token`` appear in legitimate code (cache
#: keys, sealed tokens) and would drown the signal.
SECRET_NAME_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret|api[_-]?key|apikey|"
    r"auth[_-]?token|access[_-]?token|private[_-]?key|"
    r"client[_-]?secret|bearer)")

#: String literals shaped like credentials in URLs.
URL_SECRET_RE = re.compile(
    r"(?i)https?://[^/\s'\"]*:[^/\s'\"]*@|"
    r"[?&](password|secret|api[_-]?key|token)=", )


@dataclass
class SecretAuditFinding:
    path: str
    line: int
    rule: str
    severity: str  # "high" | "medium" | "low" | "info"
    message: str
    snippet: str = ""


def _is_test_path(path: Path) -> bool:
    return "tests" in path.parts or path.name.startswith("test_")


def _downgrade(path: Path, severity: str) -> str:
    if _is_test_path(path) and severity in ("high", "medium"):
        return "info"
    return severity


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[SecretAuditFinding] = []
        self._source_lines: list[str] = []

    def _add(self, node: ast.AST, rule: str, severity: str,
             message: str) -> None:
        line = getattr(node, "lineno", 0)
        snippet = ""
        if 0 < line <= len(self._source_lines):
            snippet = self._source_lines[line - 1].strip()[:120]
        self.findings.append(SecretAuditFinding(
            path=str(self.path), line=line, rule=rule,
            severity=_downgrade(self.path, severity),
            message=message, snippet=snippet))

    def _name_matches(self, name: str) -> bool:
        return bool(SECRET_NAME_RE.search(name))

    # -- rules -----------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            value = node.value
            # Rule: credential material embedded in a URL literal,
            # wherever the literal sits.
            if (isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and URL_SECRET_RE.search(value.value)):
                self._add(node, "secret_in_url", "high",
                          "credential material embedded in a URL")
            if isinstance(target, ast.Name) and self._name_matches(
                    target.id):
                if isinstance(value, ast.Constant) and isinstance(
                        value.value, str) and value.value:
                    # UPPER_CASE constants holding a simple code slug
                    # (e.g. EVENT_SECRET_DETECTED = "secret_detected")
                    # are event names, not credentials; an opaque
                    # value in such a constant stays suspicious.
                    if target.id.isupper() and re.fullmatch(
                            r"[a-z][a-z0-9_]*", value.value):
                        continue
                    self._add(node, "hardcoded_secret", "high",
                              f"hardcoded secret assigned to {target.id!r}")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        value = node.value
        if (isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and URL_SECRET_RE.search(value.value)):
            self._add(node, "secret_in_url", "high",
                      "credential material embedded in a URL")
        if (isinstance(node.target, ast.Name)
                and self._name_matches(node.target.id)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and node.value.value
                and not (node.target.id.isupper() and re.fullmatch(
                    r"[a-z][a-z0-9_]*", node.value.value))):
            self._add(node, "hardcoded_secret", "high",
                      f"hardcoded secret assigned to {node.target.id!r}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        func_name = ""
        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr

        # Rule: secrets passed to logging/print calls.
        if func_name in ("debug", "info", "warning", "warn", "error",
                         "critical", "exception", "print", "log"):
            for arg in (*node.args, *[k.value for k in node.keywords]):
                if self._expr_mentions_secret(arg):
                    self._add(node, "secret_in_log", "high",
                              f"possible secret material in {func_name}() "
                              "call")

        # Rule: verify=False disables TLS verification.
        for kw in node.keywords:
            if (kw.arg == "verify" and isinstance(kw.value, ast.Constant)
                    and kw.value.value is False):
                self._add(node, "tls_disabled", "high",
                          "TLS verification disabled (verify=False)")

        # Rule: weak randomness for secret material.
        if (isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "random"
                and func.attr in ("random", "choice", "randrange",
                                  "randint", "uniform")):
            self._add(node, "weak_secret_gen", "medium",
                      f"random.{func.attr}() is not cryptographic "
                      "randomness; use the secrets module for secrets")

        # Rule: os.environ.get("X", <non-empty default>).
        if (func_name == "get" and isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "environ"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value):
            self._add(node, "env_default_secret", "medium",
                      "non-empty default secret in os.environ.get()")

        # Rule: secret-shaped credentials embedded in URL literals.
        for arg in (*node.args, *[k.value for k in node.keywords]):
            if (isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and URL_SECRET_RE.search(arg.value)):
                self._add(node, "secret_in_url", "high",
                          "credential material embedded in a URL")

        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        # Inspect the exception *arguments*, not the exception class
        # itself (a class named e.g. SecretDetected is not a leak).
        if node.exc is not None and isinstance(node.exc, ast.Call):
            args = [*node.exc.args,
                    *(k.value for k in node.exc.keywords)]
            if any(self._expr_mentions_secret(a) for a in args):
                self._add(node, "secret_in_exception", "medium",
                          "possible secret value interpolated into an "
                          "exception message")
        self.generic_visit(node)

    def _expr_mentions_secret(self, expr: ast.AST) -> bool:
        """True when the expression references a secret-named value."""
        for child in ast.walk(expr):
            if isinstance(child, ast.Name) and self._name_matches(
                    child.id):
                return True
            if (isinstance(child, ast.Constant)
                    and isinstance(child.value, str)
                    and len(child.value) >= 12
                    and URL_SECRET_RE.search(child.value)):
                return True
        return False


def audit_file(path: str | Path) -> list[SecretAuditFinding]:
    """Audit one Python file; return its findings."""
    path = Path(path)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    visitor = _Visitor(path)
    visitor._source_lines = source.splitlines()
    visitor.visit(tree)
    return visitor.findings


def audit_tree(root: str | Path,
               exclude: tuple[str, ...] = (".venv", "venv", "__pycache__",
                                           ".git", "node_modules")) \
        -> list[SecretAuditFinding]:
    """Audit every ``*.py`` file under ``root``."""
    root = Path(root)
    findings: list[SecretAuditFinding] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in exclude for part in path.parts):
            continue
        findings.extend(audit_file(path))
    return findings


def run_secret_audit(root: str | Path = ".") -> dict[str, Any]:
    """Run the audit and summarize by severity."""
    findings = audit_tree(root)
    by_severity: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity] = \
            by_severity.get(finding.severity, 0) + 1
    return {
        "findings": findings,
        "by_severity": by_severity,
        "high": [f for f in findings if f.severity == "high"],
    }
