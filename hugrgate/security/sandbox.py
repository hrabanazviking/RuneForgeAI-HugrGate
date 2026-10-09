"""Backend sandbox boundary. Slice 408.

A malicious or buggy backend runs arbitrary Python inside
``evaluate()`` (threat T-11). This module draws a real boundary
around that call using :func:`sys.addaudithook`: while a sandbox is
active on the current thread, audited operations outside the policy
— subprocess execution, network access, filesystem writes — are
denied by raising :class:`SandboxViolation` *before* the operation
runs.

- :class:`SandboxPolicy` — what the sandbox permits (deny by
  default; ``allow_subprocess`` / ``allow_network`` /
  ``allow_filesystem_write`` opt back in).
- :func:`run_sandboxed` — context manager / decorator enforcing a
  policy on the current thread; nestable, innermost wins.
- :class:`SandboxedBackend` — a :class:`Backend` wrapper that runs
  ``evaluate()`` (and ``warmup()``) inside the policy, converting
  violations into taxonomy errors instead of side effects.

The audit hook is installed once per process and consults
thread-local state, so unsandboxed threads pay only a pointer
check. This is a *syscall-class* boundary, not a bulletproof
jail: it stops accidental and opportunistic abuse (the threat
model's scope), not a determined interpreter-level escape.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import SandboxViolation
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "SandboxPolicy",
    "SandboxedBackend",
    "run_sandboxed",
    "sandboxed",
]

#: Audit events that constitute "run a subprocess".
_SUBPROCESS_EVENTS = frozenset({
    "os.system",
    "os.execv", "os.execve", "os.execl", "os.execle", "os.execlp",
    "os.execlpe", "os.execvp", "os.execvpe",
    "os.spawnl", "os.spawnle", "os.spawnlp", "os.spawnlpe",
    "os.spawnv", "os.spawnve", "os.spawnvp", "os.spawnvpe",
    "os.posix_spawn", "os.posix_spawnp",
    "os.fork", "os.forkpty",
    "subprocess.Popen",
})

#: Audit events that constitute "touch the network".
_NETWORK_EVENTS = frozenset({
    "socket.getaddrinfo",
    "socket.gethostbyname", "socket.gethostbyname_ex",
    "socket.getnameinfo",
    "socket.bind",
    "socket.connect",
})

_WRITE_MODES = ("w", "a", "x", "+")


@dataclass(frozen=True)
class SandboxPolicy:
    """What a sandboxed backend is allowed to do. Deny by default."""

    allow_subprocess: bool = False
    allow_network: bool = False
    allow_filesystem_write: bool = False

    def describe(self) -> dict[str, bool]:
        return {
            "subprocess": self.allow_subprocess,
            "network": self.allow_network,
            "filesystem_write": self.allow_filesystem_write,
        }


_state = threading.local()


def _stack() -> list[SandboxPolicy]:
    stack = getattr(_state, "stack", None)
    if stack is None:
        stack = _state.stack = []
    return stack


def _active_policy() -> SandboxPolicy | None:
    stack = _stack()
    return stack[-1] if stack else None


def _is_write_open(args: tuple) -> bool:
    if len(args) < 2:
        return False
    mode = args[1]
    return isinstance(mode, str) and any(m in mode for m in _WRITE_MODES)


def _audit_hook(event: str, args: tuple) -> None:
    policy = _active_policy()
    if policy is None:
        return
    if event in _SUBPROCESS_EVENTS and not policy.allow_subprocess:
        raise SandboxViolation(
            f"sandbox denies subprocess event {event!r}",
            event=event, category="subprocess")
    if event in _NETWORK_EVENTS and not policy.allow_network:
        raise SandboxViolation(
            f"sandbox denies network event {event!r}",
            event=event, category="network")
    if (event == "open" and not policy.allow_filesystem_write
            and _is_write_open(args)):
        raise SandboxViolation(
            f"sandbox denies filesystem write ({args[0]!r})",
            event=event, category="filesystem_write")


_hook_installed = False
_hook_lock = threading.Lock()


def _ensure_hook() -> None:
    global _hook_installed
    with _hook_lock:
        if not _hook_installed:
            sys.addaudithook(_audit_hook)
            _hook_installed = True


@contextmanager
def run_sandboxed(policy: SandboxPolicy) -> Iterator[SandboxPolicy]:
    """Enforce ``policy`` on the current thread for the block."""
    _ensure_hook()
    _stack().append(policy)
    try:
        yield policy
    finally:
        _stack().pop()


def sandboxed(policy: SandboxPolicy) -> Callable:
    """Decorator version of :func:`run_sandboxed`."""
    def decorator(fn: Callable) -> Callable:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with run_sandboxed(policy):
                return fn(*args, **kwargs)
        wrapper.__name__ = getattr(fn, "__name__", "sandboxed")
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator


class SandboxedBackend(Backend):
    """A backend whose ``evaluate``/``warmup`` run inside a sandbox.

    Violations surface as :class:`SandboxViolation` (a taxonomy
    error) instead of happening. Non-violating backends behave
    exactly as the wrapped backend.
    """

    def __init__(self, backend: Backend,
                 policy: SandboxPolicy | None = None) -> None:
        self._backend = backend
        self._policy = policy or SandboxPolicy()
        self.name = f"sandboxed({backend.name})"
        self.is_remote = backend.is_remote

    @property
    def wrapped(self) -> Backend:
        return self._backend

    @property
    def policy(self) -> SandboxPolicy:
        return self._policy

    def capabilities(self) -> dict[str, Any]:
        caps = dict(self._backend.capabilities())
        caps["sandbox"] = self._policy.describe()
        return caps

    def supports(self, spec: DecisionSpec) -> bool:
        return self._backend.supports(spec)

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        with run_sandboxed(self._policy):
            return self._backend.evaluate(state, spec, context)

    def warmup(self) -> None:
        with run_sandboxed(self._policy):
            self._backend.warmup()

    def health(self) -> dict[str, Any]:
        status = dict(self._backend.health())
        status["sandbox"] = self._policy.describe()
        return status

    def close(self) -> None:
        self._backend.close()
