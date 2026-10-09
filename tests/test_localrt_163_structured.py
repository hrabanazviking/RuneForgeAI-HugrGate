"""Slice 163 — structured-output adapter.

Unit tests for ``hugrgate.runtimes.structured``: JSON extraction,
the subset validator, and the retrying StructuredRuntime.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import BackendError, SpecError
from hugrgate.runtimes import (
    FakeRuntime,
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
)
from hugrgate.runtimes.structured import (
    StructuredRuntime,
    extract_json,
    validate,
)

# -- extract_json ------------------------------------------------------------------

def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('[1, 2]') == [1, 2]


def test_extract_fenced_json():
    text = 'Here you go:\n```json\n{"a": 1}\n```\nDone.'
    assert extract_json(text) == {"a": 1}


def test_extract_fenced_without_tag():
    assert extract_json('```\n{"a": 2}\n```') == {"a": 2}


def test_extract_embedded_span():
    assert extract_json('The answer is {"a": 3} trust me.') == {"a": 3}


def test_extract_span_string_aware():
    text = 'prefix {"s": "a } b { c"} suffix'
    assert extract_json(text) == {"s": "a } b { c"}


def test_extract_nothing_raises():
    with pytest.raises(BackendError):
        extract_json("no json here at all")


def test_extract_empty_raises():
    with pytest.raises(BackendError):
        extract_json("   ")


# -- validate --------------------------------------------------------------------------

def test_validate_object_ok():
    schema = {"type": "object",
              "properties": {"name": {"type": "string"},
                             "age": {"type": "integer"}},
              "required": ["name"]}
    assert validate({"name": "x", "age": 3}, schema) == []


def test_validate_missing_required():
    schema = {"type": "object", "required": ["name"]}
    errors = validate({}, schema)
    assert any("missing required" in e for e in errors)


def test_validate_wrong_type():
    errors = validate({"age": "old"},
                      {"type": "object",
                       "properties": {"age": {"type": "integer"}}})
    assert any("expected integer" in e for e in errors)


def test_validate_number_accepts_integer():
    assert validate(3, {"type": "number"}) == []
    assert validate(3.5, {"type": "integer"}) != []


def test_validate_additional_properties():
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"a": {"type": "string"}}}
    assert validate({"a": "x", "b": 1}, schema) != []
    assert validate({"a": "x"}, schema) == []


def test_validate_array_items():
    schema = {"type": "array", "items": {"type": "integer"}}
    assert validate([1, 2], schema) == []
    assert validate([1, "x"], schema) != []


def test_validate_tuple_items():
    schema = {"type": "array",
              "items": [{"type": "string"}, {"type": "integer"}]}
    assert validate(["a", 1], schema) == []
    assert validate(["a", 1, 2], schema) != []


def test_validate_enum_const():
    assert validate("b", {"enum": ["a", "b"]}) == []
    assert validate("c", {"enum": ["a", "b"]}) != []
    assert validate(1, {"const": 1}) == []
    assert validate(2, {"const": 1}) != []


def test_validate_string_keywords():
    schema = {"type": "string", "minLength": 2, "maxLength": 4,
              "pattern": "^[a-z]+$"}
    assert validate("abc", schema) == []
    assert validate("a", schema) != []
    assert validate("abcde", schema) != []
    assert validate("ABC", schema) != []


def test_validate_number_keywords():
    schema = {"type": "number", "minimum": 0, "maximum": 10,
              "exclusiveMaximum": 10}
    assert validate(5, schema) == []
    assert validate(-1, schema) != []
    assert validate(10, schema) != []  # exclusiveMaximum


def test_validate_combiners():
    assert validate(5, {"anyOf": [{"type": "string"},
                                  {"type": "integer"}]}) == []
    assert validate(5, {"oneOf": [{"type": "integer"},
                                  {"type": "number"}]}) != []
    assert validate({"a": 1}, {"allOf": [{"type": "object"},
                                         {"required": ["a"]}]}) == []


def test_validate_ref_local():
    schema = {"$defs": {"name": {"type": "string"}},
              "type": "object",
              "properties": {"n": {"$ref": "#/$defs/name"}}}
    assert validate({"n": "x"}, schema) == []
    assert validate({"n": 1}, schema) != []


def test_validate_ref_unresolvable():
    errors = validate({"n": 1}, {"$ref": "#/$defs/nope"})
    assert any("does not resolve" in e for e in errors)


def test_validate_ignored_keywords_noted():
    errors = validate("x", {"type": "string", "title": "T",
                            "description": "D"})
    assert any("not enforced" in e for e in errors)


# -- StructuredRuntime ----------------------------------------------------------------------

class ScriptedRuntime(FakeRuntime):
    name = "scripted"

    def __init__(self, texts: list[str]):
        super().__init__()
        self._texts = list(texts)

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        text = self._texts.pop(0) if self._texts else '{"ok": true}'
        return GenerationResult(text=text, finish_reason="stop")


SCHEMA = {"type": "object",
          "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"],
          "additionalProperties": False}


def test_structured_success_first_try():
    inner = ScriptedRuntime(['{"ok": true}'])
    rt = StructuredRuntime(inner)
    result, parsed = rt.generate_structured("prompt", SCHEMA)
    assert parsed == {"ok": True}
    assert result.finish_reason == "stop"


def test_structured_retries_with_error_feedback():
    inner = ScriptedRuntime(['{"ok": "yes"}', '{"ok": true}'])
    rt = StructuredRuntime(inner, max_retries=2)
    _, parsed = rt.generate_structured("prompt", SCHEMA)
    assert parsed == {"ok": True}


def test_structured_exhausts_retries():
    inner = ScriptedRuntime(['nope', 'still nope'])
    rt = StructuredRuntime(inner, max_retries=1)
    with pytest.raises(BackendError, match="failed after 2 attempt"):
        rt.generate_structured("prompt", SCHEMA)


def test_structured_passthrough_without_schema():
    inner = ScriptedRuntime(['just text'])
    rt = StructuredRuntime(inner)
    out = rt.generate("prompt", GenerationOptions())
    assert out.text == "just text"


def test_structured_generate_with_schema_option():
    inner = ScriptedRuntime(['{"ok": true}'])
    rt = StructuredRuntime(inner)
    out = rt.generate("prompt",
                      GenerationOptions(json_schema=SCHEMA))
    assert out.text == '{"ok": true}'


def test_structured_rejects_empty_schema():
    rt = StructuredRuntime(FakeRuntime())
    with pytest.raises(SpecError):
        rt.generate_structured("prompt", {})


def test_structured_rejects_negative_retries():
    with pytest.raises(SpecError):
        StructuredRuntime(FakeRuntime(), max_retries=-1)


def test_structured_info_adds_capability():
    rt = StructuredRuntime(FakeRuntime())
    info = rt.info()
    assert info.name == "fake+structured"
    assert "json_schema" in info.capabilities
    assert "generate" in info.capabilities


def test_structured_delegates_lifecycle():
    inner = FakeRuntime()
    rt = StructuredRuntime(inner)
    assert rt.health()["structured"] is True
    assert rt.privacy()["remote"] is False
    rt.close()


def test_structured_embed_classify_delegate():
    rt = StructuredRuntime(FakeRuntime())
    assert rt.embed(["a"]).dim == 64
    (res,) = rt.classify(["x"], ["a"])
    assert res.label in ("a",)


class _NoGenerate(LocalRuntime):
    name = "no-generate"

    @classmethod
    def available(cls) -> bool:
        return True

    def info(self):
        from hugrgate.runtimes import RuntimeInfo
        return RuntimeInfo(name=self.name, engine="x",
                           engine_version="1", available=True,
                           devices=("cpu",), formats=(),
                           capabilities=frozenset(), remote=False)

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None):
        raise BackendError("nope")


def test_structured_unsupported_capability_propagates():
    rt = StructuredRuntime(_NoGenerate())
    with pytest.raises(BackendError):
        rt.embed(["a"])


def test_generate_structured_rejects_grammar_plus_schema():
    # Release-gate regression: grammar and json_schema are mutually
    # exclusive in GenerationOptions, so a schema argument plus an
    # options grammar is a conflict, not a merged request.
    rt = StructuredRuntime(FakeRuntime())
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    opts = GenerationOptions(grammar='root ::= "a"')
    with pytest.raises(SpecError, match="conflicts"):
        rt.generate_structured("hi", schema, opts)
