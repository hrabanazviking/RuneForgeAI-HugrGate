"""Deserialization hardening. Slice 411.

Audit result: ``hugrgate/backends/logreg.py`` called raw
``pickle.loads`` on model files whose integrity manifest is an
unsigned sidecar — an attacker who can write the model file can
rewrite the manifest too, making this a real code-execution vector
(threat T-01). The sealed paths (``privacy_crypto``,
``privacy_provenance``) unpickle only after HMAC verification, but
get defense-in-depth anyway.

This module provides:

- :class:`SafeUnpickler` — a :class:`pickle.Unpickler` whose
  ``find_class`` enforces an allowlist: safe builtins by name,
  plus explicitly registered classes or module prefixes
  (e.g. ``sklearn.``/``numpy`` for trained models). Anything else
  — ``os.system``, ``subprocess.Popen``, ``builtins.eval`` —
  raises :class:`DeserializationBlocked`.
- :func:`restricted_loads` — one-shot hardened unpickle.
- :func:`scan_for_pickle` — detects pickle framing in opaque bytes
  so callers can refuse before parsing.
- :class:`DeserializationPolicy` — ``allow_pickle`` kill-switch
  plus the allowlist, for call sites that take it from config.

The allowlist is deliberately explicit rather than clever: new
model types register their classes; unknown classes fail closed.
"""

from __future__ import annotations

import io
import pickle
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import DeserializationBlocked

__all__ = [
    "PICKLE_MAGIC",
    "DeserializationPolicy",
    "SafeUnpickler",
    "register_safe_class",
    "restricted_loads",
    "scan_for_pickle",
]

#: Safe builtin (module, name) pairs — data containers only, never
#: callables like eval/exec/getattr/__import__.
_SAFE_BUILTINS: frozenset[tuple[str, str]] = frozenset({
    ("builtins", "list"), ("builtins", "dict"), ("builtins", "tuple"),
    ("builtins", "set"), ("builtins", "frozenset"),
    ("builtins", "str"), ("builtins", "int"), ("builtins", "float"),
    ("builtins", "bool"), ("builtins", "bytes"), ("builtins", "bytearray"),
    ("builtins", "complex"), ("builtins", "range"), ("builtins", "slice"),
    ("builtins", "NoneType"), ("builtins", "Ellipsis"),
    ("collections", "OrderedDict"), ("collections", "defaultdict"),
    ("collections", "Counter"), ("collections", "deque"),
    ("datetime", "datetime"), ("datetime", "date"), ("datetime", "time"),
    ("datetime", "timedelta"), ("datetime", "timezone"),
})

#: First bytes of pickle protocols 0..5 framing.
PICKLE_MAGIC: tuple[bytes, ...] = (
    b"\x80\x02", b"\x80\x03", b"\x80\x04", b"\x80\x05",  # protocol 2-5
    b"(l", b"(d", b"(t",  # protocol 0/1: empty list/dict/tuple MARK
    b"N", b"S", b"I", b"F",  # protocol 0 singletons/shorts
)

_registered: set[tuple[str, str]] = set()


def register_safe_class(cls: type) -> type:
    """Allowlist a class for :class:`SafeUnpickler`. Returns the class."""
    _registered.add((cls.__module__, cls.__qualname__))
    return cls


class SafeUnpickler(pickle.Unpickler):
    """Unpickler that only resolves allowlisted classes."""

    def __init__(self, file: Any,
                 allowed_modules: tuple[str, ...] = (),
                 extra_classes: frozenset[tuple[str, str]] = frozenset(),
                 ) -> None:
        super().__init__(file)
        self._allowed_modules = allowed_modules
        self._extra = extra_classes | _registered

    def find_class(self, module: str, name: str) -> Any:
        key = (module, name)
        if key in _SAFE_BUILTINS or key in self._extra:
            return super().find_class(module, name)
        if module != "builtins" and module != "__builtin__" and \
                self._allowed_modules and \
                any(module == prefix.rstrip(".")
                    or module.startswith(prefix)
                    for prefix in self._allowed_modules):
            return super().find_class(module, name)
        raise DeserializationBlocked(
            f"pickle references non-allowlisted class {module}.{name}",
            module=module, name=name)


def restricted_loads(data: bytes,
                     allowed_modules: tuple[str, ...] = (),
                     extra_classes: frozenset[tuple[str, str]] = frozenset(),
                     ) -> Any:
    """Unpickle ``data`` through the allowlist; raise on violation."""
    if not isinstance(data, (bytes, bytearray)):
        raise DeserializationBlocked(
            "restricted_loads requires bytes",
            actual_type=type(data).__name__)
    try:
        return SafeUnpickler(io.BytesIO(bytes(data)),
                             allowed_modules=allowed_modules,
                             extra_classes=extra_classes).load()
    except DeserializationBlocked:
        raise
    except Exception as e:
        raise DeserializationBlocked(
            f"pickle payload failed to decode: {e}") from e


def scan_for_pickle(data: bytes) -> bool:
    """Heuristic: do these bytes look like a pickle stream?"""
    if not isinstance(data, (bytes, bytearray)) or len(data) < 2:
        return False
    head = bytes(data[:4])
    return any(head.startswith(m) for m in PICKLE_MAGIC)


@dataclass
class DeserializationPolicy:
    """Config-level deserialization policy for a call site."""

    allow_pickle: bool = True
    allowed_modules: tuple[str, ...] = ()
    extra_classes: frozenset[tuple[str, str]] = field(
        default_factory=frozenset)

    def loads(self, data: bytes) -> Any:
        """Decode ``data`` per policy; pickle disabled fails closed."""
        if not self.allow_pickle:
            raise DeserializationBlocked(
                "pickle deserialization disabled by policy")
        return restricted_loads(data,
                                allowed_modules=self.allowed_modules,
                                extra_classes=self.extra_classes)

    def describe(self) -> dict[str, Any]:
        return {
            "allow_pickle": self.allow_pickle,
            "allowed_modules": list(self.allowed_modules),
            "extra_classes": sorted(
                f"{m}.{n}" for m, n in self.extra_classes),
        }
