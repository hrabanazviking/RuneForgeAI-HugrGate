# Slice 493 — Privacy leak gauntlet

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_493_leakscan.py` (7 tests)

## What it does

Redaction machinery existed (`privacy_redact`, `privacy_pii`,
per-class provenance modes) but nothing proved secrets couldn't
escape through observable surfaces. `hugrgate/gauntlet/leakscan.py`
plants canary values in decision state and scans:

1. **log records** emitted during `decide` (captured handler,
   incl. the cache-hit path),
2. **exception messages** from failing decisions,
3. **provenance records** under `strict` / `forbidden` privacy
   classes.

`run_leak_gauntlet()` returns a `LeakReport`; `clean` is True only
when no canary appears anywhere.

## Findings along the way

- **Environment scrubber vs. canaries:** values shaped like real
  secrets (`sk-...`) are redacted by the execution environment
  itself in transit — a gauntlet built on them would pass
  vacuously. Canaries are inert by construction
  (`canary-secret-0001`, …) and verified to survive both the
  environment scrubber and hugrgate's `SecretScanner`.
- **Anti-theater proof:** `test_gauntlet_catches_a_planted_leak`
  registers a backend whose error message echoes state and
  asserts the gauntlet flags it — the gauntlet is not a
  rubber stamp.

## Verification

7 tests green — full battery clean on the honest gate, leak
caught on the planted-leak gate; `ruff`/`mypy` clean.
