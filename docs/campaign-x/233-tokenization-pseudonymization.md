# Slice 233 — Tokenization / pseudonymization

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_tokens.py` (14 tests)

## What existed

`TokenRedactor` (slice 232) was defined against a duck-typed vault
that didn't exist yet — the pipeline had a reversible-redaction
strategy with nothing behind it.

## What changed

- New module `hugrgate/privacy_tokens.py`:
  - `TokenVault` — in-memory token→value vault. Tokens are 192-bit
    CSPRNG outputs (`hgptok_<namespace>_<rand>`), opaque and unique
    per minting. `tokenize` / `detokenize` (deep-copy isolated),
    `revoke`, `clear`, `tokenize_state`, `export` / `import_vault`
    (for encrypted persistence in slices 241-242).
  - Namespace isolation: tokens never detokenize across namespaces
    or vault instances. Unknown tokens raise `KeyError`; non-tokens
    raise `TypeError`.

## Verification

- `pytest tests/test_privacy_tokens.py` — 14 passed, including
  adversarial token-tampering and cross-vault replay, plus
  end-to-end `TokenRedactor` pipeline integration.
- `ruff check` clean.
