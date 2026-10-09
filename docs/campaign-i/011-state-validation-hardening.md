# Slice 011 — State validation hardening

**Date:** 2026-10-09 · **Tests:** `tests/test_state_validation.py` (9 tests)

## Gaps found in `validate_state`

| Gap | Consequence before the fix |
|---|---|
| Non-string keys | `json.dumps({1: "a"})` silently coerces to `{"1": "a"}` — key mutation invisible to the caller |
| NaN / ±Infinity | `json.dumps` emits `NaN`/`Infinity`: not valid JSON, despite the "JSON-serializable" contract |
| No depth limit | hostile nesting → `RecursionError` in serialization / cache-key hashing |
| No size limit | hostile payloads hashed into cache keys and stored in provenance unbounded |

## Changes (`hugrgate/validation.py`)

- `_check_keys`: recursive rejection of non-string mapping keys.
- `_check_finite`: iterative rejection of non-finite floats with a
  dotted path (`state.a[2]`) in the message.
- `_check_depth`: iterative depth check (no recursion of its own).
- Size check on the canonical serialized form
  (`sort_keys=True, allow_nan=False`).
- Tunable limits: `max_bytes` (default `DEFAULT_MAX_STATE_BYTES` =
  1 MiB), `max_depth` (default `DEFAULT_MAX_STATE_DEPTH` = 64).
  Signature is backward compatible (new kwargs optional); callers
  `core.decide` / `ladder` use defaults.

Each rejection raises `SpecError` with a specific `details["code"]`
(`state_key_not_string`, `state_not_finite`, `state_too_deep`,
`state_too_large`, …).

## Verification

9 new tests green; mypy clean; full suite at commit.
