# Slice 007 — Exception taxonomy hardening

**Date:** 2026-10-09 · **Tests:** `tests/test_errors.py` (12 tests)

## What changed

- **`QueueFull` joined the taxonomy.** It was a bare `Exception` in
  `hugrgate.daemon`; it is now `hugrgate.errors.QueueFull(HugrGateError)`
  with `code="queue_full"`, `recoverable=True`. Still importable as
  `hugrgate.daemon.QueueFull`, and now also exported from the package
  (`hugrgate.QueueFull`, added to `__all__` + the slice-003 API snapshot).
- **Wire round-trip.** `HugrGateError.to_dict()` /
  `HugrGateError.from_dict()` serialize `{code, message, recoverable,
  details}` losslessly, rebuilding the exact subclass via a
  code→class registry populated by `__init_subclass__`. Unknown codes
  fall back to the base class — a client never crashes on a newer
  server's error. `Abstention` preserves its `reason` through the wire.
- **`__str__`** now reads `[code] message`, so logs and audit trails
  carry the machine-readable code (e.g. ladder `detail` fields,
  fallback trace entries, the daemon 429 body).
- Subclass `__init__` signatures now take `**details: Any` (typed).

## Standing guards (`tests/test_errors.py`)

- Codes unique and pinned; `recoverable` flags pinned per class.
- Hierarchy sound (`BackendUnavailable`/`TimeoutError` ⊂ `BackendError`).
- `to_dict`/`from_dict` round-trip for every class, incl. details.
- Unknown-code fallback; chaining preserved.
- **Raise-site audit:** every `raise X` in the package must be a
  taxonomy error or a stdlib argument-validation error
  (`ValueError`/`TypeError`/…); bare `Exception` raises fail the suite.

## Backward compatibility

Additive only: one new exported name (`QueueFull`), new methods,
`__str__` enrichment. No error renamed, no code changed, no class
moved in a breaking way.

## Verification

`venv/bin/python -m pytest tests/test_errors.py -q` — 12 passed;
mypy cold-cache clean; full suite 377 passed.
