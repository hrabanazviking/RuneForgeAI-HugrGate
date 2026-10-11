"""Slice 12 (logschema-coverage) — coverage lock for observability log events.

Every ``emit_event`` / ``validate_event`` call site in the production
``hugrgate`` package must reference an event that carries a schema in
``EVENT_SCHEMAS`` or a documented entry in ``EXEMPT_EVENTS`` (deprecated
/ legacy emitters only).  The enumeration is static (AST): a call site
whose event name is not a string literal fails the lock, because
coverage cannot be verified for it.

Note: this lock covers *log* events (``hugrgate.observability.logschema``).
Trace-span events (``Span.add_event`` in ``hugrgate.observability.trace``)
are a separate mechanism with their own attribute validation and are
deliberately out of scope here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import hugrgate
from hugrgate.observability import logschema
from hugrgate.observability.logschema import EVENT_SCHEMAS, EXEMPT_EVENTS

_EMIT_FUNCS = ("emit_event", "validate_event")

#: Position of the ``event`` argument in each emit function's signature.
_EVENT_ARG_INDEX = {"emit_event": 1, "validate_event": 0}

_EVENT_NAME_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_.]+$")


def _emit_call_sites() -> tuple[list[tuple[str, int, str]],
                                 list[tuple[str, int]]]:
    """Return (literal_sites, dynamic_sites).

    ``literal_sites``: (file, line, event_name) for call sites whose
    event argument is a string literal.  ``dynamic_sites``: (file, line)
    for call sites whose event argument is computed at runtime.
    """
    root = Path(hugrgate.__file__).resolve().parent
    # The module that *defines* emit_event/validate_event is trusted:
    # its internal validate_event(event, fields) call inside emit_event is
    # a parameter pass-through, not a consumer call site.  The lock audits
    # every other module in the package.
    self_module = Path(logschema.__file__).resolve()
    literal: list[tuple[str, int, str]] = []
    dynamic: list[tuple[str, int]] = []
    for path in sorted(root.rglob("*.py")):
        if path.resolve() == self_module:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"),
                             filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - safety net
            raise AssertionError(f"cannot parse {path}: {exc}") from exc
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None)
            if name not in _EMIT_FUNCS:
                continue
            event_node = None
            for kw in node.keywords:
                if kw.arg == "event":
                    event_node = kw.value
                    break
            if event_node is None:
                idx = _EVENT_ARG_INDEX[name]
                if len(node.args) > idx:
                    event_node = node.args[idx]
            label = f"{path.relative_to(root)}:{node.lineno}"
            if event_node is None:
                dynamic.append((label, node.lineno))
            elif (isinstance(event_node, ast.Constant)
                  and isinstance(event_node.value, str)
                  and event_node.value):
                literal.append((label, node.lineno, event_node.value))
            else:
                dynamic.append((label, node.lineno))
    return literal, dynamic


def test_every_emitted_event_is_schema_or_exempt():
    literal, dynamic = _emit_call_sites()
    problems: list[str] = []
    for label, _lineno in dynamic:
        problems.append(
            f"{label}: event name is not a string literal — coverage "
            f"cannot be statically verified")
    for label, _lineno, event in literal:
        if event not in EVENT_SCHEMAS and event not in EXEMPT_EVENTS:
            problems.append(
                f"{label}: emitted log event {event!r} has no schema in "
                f"EVENT_SCHEMAS and no entry in EXEMPT_EVENTS")
    assert not problems, (
        "unvalidated observability log events found:\n" + "\n".join(problems))


def test_exempt_events_are_explicit_and_well_formed():
    for event, reason in EXEMPT_EVENTS.items():
        assert _EVENT_NAME_RE.match(event), (
            f"exempt event name {event!r} is not a dotted event name")
        assert isinstance(reason, str) and reason.strip(), (
            f"exempt event {event!r} must carry a non-empty reason")
        assert event not in EVENT_SCHEMAS, (
            f"event {event!r} is both schema'd and exempt — remove the "
            f"exemption")


def test_schema_event_names_are_dotted():
    for event in EVENT_SCHEMAS:
        assert _EVENT_NAME_RE.match(event), (
            f"schema event name {event!r} is not a dotted event name")
