# Slice 257 — Corrupt-model simulation

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_corrupt_model.py` (12 tests, green)

## What existed before

`hugrgate/runtimes/gguf.py` (slice 160) already parsed GGUF headers
defensively — bad magic, wrong version, implausible counts, and
truncated reads all raise `GGUFError`, and `discover_gguf_models`
records `error` on bad files instead of aborting the scan. But the
defense had no *adversary*: nothing systematically generated corrupt
model files to prove every corruption shape is actually caught.

## What was built

`hugrgate/chaos/model_faults.py` — `ModelCorruptor`:

- `write_valid(path)` builds a minimal **valid** GGUF from scratch
  (magic, version 3, one `general.architecture` kv pair, headers
  only — no weights, no fixtures to ship).
- `corrupt(path, kind, seed)` writes a corrupted sibling copy
  (`<stem>.corrupt-<kind>.gguf`, still discoverable); the original
  is never modified. Six kinds: `flip_magic`, `bad_version`,
  `truncate` (seeded cut point), `kv_bomb` (kv_count inflated past
  the 100 000 implausibility limit), `zero_out`, `bit_flip` (one
  seeded byte).
- Verification: `assert_rejected` (parse raises `GGUFError`,
  returns it for message assertions) and `assert_scan_survives`
  (discovery never aborts).

## Attack findings (Yrsa Law 11)

The loader held up under every attack — no new hardening was
needed, which is itself the result:

- `flip_magic` / `zero_out` → "bad magic, not a GGUF file";
- `bad_version` → version rejection naming the version;
- `truncate` at 25 seeded cut points → "truncated file" with byte
  offsets, never short reads;
- `kv_bomb` → rejected *before* any allocation ("implausible");
- `bit_flip` across 25 seeds → always `GGUFError`-or-valid,
  never a foreign exception, never a hang;
- discovery over a directory of 5 corrupt + 1 good file: 6
  models, 5 with `error` set, scan completes.

Unknown corruption kinds raise `SpecError`; corruption is
seed-reproducible byte-for-byte.

## Integration

- Error semantics: `GGUFError` (`code "gguf_error"`,
  recoverable) — the existing taxonomy already models a corrupt
  model as retryable-with-a-good-copy.
- No new error class; no production code paths touched.

## Verification

- 12 tests: parametrized rejection of all 5 must-reject kinds,
  message fragments naming each corruption, bit-flip containment
  property, seed reproducibility, unknown-kind rejection,
  discovery survival, `assert_rejected` failing loudly on valid
  files.
- `ruff check` clean.
