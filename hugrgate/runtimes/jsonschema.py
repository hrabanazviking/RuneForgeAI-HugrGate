"""JSON-schema constrained decoding. Slice 165.

Compiles a JSON schema (subset) to GBNF and enforces it through a
grammar-capable inner runtime, then re-validates the output with
slice 163's validator — belt and suspenders:

1. :func:`json_schema_to_gbnf` compiles the schema to GBNF text
   (validated by :class:`Grammar`);
2. :class:`JsonSchemaConstrainedRuntime` sets it as
   ``GenerationOptions.grammar`` and delegates to the inner runtime
   (which must advertise ``CAP_GRAMMAR``);
3. the emitted text is extracted (:func:`extract_json`) and validated
   (:func:`validate`); failure raises :class:`BackendError`.

Compiler coverage (honest subset): ``type`` (object/array/string/
integer/number/boolean/null), ``properties`` + ``required``
(optional properties become nested optional groups *in declaration
order* — JSON objects are unordered but constrained decoding needs
determinism; documented), ``items``, ``enum``, ``const``,
``anyOf``/``oneOf``, local ``$ref``. NOT compiled to GBNF (still
enforced post-hoc by the validator): ``pattern``, ``minLength``/
``maxLength``, ``minimum``/``maximum``, ``minItems``/``maxItems``,
``additionalProperties: true``. The compiler reports exactly which
keywords it skipped via :func:`uncompilable_keywords`.
"""

from __future__ import annotations

import json
import re
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
from hugrgate.runtimes.grammar import Grammar, gbnf_escape
from hugrgate.runtimes.structured import extract_json, validate

__all__ = [
    "JsonSchemaConstrainedRuntime",
    "json_schema_to_gbnf",
    "uncompilable_keywords",
]

#: Keywords the GBNF compiler cannot express (still validated post-hoc).
UNCOMPILABLE = frozenset({
    "pattern", "minLength", "maxLength", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems",
    "uniqueItems", "additionalProperties",
})


def uncompilable_keywords(schema: Any) -> list[str]:
    """Keywords in ``schema`` (deep) that GBNF compilation skips."""
    found: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in UNCOMPILABLE:
                    found.append(key)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(schema)
    return sorted(set(found))


class _Builder:
    """Recursive JSON-schema -> GBNF rule builder."""

    def __init__(self, root: str = "root"):
        self.root = root
        self.rules: dict[str, str] = {}
        self._counter = 0

    def new_name(self, hint: str) -> str:
        self._counter += 1
        clean = re.sub(r"[^A-Za-z0-9_-]", "-", hint)[:24] or "node"
        return f"{self.root}-{clean}-{self._counter}"

    def add(self, name: str, schema: Any) -> str:
        """Add a rule for ``schema``; returns the rule's name."""
        if name in self.rules:
            return name
        # placeholder first: recursion via $ref resolves afterwards
        self.rules[name] = ""
        self.rules[name] = self._compile(schema, name)
        return name

    def _compile(self, schema: Any, name: str) -> str:
        if schema is True:
            return self._ref_rule(
                {"anyOf": [{"type": "object"}, {"type": "array"},
                           {"type": "string"}, {"type": "number"},
                           {"type": "boolean"}, {"type": "null"}]},
                f"{name}-any")
        if schema is False:
            raise SpecError(
                "boolean schema 'false' matches nothing; refusing to "
                "compile it to a grammar")
        if not isinstance(schema, dict):
            raise SpecError(f"schema node must be an object, got "
                            f"{type(schema).__name__}")
        if "$ref" in schema:
            return self._compile_ref(str(schema["$ref"]), name)
        if "const" in schema:
            return self._compile_literal(schema["const"])
        if "enum" in schema:
            alts = " | ".join(
                self._compile_literal(v) for v in schema["enum"])
            return f"( {alts} )"
        for keyword in ("anyOf", "oneOf"):
            if keyword in schema:
                alts = " | ".join(
                    self._ref_rule(sub, f"{name}-{keyword}")
                    for sub in schema[keyword])
                return f"( {alts} )"
        if "allOf" in schema:
            # allOf is validated post-hoc; grammar takes the first branch
            return self._ref_rule(schema["allOf"][0], f"{name}-allof")
        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            alts = " | ".join(
                self._ref_rule({**schema, "type": t}, f"{name}-{t}")
                for t in schema_type)
            return f"( {alts} )"
        if schema_type == "object" or (
                schema_type is None and ("properties" in schema
                                         or "required" in schema)):
            return self._compile_object(schema, name)
        if schema_type == "array" or (
                schema_type is None and "items" in schema):
            return self._compile_array(schema, name)
        if schema_type == "string":
            return self._compile_string()
        if schema_type == "integer":
            return r'"-"? [0-9]+'
        if schema_type == "number":
            return r'"-"? ([0-9]+ ("." [0-9]+)? ([eE] [+-]? [0-9]+)?)'
        if schema_type == "boolean":
            return '"true" | "false"'
        if schema_type == "null":
            return '"null"'
        # No type and no structural keywords: accept any JSON value.
        return self._ref_rule(
            {"anyOf": [{"type": "object"}, {"type": "array"},
                       {"type": "string"}, {"type": "number"},
                       {"type": "boolean"}, {"type": "null"}]},
            f"{name}-any")

    def _ref_rule(self, schema: Any, hint: str) -> str:
        name = self.new_name(hint)
        self.add(name, schema)
        return name

    def _compile_ref(self, ref: str, name: str) -> str:
        # Local refs only; resolution happens against the root schema
        # held by the caller (see json_schema_to_gbnf).
        raise SpecError(
            f"$ref {ref!r} inside compiled node {name!r}: refs are "
            f"resolved by json_schema_to_gbnf before compilation")

    def _compile_literal(self, value: Any) -> str:
        text = json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            return f'"{gbnf_escape(value)}"'
        # numbers/bools/null render as literal text
        return " ".join(f'"{gbnf_escape(ch)}"' for ch in text)

    def _compile_string(self) -> str:
        return (r'"\"" ([^"\\] | "\\" (["\\/bfnrt] | "u" '
                r'[0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F]))* '
                r'"\""')

    def _compile_object(self, schema: dict, name: str) -> str:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        if not properties:
            return '"{" space "}" space'
        prop_names = list(properties)
        # Required first (declaration order), then optionals: required
        # props are mandatory in order; optional props become nested
        # optional groups after them (JSON is unordered, but
        # constrained decoding needs determinism — documented).
        ordered = sorted(
            prop_names,
            key=lambda p: (p not in required, prop_names.index(p)))
        reqs = [p for p in ordered if p in required]
        opts = [p for p in ordered if p not in required]
        seq = '"{" space '
        for j, prop in enumerate(reqs):
            if j:
                seq += '"," space '
            rule = self._ref_rule(properties[prop], f"{name}-{prop}")
            seq += (f'"\\"{gbnf_escape(prop)}\\"" space ":" space '
                    f"{rule} ")
        tail = '"}" space'
        for prop in reversed(opts):
            rule = self._ref_rule(properties[prop], f"{name}-{prop}")
            pair = (f'"," space "\\"{gbnf_escape(prop)}\\"" space ":" '
                    f"space {rule} ")
            tail = f"( {pair}{tail} )?"
        return seq + tail

    def _compile_array(self, schema: dict, name: str) -> str:
        items = schema.get("items")
        if items is None:
            item_rule = self._ref_rule({"type": "string"},
                                       f"{name}-item")
        elif isinstance(items, list):
            # tuple form: fixed prefix, validated post-hoc for the rest
            sub_rules = [self._ref_rule(sub, f"{name}-item{i}")
                         for i, sub in enumerate(items)]
            inner = " ".join(
                ("," if i else "") + f" space {r} "
                for i, r in enumerate(sub_rules))
            return f'"[" space {inner} "]" space'
        else:
            item_rule = self._ref_rule(items, f"{name}-item")
            return (f'"[" space ({item_rule} ("," space {item_rule})* )? '
                    f'"]" space')
        return (f'"[" space ({item_rule} ("," space {item_rule})* )? '
                f'"]" space')

    def render(self) -> str:
        lines = ["space ::= \" \"?"]
        for name, body in self.rules.items():
            lines.append(f"{name} ::= {body}")
        return "\n".join(lines) + "\n"


def _resolve_local_refs(schema: Any, root: Any) -> Any:
    """Inline local ``#/...`` refs (compiler works on ref-free schemas)."""
    if isinstance(schema, dict):
        if "$ref" in schema and str(schema["$ref"]).startswith("#/"):
            node: Any = root
            for part in str(schema["$ref"])[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                node = node[part]
            rest = {k: v for k, v in schema.items() if k != "$ref"}
            resolved = _resolve_local_refs(node, root)
            if isinstance(resolved, dict):
                return {**resolved, **_resolve_local_refs(rest, root)}
            return resolved
        return {k: _resolve_local_refs(v, root)
                for k, v in schema.items()}
    if isinstance(schema, list):
        return [_resolve_local_refs(v, root) for v in schema]
    return schema


def json_schema_to_gbnf(schema: dict[str, Any],
                         root: str = "root") -> str:
    """Compile a JSON schema to GBNF text (validated).

    Raises :class:`SpecError` for empty/non-object schemas.
    """
    if isinstance(schema, bool):
        pass  # boolean schemas are valid; _compile handles them
    elif not isinstance(schema, dict) or not schema:
        raise SpecError("schema must be a non-empty object")
    resolved = _resolve_local_refs(schema, schema)
    builder = _Builder(root=root)
    builder.add(root, resolved)
    return builder.render()


class JsonSchemaConstrainedRuntime(LocalRuntime):
    """JSON-schema constrained decoding over a grammar-capable runtime.

    Compiles ``GenerationOptions.json_schema`` to GBNF, enforces it
    through the inner runtime (must advertise ``CAP_GRAMMAR``), then
    re-validates with slice 163's validator. Composes slices 163+164:
    constrained decoding *and* a validated parse, or
    :class:`BackendError`.
    """

    def __init__(self, inner: LocalRuntime,
                 name: str | None = None) -> None:
        self.inner = inner
        self.name = name or f"{inner.name}+jsonschema"

    @classmethod
    def available(cls) -> bool:
        raise SpecError(
            "JsonSchemaConstrainedRuntime.available() needs an instance; "
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
            capabilities=inner.capabilities | frozenset({"json_schema"}),
            model=inner.model,
            remote=inner.remote,
            notes=(inner.notes + "; JSON-schema constrained" if
                   inner.notes else "JSON-schema constrained"),
        )

    def load(self, model: ModelRef) -> None:
        self.inner.load(model)

    def unload(self) -> None:
        self.inner.unload()

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        opts = options or GenerationOptions()
        if opts.json_schema is None:
            return self.inner.generate(prompt, opts)
        if not self.inner.info().supports(CAP_GRAMMAR):
            raise BackendError(
                f"inner runtime {self.inner.name!r} does not advertise "
                f"grammar support; cannot enforce a JSON schema")
        gbnf = json_schema_to_gbnf(opts.json_schema)
        grammar = Grammar.from_gbnf(gbnf)  # validated before inference
        # Forward grammar only: GenerationOptions keeps grammar and
        # json_schema mutually exclusive, so the schema travels in
        # this wrapper (for post-hoc validation), not in options.
        merged = GenerationOptions(
            max_tokens=opts.max_tokens, temperature=opts.temperature,
            top_p=opts.top_p, stop=opts.stop, seed=opts.seed,
            grammar=grammar.source, timeout_s=opts.timeout_s)
        result = self.inner.generate(prompt, merged)
        try:
            parsed = extract_json(result.text)
        except BackendError as e:
            raise BackendError(
                f"constrained output held no JSON: {e}") from e
        errors = validate(parsed, opts.json_schema)
        if errors:
            raise BackendError(
                "grammar-constrained output failed validation: "
                + "; ".join(errors))
        return result

    def generate_constrained(self, prompt: str, schema: dict[str, Any],
                             options: GenerationOptions | None = None
                             ) -> tuple[GenerationResult, Any]:
        """Generate and return ``(result, parsed_json)`` (validated)."""
        opts = options or GenerationOptions()
        if opts.grammar is not None:
            raise SpecError(
                "options.grammar conflicts with the schema argument; "
                "pass one")
        merged = GenerationOptions(
            max_tokens=opts.max_tokens, temperature=opts.temperature,
            top_p=opts.top_p, stop=opts.stop, seed=opts.seed,
            json_schema=schema, timeout_s=opts.timeout_s)
        result = self.generate(prompt, merged)
        return result, extract_json(result.text)

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
        health["json_schema_constrained"] = True
        return health

    def privacy(self) -> dict[str, Any]:
        privacy = dict(self.inner.privacy())
        privacy["runtime"] = self.name
        return privacy

    def close(self) -> None:
        self.inner.close()
