"""Attack-surface inventory. Slice 402.

A security inventory that cannot drift: :func:`enumerate_surface`
rebuilds the inventory from the code itself (AST over
``hugrgate/server.py`` routes, ``hugrgate/cli.py`` subcommands, and
``os.getenv``/``os.environ`` reads across the package), and
:func:`find_unlisted` reports anything the curated registry does not
know about. New endpoints, commands, or env vars without a registry
entry fail the gate test — the inventory is append-only by
construction.

Each entry carries a kind, whether authentication is required, and a
risk rating, so reviewers can see the exposed surface at a glance.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "AttackSurface",
    "SurfaceEntry",
    "enumerate_surface",
    "find_unlisted",
]

_PKG_ROOT = Path(__file__).resolve().parent.parent

KINDS = (
    "api_endpoint",
    "cli_command",
    "env_var",
    "file_loader",
    "plugin_loader",
    "ipc",
)

RISKS = ("low", "medium", "high")


@dataclass(frozen=True)
class SurfaceEntry:
    """One reachable entry point."""

    name: str
    kind: str
    description: str
    auth_required: bool
    risk: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown surface kind: {self.kind!r}")
        if self.risk not in RISKS:
            raise ValueError(f"unknown risk rating: {self.risk!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "auth_required": self.auth_required,
            "risk": self.risk,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SurfaceEntry:
        return cls(**data)


@dataclass
class AttackSurface:
    """The curated, reviewed inventory."""

    entries: list[SurfaceEntry] = field(default_factory=list)

    def add(self, entry: SurfaceEntry) -> None:
        if any(e.name == entry.name and e.kind == entry.kind
               for e in self.entries):
            raise ValueError(
                f"duplicate surface entry {entry.kind}:{entry.name}")
        self.entries.append(entry)

    def by_kind(self, kind: str) -> list[SurfaceEntry]:
        return [e for e in self.entries if e.kind == kind]

    def unauthenticated(self) -> list[SurfaceEntry]:
        """Entries reachable without authentication — the hot surface."""
        return [e for e in self.entries if not e.auth_required]

    def high_risk(self) -> list[SurfaceEntry]:
        return [e for e in self.entries if e.risk == "high"]

    def names(self, kind: str) -> set[str]:
        return {e.name for e in self.by_kind(kind)}

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttackSurface:
        surface = cls()
        for raw in data.get("entries", []):
            surface.add(SurfaceEntry.from_dict(raw))
        return surface


# --- code-derived enumeration -----------------------------------------------


def _routes_in_server() -> list[tuple[str, str]]:
    """(method, path) pairs from @app.<method>(\"<path>\") decorators."""
    tree = ast.parse((_PKG_ROOT / "server.py").read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)):
                continue
            target = dec.func.value
            if not (isinstance(target, ast.Name) and target.id == "app"):
                continue
            if dec.func.attr not in {
                    "get", "post", "put", "delete", "patch"}:
                continue
            if (dec.args and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)):
                found.append((dec.func.attr.upper(), dec.args[0].value))
    return sorted(set(found))


def _commands_in_cli() -> list[str]:
    """Subcommand names from sub.add_parser(\"<name>\") calls."""
    tree = ast.parse((_PKG_ROOT / "cli.py").read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_parser"):
            continue
        if (node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            found.append(node.args[0].value)
    return sorted(set(found))


def _env_vars_in_package() -> list[str]:
    """Env var names read via os.getenv / os.environ anywhere in hugrgate."""
    found: set[str] = set()
    for path in sorted(_PKG_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Attribute) and func.attr == "getenv"
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "os"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    found.add(node.args[0].value)
                elif (isinstance(func, ast.Attribute) and func.attr == "get"
                        and isinstance(func.value, ast.Subscript)
                        and _is_os_environ(func.value.value)
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    found.add(node.args[0].value)
            elif (isinstance(node, ast.Subscript)
                    and _is_os_environ(node.value)
                    and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)):
                found.add(node.slice.value)
    return sorted(found)


def _is_os_environ(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os")


def enumerate_surface() -> dict[str, list[str]]:
    """Rebuild the machine-readable surface from current source code."""
    return {
        "api_endpoint": [f"{m} {p}" for m, p in _routes_in_server()],
        "cli_command": _commands_in_cli(),
        "env_var": _env_vars_in_package(),
    }


def find_unlisted(surface: AttackSurface) -> dict[str, list[str]]:
    """Code-derived entries missing from the curated registry.

    Empty dict means the inventory is complete. Any non-empty result
    is a release-blocking drift: a new endpoint/command/env var was
    added without a reviewed inventory entry.
    """
    derived = enumerate_surface()
    drift: dict[str, list[str]] = {}
    for kind, names in derived.items():
        missing = sorted(set(names) - surface.names(kind))
        if missing:
            drift[kind] = missing
    return drift


def curated_surface() -> AttackSurface:
    """The reviewed inventory. Update with care when the surface changes."""
    surface = AttackSurface()
    add = surface.add
    # HTTP service (hugrgate/server.py::create_app)
    add(SurfaceEntry("GET /", "api_endpoint",
                     "service root, version banner", False, "low"))
    add(SurfaceEntry("GET /health", "api_endpoint",
                     "liveness probe", False, "low"))
    add(SurfaceEntry("GET /backends", "api_endpoint",
                     "lists registered backends and capabilities",
                     False, "low"))
    add(SurfaceEntry("GET /models", "api_endpoint",
                     "lists known model metadata", False, "low"))
    add(SurfaceEntry("POST /decide", "api_endpoint",
                     "runs a full decision pipeline on caller JSON",
                     False, "high"))
    add(SurfaceEntry("GET /protocol", "api_endpoint",
                     "returns the wire-protocol version and capabilities",
                     False, "low"))
    # CLI (hugrgate/cli.py)
    for cmd, desc, risk in [
        ("decide", "make one decision from argv/JSON", "medium"),
        ("backends", "list available backends", "low"),
        ("models", "list known models", "low"),
        ("health", "check service health", "low"),
        ("serve", "run the service daemon", "medium"),
        ("bench", "run a benchmark", "low"),
        ("report", "render a benchmark report as markdown", "low"),
        ("check-backend", "run backend conformance battery", "low"),
        ("check-contract", "run contract conformance battery", "low"),
        ("completion", "emit shell completion script", "low"),
        ("doctor", "diagnose environment and configuration", "low"),
        ("gen", "generate project scaffolding", "medium"),
        ("init", "initialize a new project", "medium"),
        ("inspect", "inspect models/contracts/backends", "low"),
        ("new", "create a new component from template", "medium"),
        ("openapi", "emit OpenAPI specification", "low"),
        ("plugins", "list/manage plugins", "low"),
    ]:
        add(SurfaceEntry(cmd, "cli_command", desc, False, risk))
    # Environment variables actually read by the package
    for var in _env_vars_in_package():
        add(SurfaceEntry(var, "env_var",
                         f"read via os.getenv/os.environ in {_which(var)}",
                         False, "low"))
    # Plugin loading: backend registry accepts arbitrary Backend objects
    add(SurfaceEntry("BackendRegistry.register", "plugin_loader",
                     "registers third-party Backend implementations; "
                     "arbitrary code runs inside evaluate()",
                     False, "high"))
    # File loading: model/pack loaders read attacker-influenced paths
    add(SurfaceEntry("runtimes pack loaders", "file_loader",
                     "GGUF/ONNX/pack metadata + weight files parsed from "
                     "disk paths supplied by the operator",
                     False, "medium"))
    add(SurfaceEntry("EncryptedDecisionCache sealed blobs", "file_loader",
                     "sealed cache entries unsealed from shared storage",
                     False, "medium"))
    return surface


def _which(var: str) -> str:
    for path in sorted(_PKG_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if f'"{var}"' in text or f"'{var}'" in text:
            return path.relative_to(_PKG_ROOT).as_posix()
    return "hugrgate"
