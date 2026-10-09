# Slice 165 — JSON-schema constrained decoding

## Skald (what already existed)
- Slice 163: post-hoc JSON extraction + validation.
- Slice 164: GBNF grammars + enforcement wrapper.
- Missing: the bridge — compiling a JSON schema *into* a grammar so
  decoding is constrained *and* the output validated.

## Rúnhild (design)
`hugrgate/runtimes/jsonschema.py`: `json_schema_to_gbnf` recursively
compiles schemas to GBNF (objects with required-then-optional nested
groups in declaration order, arrays, strings with the standard
JSON string rule, integers/numbers/booleans/null, enums, consts,
anyOf/oneOf, type unions, local `$ref` inlined beforehand).
Keywords GBNF cannot express (pattern, min/max length, numeric
bounds, min/max items, additionalProperties) are reported by
`uncompilable_keywords` and still enforced post-hoc.
`JsonSchemaConstrainedRuntime` composes 163+164: compile → validate
grammar → enforce via inner `CAP_GRAMMAR` runtime → extract → validate
→ `BackendError` on any failure.

## Eldra (what was built)
- `hugrgate/runtimes/jsonschema.py` (new): `json_schema_to_gbnf`,
  `uncompilable_keywords`, `JsonSchemaConstrainedRuntime`.
- `tests/test_localrt_165_jsonschema.py` (new, 17 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_165_jsonschema.py -q` → 17 passed.
`ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Reuses `Grammar`/`gbnf_escape` (164) and `extract_json`/`validate`
  (163); no duplication. `GenerationOptions.json_schema` now has a
  full enforcement path on grammar-capable runtimes.

## Scribe
Commit `feat(gjallarbu-165): json-schema constrained decoding` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Compiled GBNF against real llama.cpp for representative schemas
  (nested objects, anyOf) — accepted and constrains as intended.
