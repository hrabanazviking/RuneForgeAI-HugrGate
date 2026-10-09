# Slice 427 — OpenAPI stabilization

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_427_openapi.py` (18 tests)

## What existed

FastAPI auto-generated an OpenAPI schema, but it was undocumented
contract surface: routes had no tags, summaries, or descriptions;
`/decide` (which reads the raw request body for taxonomy-precise
422s) exposed **no request schema at all**; error responses were
undocumented; and there was no way to dump or diff the schema.

## What changed

- `hugrgate/server.py`:
  - `DecideRequest` / `ErrorBody` / `ProtocolBody` Pydantic models —
    the documented wire contract. The `/decide` handler validates
    the raw body against the *same* `DecideRequest` model before any
    spec/policy parsing, so malformed envelopes (non-object body,
    missing `spec`/`state`, wrong field types) now get structured
    422/400 taxonomy errors instead of accidental 500s.
  - Every route carries `tags`, `summary`, `description`; `/decide`
    documents its 400/422/502/503 error envelopes; `/protocol` uses
    `response_model=ProtocolBody`.
  - `dump_openapi_schema()` generates the schema from the live route
    table and documents the `/decide` request body with the
    `DecideRequest` component (the one object the handler validates
    with), so the published contract cannot drift from runtime
    validation.
- `hugrgate/cli.py`: new `hugrgate openapi [--out FILE]` command
  dumping the stabilized schema.

## Verification

18 new tests: schema info/version match the package; all six routes
present, tagged, and summarized; `DecideRequest` requires
spec+state; error statuses documented; malformed envelope →
structured 422 (never 500); non-object body → 400; CLI dump writes
valid JSON. `ruff`/`mypy` clean.

## Commands run

- `pytest tests/test_deveco_427_openapi.py tests/test_deveco_426_protocol.py` — 43 passed
- `python -m hugrgate.cli openapi` equivalent via `main(["openapi", ...])` in tests
