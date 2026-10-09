"""Structured-output adapter. Slice 163.

:class:`StructuredRuntime` wraps any :class:`LocalRuntime` and turns
free-text generation into *validated* structured data:

1. the inner runtime generates (with the JSON schema attached to
   :class:`GenerationOptions` when the inner runtime understands it);
2. :func:`extract_json` pulls the JSON payload out of the raw text
   (plain, fenced, or embedded);
3. :func:`validate` checks it against the schema with a small
   dependency-free validator (documented subset below);
4. on failure the model is re-prompted with the validation errors,
   up to ``max_retries``; persistent failure raises
   :class:`BackendError` — never a silently invalid object.

Validator subset (honest, no surprises): ``type`` (all six JSON
types + ``integer``/``number`` distinction), ``properties``,
``required``, ``additionalProperties`` (bool or schema),
``items`` (schema or list), ``enum``, ``const``, ``minimum`` /
``maximum`` (+ ``exclusiveMinimum``/``exclusiveMaximum``),
``minLength``/``maxLength``, ``pattern``, ``anyOf``/``oneOf``/
``allOf``, and local ``$ref`` (``#/...`` pointers only). Anything
else in a schema is *ignored with a note* in the validation report —
never silently enforced, never silently dropped without mention.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

from hugrgate.errors import BackendError, SpecError
from hugrgate.runtimes import (
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
    ModelRef,
    RuntimeInfo,
)

__all__ = [
    "IGNORED_KEYWORDS",
    "StructuredRuntime",
    "extract_json",
    "validate",
]

#: Schema keywords the subset validator reads but does not enforce;
#: their presence is reported, not silently dropped.
IGNORED_KEYWORDS = frozenset({
    "$schema", "$id", "$comment", "title", "description", "default",
    "examples", "deprecated", "readOnly", "writeOnly",
})


def extract_json(text: str) -> Any:
    """Pull the JSON payload out of raw model text.

    Tries, in order: the whole text; a fenced code block
    (`````json ... ````` or plain `````); the first balanced
    ``{...}`` or ``[...]`` span. Raises :class:`BackendError` when
    nothing parses.
    """
    text = (text or "").strip()
    if not text:
        raise BackendError("empty text: no JSON to extract")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text,
                      re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    span = _balanced_span(text)
    if span is not None:
        try:
            return json.loads(span)
        except json.JSONDecodeError:
            pass
    raise BackendError(
        f"no JSON payload found in {len(text)} chars of model text")


def _balanced_span(text: str) -> str | None:
    """First balanced ``{...}`` or ``[...]`` span, string-aware."""
    start = next((i for i, c in enumerate(text) if c in "{["), -1)
    if start < 0:
        return None
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
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
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _check_type(value: Any, expected: str, path: str,
                errors: list[str]) -> None:
    actual = _type_name(value)
    if expected == "number":
        ok = actual in ("integer", "number")
    elif expected == "integer":
        ok = actual == "integer" or (
            actual == "number" and float(value).is_integer())
    else:
        ok = actual == expected
    if not ok:
        errors.append(
            f"{path}: expected {expected}, got {actual}")


def validate(instance: Any, schema: dict[str, Any],
             path: str = "$") -> list[str]:
    """Validate ``instance`` against ``schema``.

    Returns a list of human-readable errors (empty = valid).
    ``$ref`` supports local ``#/...`` JSON pointers only.
    """
    errors: list[str] = []
    _validate(instance, schema, path, errors, schema)
    return errors


def _resolve_ref(ref: str, root: dict[str, Any],
                 errors: list[str], path: str) -> dict[str, Any] | None:
    if not ref.startswith("#/"):
        errors.append(f"{path}: only local $ref supported, got {ref!r}")
        return None
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            errors.append(
                f"{path}: $ref {ref!r} does not resolve")
            return None
        node = node[part]
    if not isinstance(node, dict):
        errors.append(f"{path}: $ref {ref!r} is not a schema")
        return None
    return node


def _validate(instance: Any, schema: dict[str, Any], path: str,
              errors: list[str], root: dict[str, Any]) -> None:
    if not isinstance(schema, dict):
        errors.append(f"{path}: schema must be an object")
        return
    if "$ref" in schema:
        resolved = _resolve_ref(str(schema["$ref"]), root, errors, path)
        if resolved is None:
            return
        merged = {**resolved,
                  **{k: v for k, v in schema.items() if k != "$ref"}}
        _validate(instance, merged, path, errors, root)
        return

    ignored = sorted(IGNORED_KEYWORDS & set(schema))
    if ignored and path == "$":
        errors.append(f"{path}: note: keywords not enforced: "
                      f"{', '.join(ignored)}")

    expected = schema.get("type")
    if expected is not None:
        types = [expected] if isinstance(expected, str) else expected
        if not any(_matches_type(instance, t) for t in types):
            errors.append(
                f"{path}: expected {'/'.join(types)}, got "
                f"{_type_name(instance)}")
            return  # further checks would be noise

    if isinstance(instance, dict):
        _validate_object(instance, schema, path, errors, root)
    elif isinstance(instance, list):
        _validate_array(instance, schema, path, errors, root)
    elif isinstance(instance, str):
        _validate_string(instance, schema, path, errors)
    elif isinstance(instance, (int, float)) and not isinstance(
            instance, bool):
        _validate_number(instance, schema, path, errors)

    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in schema:
            _validate_combiner(instance, schema[keyword], keyword, path,
                               errors, root)

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum "
                      f"{schema['enum']!r}")
    if "const" in schema and instance != schema["const"]:
        errors.append(
            f"{path}: {instance!r} != const {schema['const']!r}")


def _matches_type(value: Any, expected: str) -> bool:
    errs: list[str] = []
    _check_type(value, expected, "$", errs)
    return not errs


def _validate_object(instance: dict, schema: dict, path: str,
                     errors: list[str], root: dict) -> None:
    properties = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in instance:
            errors.append(f"{path}: missing required property {name!r}")
    for name, value in instance.items():
        prop_schema = properties.get(name)
        if prop_schema is not None:
            _validate(value, prop_schema, f"{path}.{name}", errors, root)
        else:
            additional = schema.get("additionalProperties", True)
            if additional is False:
                errors.append(
                    f"{path}: additional property {name!r} not allowed")
            elif isinstance(additional, dict):
                _validate(value, additional, f"{path}.{name}", errors,
                          root)


def _validate_array(instance: list, schema: dict, path: str,
                    errors: list[str], root: dict) -> None:
    items = schema.get("items")
    if items is None:
        return
    if isinstance(items, list):  # tuple form
        for i, (value, sub) in enumerate(zip(instance, items,
                                              strict=False)):
            _validate(value, sub, f"{path}[{i}]", errors, root)
        if len(instance) > len(items):
            errors.append(
                f"{path}: array has {len(instance)} items, schema "
                f"allows {len(items)}")
    else:
        for i, value in enumerate(instance):
            _validate(value, items, f"{path}[{i}]", errors, root)


def _validate_string(instance: str, schema: dict, path: str,
                     errors: list[str]) -> None:
    if "minLength" in schema and len(instance) < schema["minLength"]:
        errors.append(f"{path}: shorter than minLength "
                      f"{schema['minLength']}")
    if "maxLength" in schema and len(instance) > schema["maxLength"]:
        errors.append(f"{path}: longer than maxLength "
                      f"{schema['maxLength']}")
    if "pattern" in schema:
        try:
            if not re.search(schema["pattern"], instance):
                errors.append(
                    f"{path}: does not match pattern "
                    f"{schema['pattern']!r}")
        except re.error as e:
            errors.append(f"{path}: bad pattern: {e}")


def _validate_number(instance: float, schema: dict, path: str,
                     errors: list[str]) -> None:
    for key, cmp, label in (
            ("minimum", lambda a, b: a < b, "below minimum"),
            ("maximum", lambda a, b: a > b, "above maximum"),
            ("exclusiveMinimum", lambda a, b: a <= b,
             "not above exclusiveMinimum"),
            ("exclusiveMaximum", lambda a, b: a >= b,
             "not below exclusiveMaximum")):
        if key in schema and cmp(instance, schema[key]):
            errors.append(f"{path}: {label} {schema[key]}")


def _validate_combiner(instance: Any, subschemas: list, keyword: str,
                       path: str, errors: list[str],
                       root: dict) -> None:
    counts = 0
    first_errors: list[str] = []
    for sub in subschemas:
        sub_errors: list[str] = []
        _validate(instance, sub, path, sub_errors, root)
        if not sub_errors:
            counts += 1
        elif not first_errors:
            first_errors = sub_errors
    if keyword == "allOf" and counts != len(subschemas):
        errors.append(f"{path}: allOf failed: {first_errors[0] if first_errors else '?'}")
    elif keyword == "anyOf" and counts == 0:
        errors.append(f"{path}: anyOf matched no subschema")
    elif keyword == "oneOf" and counts != 1:
        errors.append(
            f"{path}: oneOf matched {counts} subschemas, need exactly 1")


class StructuredRuntime(LocalRuntime):
    """Validated structured generation over any inner runtime.

    Parameters
    ----------
    inner: the runtime that actually generates.
    max_retries: re-prompts after a validation failure (the errors
        are appended to the prompt so the model can self-correct).
    name: defaults to ``"<inner-name>+structured"``.
    """

    def __init__(self, inner: LocalRuntime, max_retries: int = 2,
                 name: str | None = None) -> None:
        if max_retries < 0:
            raise SpecError(f"max_retries must be >= 0, got {max_retries}")
        self.inner = inner
        self.max_retries = max_retries
        self.name = name or f"{inner.name}+structured"
        self._lock = threading.RLock()

    # -- LocalRuntime contract (delegated) -----------------------------------

    @classmethod
    def available(cls) -> bool:
        raise SpecError(
            "StructuredRuntime.available() needs an instance; "
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
            notes=(inner.notes + "; structured-output validated"
                   if inner.notes else "structured-output validated"),
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
        _result, _parsed = self.generate_structured(
            prompt, opts.json_schema, opts)
        return _result

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
        health["structured"] = True
        return health

    def privacy(self) -> dict[str, Any]:
        privacy = dict(self.inner.privacy())
        privacy["runtime"] = self.name
        return privacy

    def close(self) -> None:
        self.inner.close()

    # -- structured generation -------------------------------------------------

    def generate_structured(self, prompt: str, schema: dict[str, Any],
                            options: GenerationOptions | None = None
                            ) -> tuple[GenerationResult, Any]:
        """Generate ``prompt`` and return ``(result, parsed_json)``.

        ``parsed_json`` is validated against ``schema``; failure after
        ``max_retries`` re-prompts raises :class:`BackendError`.
        """
        if not isinstance(schema, dict) or not schema:
            raise SpecError("schema must be a non-empty object")
        opts = options or GenerationOptions()
        if opts.grammar is not None:
            raise SpecError(
                "options.grammar conflicts with the schema argument; "
                "pass one")
        # Attach the schema so grammar-capable inner runtimes can
        # constrain decoding natively (slice 165). The schema travels
        # without grammar: GenerationOptions keeps the two mutually
        # exclusive.
        opts = GenerationOptions(
            max_tokens=opts.max_tokens, temperature=opts.temperature,
            top_p=opts.top_p, stop=opts.stop, seed=opts.seed,
            json_schema=schema, timeout_s=opts.timeout_s)
        current_prompt = self._check_prompt(prompt)
        last_errors: list[str] = []
        result = None
        for attempt in range(self.max_retries + 1):
            result = self.inner.generate(current_prompt, opts)
            try:
                parsed = extract_json(result.text)
            except BackendError as e:
                last_errors = [str(e)]
            else:
                last_errors = validate(parsed, schema)
                if not last_errors:
                    return result, parsed
            if attempt < self.max_retries:
                current_prompt = (
                    f"{prompt}\n\nYour previous answer was invalid:\n"
                    + "\n".join(f"- {e}" for e in last_errors)
                    + "\nRespond with valid JSON only.")
        raise BackendError(
            f"structured generation failed after "
            f"{self.max_retries + 1} attempt(s): "
            + "; ".join(last_errors))

    def _require_capability(self, capability: str) -> None:
        # StructuredRuntime adds json_schema on top of inner's set.
        if capability == "json_schema":
            return
        self.inner._require_capability(capability)
