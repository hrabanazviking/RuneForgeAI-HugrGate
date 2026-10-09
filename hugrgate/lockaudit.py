"""Lock contention audit — instrumented locks and static lock-site audit.

Slice 293. Two tools:

- :class:`InstrumentedLock`: a drop-in wrapper for
  :class:`threading.Lock` / :class:`threading.RLock` that records
  acquisition count, total/mean/max *wait* time (contention) and
  *hold* time per lock instance.  Wrap a suspect lock, run the
  workload, read :meth:`InstrumentedLock.report`.
- :func:`audit_locks`: an AST pass over the ``hugrgate`` package that
  finds every ``with <lock>:`` critical section and flags:
  ``call-in-critical-section`` (method calls while holding a lock —
  each is a potential long hold or a lock-order edge),
  ``nested-lock`` (a second lock acquired inside a critical section —
  the classic deadlock shape), and ``blocking-call`` (``sleep`` /
  I/O / ``join`` / ``wait`` inside a critical section).

Findings from the first audit are recorded in
``docs/campaign-xii/293-lock-contention-audit.md``; the audit fixed
the highest-contention site it found (``DecisionCache`` key/copy work
hoisted out of the lock).
"""

from __future__ import annotations

import ast
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "Finding",
    "InstrumentedLock",
    "audit_locks",
]


class InstrumentedLock:
    """A Lock/RLock wrapper measuring contention and hold time.

    Drop-in: exposes ``acquire``, ``release``, ``__enter__`` /
    ``__exit__``, and ``locked``.  ``kind`` is ``"lock"`` or
    ``"rlock"``.  Overhead is two ``perf_counter`` calls per
    acquisition — do not leave wrapped in the hottest paths in
    production; use it to *find* the hot lock, then fix the hold.
    """

    def __init__(self, name: str, kind: str = "rlock") -> None:
        if kind not in ("lock", "rlock"):
            raise ValueError(f"kind must be 'lock' or 'rlock', got {kind!r}")
        self._name = name
        self._inner = threading.RLock() if kind == "rlock" \
            else threading.Lock()
        self._guard = threading.Lock()
        self._depth = 0  # held-count (RLock exposes no locked())
        self.acquisitions = 0
        self.total_wait_s = 0.0
        self.total_hold_s = 0.0
        self.max_wait_s = 0.0
        self.max_hold_s = 0.0

    @property
    def name(self) -> str:
        return self._name

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        t0 = time.perf_counter()
        ok = self._inner.acquire(blocking, timeout)
        waited = time.perf_counter() - t0
        if ok:
            with self._guard:
                self.acquisitions += 1
                self.total_wait_s += waited
                self.max_wait_s = max(self.max_wait_s, waited)
                self._depth += 1
            # Stamp hold-start on the instance without touching the
            # wrapped lock's state: RLock re-entry needs a stack.
            stack = getattr(self, "_hold_stack", None)
            if stack is None:
                stack = []
                object.__setattr__(self, "_hold_stack", stack)
            stack.append(time.perf_counter())
        return ok

    def release(self) -> None:
        stack = getattr(self, "_hold_stack", None)
        started = stack.pop() if stack else time.perf_counter()
        held = time.perf_counter() - started
        with self._guard:
            self.total_hold_s += held
            self.max_hold_s = max(self.max_hold_s, held)
            self._depth = max(0, self._depth - 1)
        self._inner.release()

    def __enter__(self) -> InstrumentedLock:
        self.acquire()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()

    def locked(self) -> bool:
        with self._guard:
            return self._depth > 0

    def report(self) -> dict[str, Any]:
        """Snapshot of contention statistics."""
        with self._guard:
            n = self.acquisitions
            return {
                "name": self._name,
                "acquisitions": n,
                "total_wait_s": self.total_wait_s,
                "mean_wait_us": (self.total_wait_s / n * 1e6) if n else 0.0,
                "max_wait_us": self.max_wait_s * 1e6,
                "total_hold_s": self.total_hold_s,
                "mean_hold_us": (self.total_hold_s / n * 1e6) if n else 0.0,
                "max_hold_us": self.max_hold_s * 1e6,
            }


@dataclass
class Finding:
    """One flagged critical section."""
    path: str
    lineno: int
    function: str
    lock_expr: str
    kind: str  # "call-in-critical-section" | "nested-lock" | "blocking-call"
    detail: str


_BLOCKING_CALLS = {
    "sleep", "wait", "join", "input", "recv", "send", "read", "write",
    "connect", "accept", "request", "get", "post", "put", "delete",
    "acquire",  # blocking acquire inside a critical section
}


def _is_lock_with(node: ast.With) -> str | None:
    """Return the lock expression source if this `with` guards a lock."""
    if len(node.items) != 1:
        return None
    expr = node.items[0].context_expr
    src = ast.unparse(expr)
    lowered = src.lower()
    if "lock" in lowered or "cond" in lowered or "sema" in lowered:
        return src
    return None


def _calls_in(node: ast.AST) -> list[tuple[str, str, int]]:
    """All call expressions under node: (receiver source, attr, lineno).

    ``receiver`` is "" for bare-name calls like ``sleep(1)``.
    """
    found: list[tuple[str, str, int]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute):
                found.append((ast.unparse(func.value), func.attr,
                              child.lineno))
            elif isinstance(func, ast.Name):
                found.append(("", func.id, child.lineno))
    return found


@dataclass
class _AuditState:
    findings: list[Finding] = field(default_factory=list)
    sections: int = 0  # total `with <lock>:` blocks found


def audit_locks(package_root: str | Path = "hugrgate") -> list[Finding]:
    """AST-audit every ``with <lock>:`` block under ``package_root``."""
    root = Path(package_root)
    state = _AuditState()
    for path in sorted(root.rglob("*.py")):
        if any(part == "tests" for part in path.parts) \
                or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError) as e:
            logger.warning("audit: cannot parse %s: %s", path, e)
            continue
        _audit_tree(path, tree, state)
    logger.info("audit: %d critical sections, %d findings",
                state.sections, len(state.findings))
    return state.findings


def _audit_tree(path: Path, tree: ast.Module, state: _AuditState) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.With):
                continue
            lock_expr = _is_lock_with(child)
            if lock_expr is None:
                continue
            state.sections += 1
            _audit_section(path, node.name, child, lock_expr, state)


def _audit_section(path: Path, func: str, node: ast.With,
                   lock_expr: str, state: _AuditState) -> None:
    loc = f"{path}:{node.lineno}"

    def add(kind: str, detail: str, lineno: int) -> None:
        state.findings.append(Finding(
            path=str(path), lineno=lineno, function=func,
            lock_expr=lock_expr, kind=kind, detail=detail))

    for stmt in node.body:
        for child in ast.walk(stmt):
            if isinstance(child, ast.With) and child is not node:
                inner = _is_lock_with(child)
                if inner is not None:
                    add("nested-lock",
                        f"{loc} acquires {inner} while holding "
                        f"{lock_expr} — lock-order edge", child.lineno)
    for recv, name, lineno in _calls_in(node):
        # The `with` statement's own context expression was already
        # walked; skip the lock's acquire/__enter__ itself, and skip
        # condition-variable protocol calls on the *held* lock
        # (cond.wait()/notify() inside `with cond:` is correct usage).
        if name in ("__enter__", "__exit__"):
            continue
        if recv == lock_expr and name in ("wait", "wait_for", "notify",
                                          "notify_all"):
            continue
        if name in _BLOCKING_CALLS:
            add("blocking-call",
                f"{loc} calls {name}() while holding {lock_expr}",
                lineno)
        else:
            # Heuristic: any call inside a critical section extends the
            # hold; flag it so the owner can justify or hoist it.
            add("call-in-critical-section",
                f"{loc} calls {name}() while holding {lock_expr}",
                lineno)


def summarize(findings: list[Finding]) -> dict[str, Any]:
    """Count findings by kind and by file."""
    by_kind: dict[str, int] = {}
    by_file: dict[str, int] = {}
    for f in findings:
        by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
        by_file[f.path] = by_file.get(f.path, 0) + 1
    return {"total": len(findings), "by_kind": by_kind,
            "by_file": dict(sorted(by_file.items(),
                                   key=lambda kv: kv[1], reverse=True)[:15])}
