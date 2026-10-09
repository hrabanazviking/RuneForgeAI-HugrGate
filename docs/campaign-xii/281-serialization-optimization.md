# Slice 281 — Serialization optimization

**Status:** complete. Commit: `feat(gjallarbu-281)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

`hugrgate/serde.py` had only the canonical dict form. Measured on a
64-option result: `to_dict` 1.45µs, `result_from_dict` 13.9µs
(decode dominated by `__post_init__` re-validation — 66 `isinstance`
calls per decode — plus dict key hashing on both ends).

## What was built

- `hugrgate/serde.py`:
  - `result_to_compact` / `result_from_compact`,
    `policy_to_compact` / `policy_from_compact`: versioned positional
    list encoding (`COMPACT_VERSION = 1`; field-order constants
    `_RESULT_FIELDS`/`_POLICY_FIELDS` wire the length checks).
    Encode aliases `distribution`/`metadata` (no copy — documented
    read-only contract, the slice-280 synergy); decode copies
    defensively and re-validates all invariants.
  - JSON-serializable, so it composes with
    `zerocopy.SharedPayload` for cluster transport.
  - `policy_from_dict`: `d.keys() - _POLICY_KEYS` instead of
    `set(d) - _POLICY_KEYS` (avoids an intermediate set build).
- `hugrgate/errors.py`: new `SerdeError` (`code="serde_error"`,
  `recoverable=False` — a malformed payload is a caller bug);
  registered in `tests/test_errors.py`. Malformed compact payloads
  (bad version, wrong length, non-list) now raise taxonomy errors
  instead of `IndexError`/`TypeError` deep in unpacking.

## Measured results (this host, 64-option result, µs/op)

| op | dict form | compact | delta |
|---|---|---|---|
| encode | 1.45 | 0.36 | **4.0x faster** |
| decode | 13.9 | 14.9 | parity (validation-bound by design) |
| wire bytes | 2307 | 2157 | 6.5% smaller |

Decode parity is deliberate: `result_from_compact` re-runs the full
`DecisionResult` invariant checks. Skipping re-validation would be
faster and wrong — the rail stays.

## Tests

`tests/test_perf_281_serde.py` — 17 tests: lossless round-trips,
dict/compact semantic equivalence, JSON-serializability, aliasing
contract, defensive decode copy, malformed-payload rejection
(SerdeError), version stability, **measured** encode speedup, decode
no-regression bound, unknown-policy-key rejection preserved. The
existing `test_serialization_contracts.py` suite still passes
unchanged. All green; ruff clean; import-cycle test green.
