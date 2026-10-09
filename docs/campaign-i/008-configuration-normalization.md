# Slice 008 — Configuration normalization

**Date:** 2026-10-09 · **Tests:** `tests/test_config.py` (15 tests)

## Findings

- `DecisionPolicy(privacy_class="stirct")` was silently accepted and
  treated as `"standard"` — a typo disarming strict privacy without a
  sound. Privacy-relevant silent failure.
- `policy_from_dict`, `DecisionSpec.from_dict` silently dropped unknown
  keys: a misspelled key fell back to its default with no signal.
- `DaemonConfig` had no validation at all (`port=0`, `max_batch=0`
  accepted) and no serialization.

## Changes

- `DecisionPolicy.__post_init__`: `privacy_class` must be one of
  `("standard", "strict")` (new `PRIVACY_CLASSES` constant);
  `maximum_latency_ms` must be > 0, `max_cost` >= 0 when set.
- `policy_from_dict` / `DecisionSpec.from_dict`: reject unknown keys
  with `PolicyError` / `SpecError` naming the offending keys.
- `DaemonConfig`: `__post_init__` validates port range 1–65535,
  positive `batch_window_ms`/`max_batch`/`max_queue`, non-negative
  `drain_timeout_s`, non-empty `client_id_header`; added
  `to_dict()`/`from_dict()` round-trip, with unknown-key rejection.

## Backward compatibility

`from_dict` unknown-key rejection is intentionally stricter: configs
that relied on silently-ignored keys will now fail loudly at load
time. This is the documented normalization policy (typos must not
become defaults). All previously-valid configs still load.

## Verification

`venv/bin/python -m pytest tests/test_config.py -q` — 15 passed;
mypy clean; full suite 392 passed.
