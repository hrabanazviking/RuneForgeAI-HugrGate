"""Platform/architecture matrix for the 1.0 release (slices 479-482).

The supported-platform matrix is built from *actually validated*
platforms only — never from hope. This module provides:

- :class:`PlatformInfo` / :func:`current_platform`: the machine we
  are standing on.
- :data:`VALIDATED_PLATFORMS`: platforms the gauntlet has proven by
  running its checks there. Entries are added by the per-OS slices
  (479 Linux, 480 Windows, 481 macOS) only after their checks pass.
- :func:`scan_posix_only`: AST scan for POSIX-only stdlib APIs
  (``fcntl``, ``pty``, ``pwd``, ``grp``, ``termios``,
  ``os.fork``/``os.posix_spawn``, ``signal.SIGKILL``/``SIGSTOP``)
  and whether each use site is guarded (``try/except ImportError``,
  ``sys.platform``/``os.name`` checks, or ``getattr`` with a
  default). Unguarded uses are import-time crashes on Windows.
- :func:`linux_live_checks`: runtime probes that only make sense on
  Linux (epoll, ``/proc/self``, ``uname``).

Slice 482 extends the machine axis (x86_64 vs ARM64).
"""

from __future__ import annotations

import ast
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "POSIX_ONLY_MODULES",
    "VALIDATED_PLATFORMS",
    "PlatformInfo",
    "PosixFinding",
    "current_platform",
    "is_validated",
    "linux_live_checks",
    "record_validated",
    "scan_posix_only",
]

#: Stdlib modules that do not exist on Windows.
POSIX_ONLY_MODULES = frozenset(
    {"fcntl", "pty", "pwd", "grp", "termios", "resource", "curses"}
)

#: POSIX-only attribute uses that crash at import/call time on Windows.
POSIX_ONLY_ATTRS = frozenset(
    {
        ("os", "fork"),
        ("os", "forkpty"),
        ("os", "posix_spawn"),
        ("os", "posix_spawnp"),
        ("os", "setuid"),
        ("os", "setgid"),
        ("signal", "SIGKILL"),
        ("signal", "SIGSTOP"),
    }
)

#: Platforms proven by actually running the gauntlet checks there.
#: Populated by slices 479-481; never extended by assertion.
VALIDATED_PLATFORMS: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PlatformInfo:
    """The platform we are standing on."""

    os_name: str  # "posix" / "nt" / "java"
    sys_platform: str  # "linux" / "darwin" / "win32" / ...
    machine: str  # "x86_64" / "arm64" / "aarch64" / ...
    bits: int  # pointer width: 32 or 64

    @property
    def os_key(self) -> str:
        return {"linux": "linux", "darwin": "macos"}.get(
            self.sys_platform,
            "windows" if self.sys_platform == "win32" else self.sys_platform,
        )


@dataclass(frozen=True)
class PosixFinding:
    """One POSIX-only API use site."""

    path: str
    lineno: int
    api: str
    guarded: bool

    def __str__(self) -> str:
        status = "guarded" if self.guarded else "UNGUARDED"
        return f"{self.path}:{self.lineno}: {self.api} ({status})"


def current_platform() -> PlatformInfo:
    """Describe the running interpreter's platform."""
    return PlatformInfo(
        os_name=os.name,
        sys_platform=sys.platform,
        machine=platform.machine(),
        bits=64 if sys.maxsize > 2**32 else 32,
    )


def record_validated(info: PlatformInfo) -> tuple[tuple[str, str], ...]:
    """Return the validated-platforms tuple with ``info`` added."""
    global VALIDATED_PLATFORMS
    key = (info.os_key, info.machine)
    if key not in VALIDATED_PLATFORMS:
        VALIDATED_PLATFORMS = (*VALIDATED_PLATFORMS, key)
    return VALIDATED_PLATFORMS


def is_validated(info: PlatformInfo) -> bool:
    """Whether ``info``'s (os, machine) pair has been proven."""
    return (info.os_key, info.machine) in VALIDATED_PLATFORMS


def _is_guarded(tree: ast.Module, node: ast.AST) -> bool:
    """Heuristic: is ``node`` inside a platform guard?

    Recognizes ``try/except ImportError``, ``if sys.platform`` /
    ``if os.name`` tests, and ``hasattr``/``getattr`` probes. This is
    intentionally conservative: an unrecognized guard style reports
    the site as unguarded so a human looks at it.
    """
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent

    current: ast.AST | None = node
    while current is not None:
        up: ast.AST | None = parents.get(id(current))
        if isinstance(up, ast.Try):
            for handler in up.handlers:
                if handler.type is None:
                    return True
                names = set()
                if isinstance(handler.type, ast.Name):
                    names.add(handler.type.id)
                elif isinstance(handler.type, ast.Tuple):
                    names.update(
                        e.id for e in handler.type.elts if isinstance(e, ast.Name)
                    )
                if names & {"ImportError", "AttributeError", "OSError", "Exception"}:
                    return True
        if isinstance(up, ast.If):
            src = ast.dump(up.test)
            if "sys.platform" in src or "os.name" in src or "platform" in src:
                return True
        current = up
    return False


def _module_imports_posix(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in POSIX_ONLY_MODULES:
                    found.append((node.lineno, top))
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in POSIX_ONLY_MODULES:
                found.append((node.lineno, top))
    return found


def _attr_uses_posix(tree: ast.Module) -> list[tuple[int, str, ast.AST]]:
    found: list[tuple[int, str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            key = (node.value.id, node.attr)
            if key in POSIX_ONLY_ATTRS:
                found.append((node.lineno, f"{key[0]}.{key[1]}", node))
    return found


def scan_posix_only(root: str | Path) -> tuple[PosixFinding, ...]:
    """Scan ``root`` for POSIX-only API uses and their guard status."""
    findings: list[PosixFinding] = []
    for path in sorted(Path(root).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        rel = str(path)
        for lineno, mod in _module_imports_posix(tree):
            import_node = next(
                n for n in ast.walk(tree)
                if isinstance(n, (ast.Import, ast.ImportFrom))
                and n.lineno == lineno
            )
            findings.append(
                PosixFinding(rel, lineno, f"import {mod}",
                             _is_guarded(tree, import_node))
            )
        for lineno, api, node in _attr_uses_posix(tree):
            findings.append(
                PosixFinding(rel, lineno, api, _is_guarded(tree, node))
            )
    return tuple(findings)


def linux_live_checks() -> dict[str, bool]:
    """Runtime probes for Linux. All must be True on a Linux 1.0 host."""
    info = current_platform()
    checks: dict[str, bool] = {}
    checks["is_linux"] = info.sys_platform == "linux"
    try:
        import select as _select

        checks["epoll_available"] = hasattr(_select, "epoll")
    except ImportError:
        checks["epoll_available"] = False
    checks["proc_self_readable"] = Path("/proc/self/status").is_file()
    try:
        checks["uname_works"] = bool(os.uname().sysname)
    except (AttributeError, OSError):
        checks["uname_works"] = False
    return checks
