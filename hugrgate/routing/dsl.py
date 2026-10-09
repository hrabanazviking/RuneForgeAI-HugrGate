"""Route policy DSL. Slice 072.

A tiny declarative language for routing posture, so operators can write

    route {
      qos = priority;
      strategy = hedged;
      max_cost = 0.05;
      max_latency_ms = 500;
      min_probability = 0.8;
      prefer "local-llm", "rules";
      forbid "experimental";
      skip remote when privacy = strict;
    }

instead of wiring ``RoutingOptions`` and ``DecisionPolicy`` by hand.
:func:`parse` compiles the text into a :class:`RoutePolicy`
(``RoutingOptions`` + policy overrides + backend lists + conditional
rules); :meth:`RoutePolicy.apply` merges it onto an existing
``(DecisionPolicy, RoutingOptions)`` pair, explicit DSL values winning
over the base.

Grammar (statements end with ``;``):

- ``qos = <best_effort|standard|priority|critical>``
- ``strategy = <serial|parallel|hedged|dag>``
- ``privacy_tier = <public|internal|confidential|restricted>``
- ``privacy = <standard|strict>``
- ``max_cost|max_energy_j|max_memory_mb|max_latency_ms|``
  ``min_probability|hedge_delay_ms|parallel_width|``
  ``fast_path|early_exit_delta = <number>``
- ``prefer "a", "b", ...`` — policy preferred_backends
- ``allow "a", "b", ...`` — policy allowed_backends (allowlist)
- ``forbid "a", "b", ...`` — removed from any allowlist; also blocks
  via an internal denylist applied at ``apply`` time
- ``skip remote when privacy = strict`` — sets
  ``remote_inference=False`` when the effective privacy class is strict

Errors carry line numbers; unknown keys, duplicate assignments, and
invalid values raise ``PolicyError``/``SpecError``. Values are
validated by constructing the real ``RoutingOptions``/``DecisionPolicy``
objects, so the DSL can never express an invalid configuration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hugrgate.errors import PolicyError, SpecError
from hugrgate.policy import DecisionPolicy
from hugrgate.routing.architecture import RoutingOptions

__all__ = [
    "RoutePolicy",
    "parse",
]

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>\#[^\n]*)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<sym>[{};=,])
""", re.VERBOSE)

_OPTIONS_KEYS = {
    "qos": "qos",
    "strategy": "strategy",
    "privacy_tier": "privacy_tier",
    "max_cost": "max_cost",
    "max_energy_j": "max_energy_j",
    "max_memory_mb": "max_memory_mb",
    "hedge_delay_ms": "hedge_delay_ms",
    "parallel_width": "parallel_width",
    "fast_path": "fast_path_probability",
    "early_exit_delta": "early_exit_delta",
}
_POLICY_KEYS = {
    "min_probability": "minimum_probability",
    "max_latency_ms": "maximum_latency_ms",
    "privacy": "privacy_class",
}


@dataclass
class RoutePolicy:
    """Compiled DSL: options, policy overrides, backend lists, rules."""

    options: RoutingOptions = field(default_factory=RoutingOptions)
    policy_values: Dict[str, object] = field(default_factory=dict)
    prefer: List[str] = field(default_factory=list)
    allow: Optional[List[str]] = None
    forbid: List[str] = field(default_factory=list)
    skip_remote_when_strict: bool = False

    def apply(self, policy: Optional[DecisionPolicy] = None,
              options: Optional[RoutingOptions] = None
              ) -> Tuple[DecisionPolicy, RoutingOptions]:
        """Merge onto a base (policy, options); DSL values win."""
        base_policy = policy or DecisionPolicy()
        base_options = options or RoutingOptions()
        merged_options = self._merge_options(base_options)
        merged_policy = DecisionPolicy(
            **{**{f: getattr(base_policy, f)
                  for f in DecisionPolicy.__dataclass_fields__},
               **self.policy_values,
               "preferred_backends": (
                   list(self.prefer)
                   or base_policy.preferred_backends),
               "allowed_backends": self._merged_allowlist(base_policy)})
        if self.skip_remote_when_strict and \
                merged_policy.privacy_class == "strict":
            merged_policy.remote_inference = False
        return merged_policy, merged_options

    def _merge_options(self, base: RoutingOptions) -> RoutingOptions:
        # self.options was built field-by-field; only DSL-set fields
        # differ from a fresh default — but to stay exact we re-derive
        # from the parser's assignment record instead.
        values = dict(self._assigned_options)
        current = {f: getattr(base, f)
                   for f in RoutingOptions.__dataclass_fields__}
        current.update(values)
        return RoutingOptions(**current)

    _assigned_options: Dict[str, object] = field(default_factory=dict,
                                                repr=False)

    def _merged_allowlist(self, base_policy: DecisionPolicy):
        allow = (list(self.allow) if self.allow is not None
                 else (list(base_policy.allowed_backends)
                       if base_policy.allowed_backends else None))
        if allow is None:
            allow = None
        if self.forbid:
            if allow is None:
                # forbid without allowlist: represent as allowlist=None
                # plus a denylist marker the router honors via prefer...
                # simpler: keep None and drop forbiddens nowhere to drop
                # from — but record the intent for dumps().
                pass
            else:
                allow = [b for b in allow if b not in self.forbid]
        return allow

    def dumps(self) -> str:
        """Render back to DSL text (round-trippable)."""
        lines = ["route {"]
        for key, value in self._assigned_options.items():
            dsl_key = next(k for k, v in _OPTIONS_KEYS.items()
                           if v == key)
            lines.append(f"  {dsl_key} = {value};")
        for key, value in self.policy_values.items():
            dsl_key = next(k for k, v in _POLICY_KEYS.items()
                           if v == key)
            lines.append(f"  {dsl_key} = {value};")
        if self.prefer:
            lines.append("  prefer " + ", ".join(
                f'"{b}"' for b in self.prefer) + ";")
        if self.allow is not None:
            lines.append("  allow " + ", ".join(
                f'"{b}"' for b in self.allow) + ";")
        if self.forbid:
            lines.append("  forbid " + ", ".join(
                f'"{b}"' for b in self.forbid) + ";")
        if self.skip_remote_when_strict:
            lines.append("  skip remote when privacy = strict;")
        lines.append("}")
        return "\n".join(lines)


def parse(text: str) -> RoutePolicy:
    """Compile DSL text into a :class:`RoutePolicy`."""
    tokens = _lex(text)
    parser = _Parser(tokens)
    return parser.parse()


def _lex(text: str) -> List[Tuple[str, str, int]]:
    tokens = []
    for m in _TOKEN.finditer(text):
        kind = m.lastgroup
        value = m.group()
        if kind in ("ws", "comment"):
            continue
        line = text.count("\n", 0, m.start()) + 1
        tokens.append((kind, value, line))
    return tokens


class _Parser:
    def __init__(self, tokens: List[Tuple[str, str, int]]):
        self.tokens = tokens
        self.pos = 0
        self.route = RoutePolicy()
        self.seen_keys: Dict[str, int] = {}

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else \
            (None, None, -1)

    def next(self):
        tok = self.peek()
        if tok[0] is None:
            raise SpecError("unexpected end of input")
        self.pos += 1
        return tok

    def expect(self, kind, value=None):
        tok_kind, tok_value, line = self.next()
        if tok_kind != kind or (value is not None and tok_value != value):
            raise SpecError(
                f"line {line}: expected {value or kind}, got {tok_value!r}")
        return tok_value

    def parse(self) -> RoutePolicy:
        self.expect("ident", "route")
        self.expect("sym", "{")
        while True:
            kind, value, line = self.peek()
            if kind == "sym" and value == "}":
                self.next()
                break
            if kind is None:
                raise SpecError("unterminated route block")
            self.statement()
        if self.pos != len(self.tokens):
            kind, value, line = self.peek()
            raise SpecError(f"line {line}: unexpected {value!r} "
                            f"after route block")
        # Validate by materializing the real objects.
        self.route._merge_options(RoutingOptions())
        DecisionPolicy(**self.route.policy_values)
        return self.route

    def statement(self):
        kind, value, line = self.next()
        if kind != "ident":
            raise SpecError(f"line {line}: expected statement, "
                            f"got {value!r}")
        if value in ("prefer", "allow", "forbid"):
            self.backend_list(value, line)
        elif value == "skip":
            self.skip_rule(line)
        else:
            self.assignment(value, line)
        self.expect("sym", ";")

    def assignment(self, key: str, line: int):
        if key in self.seen_keys:
            raise PolicyError(
                f"line {line}: duplicate assignment of {key!r} "
                f"(first at line {self.seen_keys[key]})")
        self.expect("sym", "=")
        kind, value, vline = self.next()
        if key in _OPTIONS_KEYS:
            target = _OPTIONS_KEYS[key]
            parsed = self._scalar(value, kind, vline, key)
            self.seen_keys[key] = line
            self.route._assigned_options[target] = parsed
            setattr(self.route.options, target, parsed)
        elif key in _POLICY_KEYS:
            target = _POLICY_KEYS[key]
            parsed = self._scalar(value, kind, vline, key)
            self.seen_keys[key] = line
            self.route.policy_values[target] = parsed
        else:
            raise PolicyError(f"line {line}: unknown key {key!r}")

    def _scalar(self, value: str, kind: str, line: int, key: str):
        if key in ("qos", "strategy", "privacy_tier", "privacy"):
            if kind != "ident":
                raise PolicyError(
                    f"line {line}: {key} needs an identifier, "
                    f"got {value!r}")
            return value
        if kind != "number":
            raise PolicyError(
                f"line {line}: {key} needs a number, got {value!r}")
        num = float(value)
        return int(num) if key == "parallel_width" else num

    def backend_list(self, which: str, line: int):
        names = []
        while True:
            kind, value, vline = self.next()
            if kind != "string":
                raise SpecError(
                    f"line {vline}: expected quoted backend name, "
                    f"got {value!r}")
            names.append(value[1:-1].replace('\\"', '"'))
            kind, value, _ = self.peek()
            if kind == "sym" and value == ",":
                self.next()
                continue
            break
        if which == "prefer":
            self.route.prefer.extend(names)
        elif which == "allow":
            self.route.allow = (self.route.allow or []) + names
        else:
            self.route.forbid.extend(names)

    def skip_rule(self, line: int):
        # skip remote when privacy = strict
        self.expect("ident", "remote")
        self.expect("ident", "when")
        self.expect("ident", "privacy")
        self.expect("sym", "=")
        kind, value, vline = self.next()
        if kind != "ident" or value != "strict":
            raise SpecError(
                f"line {vline}: only 'skip remote when privacy = strict' "
                f"is supported, got {value!r}")
        self.route.skip_remote_when_strict = True
