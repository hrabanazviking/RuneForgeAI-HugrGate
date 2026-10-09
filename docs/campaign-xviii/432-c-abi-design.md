# Slice 432 — C ABI design

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_432_c_abi.py` (9 tests)

## What existed

No C-level contract: every language binding would invent its own.

## What changed

- `sdks/c/include/hugrgate.h` — the stable C ABI, the binary
  contract every future binding (C client, Mojo, Rust, Go) builds
  on. Six stability rules documented in the header itself:
  1. `hg_client_t` is opaque (state grows behind the pointer);
  2. `hg_decision_t` is a caller-owned snapshot, passed only by
     pointer, fields appended at the end;
  3. `hg_status_t` codes frozen, append-only with `HG_STATUS_COUNT`
     sentinel;
  4. NUL-terminated UTF-8 across the boundary; inputs borrowed,
     outputs owned;
  5. every fallible function reports via `hg_error_t **`
     (`hg_error_free(NULL)` is a no-op);
  6. C99-clean, C++-compatible (`extern "C"`), no bitfields, no
     `bool` in the ABI.
- API: `hg_client_new/free`, `hg_client_decide`,
  `hg_decision_free`, `hg_client_protocol` (JSON advertisement),
  `hg_status_message`, `hg_status_recoverable`,
  `hg_error_free`, `hg_free_string`; version macros
  `HUGRGATE_ABI_VERSION_MAJOR/MINOR`, `HUGRGATE_PROTOCOL_VERSION`,
  `HUGRGATE_SDK_VERSION`.
- Threading contract documented: one handle per thread.

## Verification

9 tests: header guard + `extern "C"`, version macros, frozen
status codes, opaque handle (no struct definition in header),
error/decision struct fields, no bitfields, `hg_` prefix on all
functions, `hg_error_t **` on fallible functions, no C++-only
constructs, **real `gcc -fsyntax-only -Werror` compile in C99 and
C++11 modes**. All green; `ruff` clean.

## Commands run

- `pytest tests/test_deveco_432_c_abi.py` — 9 passed
