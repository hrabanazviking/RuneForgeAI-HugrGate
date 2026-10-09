"""Grammar-constrained decoding. Slice 164.

GBNF grammars steer token-level decoding so the model can only emit
strings the grammar accepts. :class:`Grammar` builds and validates
GBNF text; :class:`GrammarConstrainedRuntime` wraps any inner runtime
and forwards ``GenerationOptions.grammar`` to engines that enforce it
natively (llama.cpp does — see :mod:`hugrgate.runtimes.llama_cpp`).
Engines without native support get a clear :class:`BackendError`,
never silent unconstrained generation.

Builders:

- :meth:`Grammar.from_gbnf` — explicit GBNF text (validated);
- :meth:`Grammar.from_literals` — alternation over quoted literals
  (the constrained-decoding workhorse for categorical choices);
- :meth:`Grammar.from_choice` — ``from_literals`` plus optional
  surrounding whitespace.

Validation is syntactic honesty, not a full GBNF parser: balanced
quotes/parens, exactly one root rule, no empty alternatives. It
catches malformed builder output and hand-written mistakes, not
deep grammar semantics — documented as such.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import BackendError, SpecError
from hugrgate.runtimes import (
    CAP_GRAMMAR,
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
    ModelRef,
    RuntimeInfo,
)

__all__ = [
    "Grammar",
    "GrammarConstrainedRuntime",
    "gbnf_escape",
]


def gbnf_escape(text: str) -> str:
    """Escape a literal for a GBNF double-quoted string."""
    return (text.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t"))


def _check_gbnf(source: str, root: str = "root") -> None:
    """Syntactic sanity check for GBNF text. Raises SpecError."""
    if not source or not source.strip():
        raise SpecError("grammar source must be non-empty")
    # Balanced double quotes (respecting backslash escapes).
    in_string, escaped = False, False
    for char in source:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
    if in_string:
        raise SpecError("grammar has an unterminated string literal")
    # Balanced parens/brackets outside strings.
    depth_paren = depth_bracket = 0
    in_string, escaped = False, False
    for char in source:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth_paren += 1
        elif char == ")":
            depth_paren -= 1
        elif char == "[":
            depth_bracket += 1
        elif char == "]":
            depth_bracket -= 1
        if depth_paren < 0 or depth_bracket < 0:
            raise SpecError("grammar has unbalanced brackets")
    if depth_paren or depth_bracket:
        raise SpecError("grammar has unbalanced brackets")
    # A root rule must exist: `root ::= ...` at line start (ish).
    pattern = re.compile(rf"(?m)^\s*{re.escape(root)}\s*::=")
    if not pattern.search(source):
        raise SpecError(
            f"grammar has no {root!r} rule (expected "
            f"`{root} ::= ...`)")
    # No empty alternatives (`| |`, `| )`, trailing `|`).
    if re.search(r"\|\s*(\||\)|$)", source):
        raise SpecError("grammar has an empty alternative")


@dataclass(frozen=True)
class Grammar:
    """A validated GBNF grammar."""

    source: str
    root: str = "root"

    def __post_init__(self) -> None:
        _check_gbnf(self.source, self.root)

    @classmethod
    def from_gbnf(cls, source: str, root: str = "root") -> Grammar:
        """Wrap explicit GBNF text (validated)."""
        return cls(source=source, root=root)

    @classmethod
    def from_literals(cls, values: list[str],
                      root: str = "root") -> Grammar:
        """Alternation over quoted literals: ``"a" | "b" | ...``.

        The workhorse for categorical constrained decoding — the
        model must emit exactly one of the values.
        """
        if not values:
            raise SpecError("from_literals needs at least one value")
        if len(set(values)) != len(values):
            raise SpecError("from_literals values must be unique")
        alts = " | ".join(f'"{gbnf_escape(v)}"' for v in values)
        return cls(source=f"{root} ::= {alts}", root=root)

    @classmethod
    def from_choice(cls, values: list[str], root: str = "root",
                    whitespace: str = " ") -> Grammar:
        """Literals with optional surrounding whitespace."""
        if whitespace not in (" ", "\\t", ""):
            raise SpecError(
                f"whitespace must be ' ', '\\t' or '', got "
                f"{whitespace!r}")
        inner = cls.from_literals(values, root=f"{root}-inner")
        ws = f'"{whitespace}"?' if whitespace else ""
        source = (f"{root} ::= {ws} {root}-inner {ws}\n"
                  f"{inner.source}")
        return cls(source=source, root=root)

    def __str__(self) -> str:
        return self.source


class GrammarConstrainedRuntime(LocalRuntime):
    """GBNF grammar enforcement over any inner runtime.

    Forwards ``GenerationOptions.grammar`` to the inner runtime, which
    must advertise :data:`CAP_GRAMMAR` (llama.cpp does natively).
    Without the capability, generation with a grammar raises
    :class:`BackendError` instead of silently ignoring the constraint.
    """

    def __init__(self, inner: LocalRuntime,
                 name: str | None = None) -> None:
        self.inner = inner
        self.name = name or f"{inner.name}+grammar"

    @classmethod
    def available(cls) -> bool:
        raise SpecError(
            "GrammarConstrainedRuntime.available() needs an instance; "
            "query inner.available() instead")

    def info(self) -> RuntimeInfo:
        inner = self.inner.info()
        return RuntimeInfo(
            name=self.name,
            engine=inner.engine,
            engine_version=inner.engine_version,
            available=inner.available,
            devices=inner.devices,
            formats=inner.formats,
            capabilities=inner.capabilities,  # grammar required, not added
            model=inner.model,
            remote=inner.remote,
            notes=(inner.notes + "; GBNF grammar-constrained" if
                   inner.notes else "GBNF grammar-constrained"),
        )

    def _require_grammar(self) -> None:
        if not self.inner.info().supports(CAP_GRAMMAR):
            raise BackendError(
                f"inner runtime {self.inner.name!r} does not advertise "
                f"grammar support; refusing to generate unconstrained "
                f"when a grammar was requested")

    def load(self, model: ModelRef) -> None:
        self.inner.load(model)

    def unload(self) -> None:
        self.inner.unload()

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        opts = options or GenerationOptions()
        if opts.grammar is not None:
            # Validate early: fail fast on malformed grammars before
            # spending inference on them.
            Grammar.from_gbnf(opts.grammar)
            self._require_grammar()
        return self.inner.generate(prompt, opts)

    def generate_constrained(self, prompt: str, grammar: Grammar,
                             options: GenerationOptions | None = None
                             ) -> GenerationResult:
        """Generate with ``grammar`` enforced (validated first)."""
        opts = options or GenerationOptions()
        if opts.grammar is not None and opts.grammar != grammar.source:
            raise SpecError(
                "options.grammar conflicts with the grammar argument; "
                "pass one")
        merged = GenerationOptions(
            max_tokens=opts.max_tokens, temperature=opts.temperature,
            top_p=opts.top_p, stop=opts.stop, seed=opts.seed,
            grammar=grammar.source, timeout_s=opts.timeout_s)
        return self.generate(prompt, merged)

    def embed(self, texts: list[str]):
        return self.inner.embed(texts)

    def classify(self, texts: list[str], labels: list[str]):
        return self.inner.classify(texts, labels)

    def tokenize(self, text: str):
        return self.inner.tokenize(text)

    def warmup(self) -> None:
        self.inner.warmup()

    def health(self) -> dict[str, Any]:
        health = dict(self.inner.health())
        health["runtime"] = self.name
        health["grammar_constrained"] = True
        return health

    def privacy(self) -> dict[str, Any]:
        privacy = dict(self.inner.privacy())
        privacy["runtime"] = self.name
        return privacy

    def close(self) -> None:
        self.inner.close()
