"""Slice 165 — JSON-schema constrained decoding.

Unit tests for ``hugrgate.runtimes.jsonschema``: schema -> GBNF
compilation and the constraining wrapper.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import BackendError, SpecError
from hugrgate.runtimes import (
    CAP_GRAMMAR,
    FakeRuntime,
    GenerationOptions,
    GenerationResult,
)
from hugrgate.runtimes.grammar import Grammar
from hugrgate.runtimes.jsonschema import (
    JsonSchemaConstrainedRuntime,
    json_schema_to_gbnf,
    uncompilable_keywords,
)


def _grammar_rt():
    class G(FakeRuntime):
        name = "g"

        def __init__(self):
            super().__init__(supports=frozenset({CAP_GRAMMAR,
                                                "generate"}))
            self.seen: list[GenerationOptions] = []

        def generate(self, prompt: str,
                     options: GenerationOptions | None = None
                     ) -> GenerationResult:
            self.seen.append(options or GenerationOptions())
            return GenerationResult(text='{"ok": true}',
                                    finish_reason="constrained")

    return G()


# -- json_schema_to_gbnf -------------------------------------------------------------------

def test_compiles_object_with_required_and_optional():
    schema = {"type": "object",
              "properties": {"name": {"type": "string"},
                             "age": {"type": "integer"}},
              "required": ["name"]}
    gbnf = json_schema_to_gbnf(schema)
    Grammar.from_gbnf(gbnf)  # validates
    assert '"name"' in gbnf.replace('\\"', '"')
    assert ")?" in gbnf  # optional age is a nested optional group


def test_compiles_nested_types():
    schema = {"type": "object",
              "properties": {
                  "tags": {"type": "array",
                           "items": {"type": "string"}},
                  "score": {"type": "number"},
                  "active": {"type": "boolean"},
                  "nick": {"type": "null"},
              },
              "required": ["tags", "score", "active", "nick"]}
    gbnf = json_schema_to_gbnf(schema)
    Grammar.from_gbnf(gbnf)
    assert "[0-9]" in gbnf  # number rule present


def test_compiles_enum_and_const():
    gbnf = json_schema_to_gbnf({"enum": ["a", "b"]})
    Grammar.from_gbnf(gbnf)
    assert '"a"' in gbnf and '"b"' in gbnf
    gbnf = json_schema_to_gbnf({"const": 42})
    Grammar.from_gbnf(gbnf)


def test_compiles_anyof_oneof():
    gbnf = json_schema_to_gbnf(
        {"anyOf": [{"type": "string"}, {"type": "integer"}]})
    Grammar.from_gbnf(gbnf)
    gbnf = json_schema_to_gbnf(
        {"oneOf": [{"type": "string"}, {"type": "null"}]})
    Grammar.from_gbnf(gbnf)


def test_compiles_type_union():
    gbnf = json_schema_to_gbnf({"type": ["string", "null"]})
    Grammar.from_gbnf(gbnf)


def test_compiles_local_ref():
    schema = {"$defs": {"name": {"type": "string"}},
              "type": "object",
              "properties": {"n": {"$ref": "#/$defs/name"}},
              "required": ["n"]}
    gbnf = json_schema_to_gbnf(schema)
    Grammar.from_gbnf(gbnf)


def test_compiles_empty_object():
    gbnf = json_schema_to_gbnf({"type": "object"})
    Grammar.from_gbnf(gbnf)
    assert '"{"' in gbnf


def test_rejects_empty_schema():
    with pytest.raises(SpecError):
        json_schema_to_gbnf({})


def test_rejects_false_schema():
    with pytest.raises(SpecError, match="matches nothing"):
        json_schema_to_gbnf(False)


def test_uncompilable_keywords_reported():
    schema = {"type": "string", "pattern": "^a+$", "minLength": 2,
              "properties": {"x": {"type": "integer", "minimum": 0}}}
    found = uncompilable_keywords(schema)
    assert found == ["minLength", "minimum", "pattern"]


# -- JsonSchemaConstrainedRuntime ------------------------------------------------------------------

SCHEMA = {"type": "object",
          "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"],
          "additionalProperties": False}


def test_constrains_and_validates():
    inner = _grammar_rt()
    rt = JsonSchemaConstrainedRuntime(inner)
    out = rt.generate("prompt", GenerationOptions(json_schema=SCHEMA))
    assert out.finish_reason == "constrained"
    seen = inner.seen[0]
    assert seen.grammar is not None
    Grammar.from_gbnf(seen.grammar)  # what we sent was valid GBNF
    # Contract: grammar and json_schema stay mutually exclusive —
    # the schema travels in the wrapper, not in options.
    assert seen.json_schema is None


def test_generate_constrained_returns_parsed():
    inner = _grammar_rt()
    rt = JsonSchemaConstrainedRuntime(inner)
    result, parsed = rt.generate_constrained("prompt", SCHEMA)
    assert parsed == {"ok": True}
    assert result.finish_reason == "constrained"


def test_passthrough_without_schema():
    inner = _grammar_rt()
    rt = JsonSchemaConstrainedRuntime(inner)
    rt.generate("prompt")
    assert inner.seen[0].grammar is None


def test_refuses_without_grammar_capability():
    rt = JsonSchemaConstrainedRuntime(FakeRuntime())
    with pytest.raises(BackendError, match="grammar support"):
        rt.generate("prompt", GenerationOptions(json_schema=SCHEMA))


def test_invalid_output_raises():
    class Bad(FakeRuntime):
        name = "bad"

        def __init__(self):
            super().__init__(supports=frozenset({CAP_GRAMMAR,
                                                "generate"}))

        def generate(self, prompt: str,
                     options: GenerationOptions | None = None
                     ) -> GenerationResult:
            return GenerationResult(text='{"ok": "yes"}',
                                    finish_reason="constrained")

    rt = JsonSchemaConstrainedRuntime(Bad())
    with pytest.raises(BackendError, match="failed validation"):
        rt.generate("prompt", GenerationOptions(json_schema=SCHEMA))


def test_non_json_output_raises():
    class Worse(FakeRuntime):
        name = "worse"

        def __init__(self):
            super().__init__(supports=frozenset({CAP_GRAMMAR,
                                                "generate"}))

        def generate(self, prompt: str,
                     options: GenerationOptions | None = None
                     ) -> GenerationResult:
            return GenerationResult(text='no json here',
                                    finish_reason="constrained")

    rt = JsonSchemaConstrainedRuntime(Worse())
    with pytest.raises(BackendError, match="no JSON"):
        rt.generate("prompt", GenerationOptions(json_schema=SCHEMA))


def test_wrapper_info_health_privacy():
    rt = JsonSchemaConstrainedRuntime(_grammar_rt())
    assert rt.info().name == "g+jsonschema"
    assert "json_schema" in rt.info().capabilities
    assert rt.health()["json_schema_constrained"] is True
    assert rt.privacy()["remote"] is False
    rt.close()
