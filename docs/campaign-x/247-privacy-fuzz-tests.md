# Slice 247 — Privacy fuzz tests

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_fuzz.py` (15 property tests)

## What existed

Privacy components were tested on hand-picked examples only —
exactly the inputs least likely to reveal gaps.

## What changed

- New `tests/test_privacy_fuzz.py`: 15 seeded property tests
  (stdlib `random` only, fixed seed `20261009`, reproducible)
  over randomized nested states, adversarial strings, and
  secret material. Properties: redaction idempotence and
  key-preservation, minimization projection, local-only leaf
  stripping, secret-scanner injected-secret detection, token
  vault round-trip/uniqueness/namespace isolation, SealedBox
  round-trip/tamper/wrong-key, audit-chain verification,
  dry-run non-mutation, HKDF determinism, guard verdict
  determinism.
- **Real gap found and fixed (Anti-Checkbox Rule):** the fuzzer
  injected realistic `sk-` + base64url OpenAI-style keys and the
  scanner missed them — `SECRET_PATTERNS` had no OpenAI entry.
  Added `("openai_key", r"sk-[A-Za-z0-9\-_]{20,}", "high")` plus
  a regression test. Also verified the local-only strip path
  under fuzz (leaf-granularity reporting confirmed correct;
  an early "fix" of mine was reverted after stash-testing
  proved the original behavior already stripped correctly).

## Verification

- `pytest tests/test_privacy_fuzz.py` — 15 passed.
- `pytest tests/test_privacy_secrets.py` — 24 passed
  (incl. new `test_openai_key`).
- `ruff` clean.
