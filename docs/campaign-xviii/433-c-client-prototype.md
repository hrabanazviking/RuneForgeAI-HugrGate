# Slice 433 — C client prototype

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_433_c_client.py` (9 e2e tests)

## What existed

The C ABI (slice 432) had no implementation behind it.

## What changed

- `sdks/c/src/hugrgate.c` — real POSIX-sockets implementation of
  the ABI: URL parsing (`http://` only, honest no-TLS limit),
  TCP connect with timeouts, hand-rolled HTTP/1.1 request/response,
  a minimal JSON parser **and** serializer (~350 lines, UTF-8
  escapes, nested objects/arrays), `protocol_version: "1.0"` on
  every request, `User-Agent: hugrgate-sdk-c/2.0`, service error
  envelopes mapped onto frozen `hg_status_t` codes with
  recoverability, abstention → `HG_ERR_ABSTAINED`.
- `sdks/c/e2e/smoke.c` — test driver; `sdks/c/Makefile`;
  `sdks/c/README.md` with usage and documented prototype limits.

## Verification

9 end-to-end tests: real `gcc -Werror` compile, live socket
round-trips against a scripted Python stub server — decide
success (value + backend), protocol-version/User-Agent
advertisement, abstention → status 10, 422 `spec_error` →
status 6 non-recoverable with service code, 503 →
status 9 recoverable, `/protocol` JSON, unreachable host →
status 3 recoverable, `https://` rejected, NULL args rejected.
Additionally verified **AddressSanitizer + UBSan clean** on the
decide/abstain/protocol paths. `ruff` clean.

## Commands run

- `pytest tests/test_deveco_433_c_client.py` — 9 passed
- `gcc -fsanitize=address,undefined` smoke runs — clean
