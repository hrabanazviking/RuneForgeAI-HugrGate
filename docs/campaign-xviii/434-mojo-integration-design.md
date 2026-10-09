# Slice 434 — Mojo integration design

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_434_mojo.py` (6 tests)

## What existed

No path for Mojo (Modular's systems language for AI workloads) to
reach HugrGate.

## What changed

- `sdks/mojo/hugrgate_mojo.mojo` — design-complete Mojo binding
  over the stable C ABI via `sys.ffi.external_call`:
  - ABI mirror: `hg_status_t` = `Int32`, frozen status-code
    aliases, `HG_PROTOCOL_VERSION`;
  - raw FFI declarations for all nine C ABI functions;
  - LP64 struct-field offset aliases for `hg_error_t` and
    `hg_decision_t` with `UnsafePointer` load helpers;
  - `_raise_for_status`: ABI failures become Mojo `Error`s (the
    error object is always freed; abstention surfaces as a
    matchable error, not a crash);
  - owned `Decision` / `Client` structs (`Movable`, `__del__`
    frees via `hg_decision_free` / `hg_client_free`);
  - `Client.decide` keeps `Optional[String]` arguments alive for
    the call and passes null pointers when absent;
    `Client.protocol()` copies the JSON out and frees it;
  - `main()` demo: protocol advertisement + one decision.
- Build recipe documented in the file header (compile the C
  client as `libhugrgate_client.so`, `mojo build -L/-l`).

## Verification

The Mojo toolchain is not installed in this environment — stated
plainly. `tests/test_deveco_434_mojo.py` verifies with teeth:
every `external_call["hg_..."]` symbol exists in `hugrgate.h`;
all nine ABI functions are bound; **the LP64 struct offsets in the
Mojo file match offsets computed from the header's own field
declarations** (layout drift between the two files is caught);
status-code aliases mirror the frozen header values; ownership
wrappers and error raising are present. 6 passed.

## Commands run

- `pytest tests/test_deveco_434_mojo.py` — 6 passed
