# Slice 429 — TypeScript SDK

**Date:** 2026-10-09 · **Tests:** `sdks/typescript/src/index.test.ts` (15 tests, `node --test`), `tests/test_deveco_429_ts_sdk.py` (gate)

## What existed

No TypeScript client: browser and Node.js integrations had to
hand-roll `fetch` calls against the HTTP API with no shared types,
no error mapping, and no retry policy.

## What changed

- `sdks/typescript/` — `@runeforgeai/hugrgate` (v0.1.0):
  - `src/index.ts`: `HugrGateClient` with `decide`,
    `decideBatch` (per-item errors returned in place),
    `decideValue`, `health` (never throws),
    `backends`, `models`, `protocol`, `close`;
    `HugrGateError` (code/message/recoverable/details) mapped from
    service error envelopes, `Abstention`, `SDKError`;
    `PROTOCOL_VERSION` sent on every `/decide` request;
    versioned `User-Agent: hugrgate-sdk-ts/2.0`;
    exponential-backoff retry on recoverable faults only
    (network errors, HTTP 502/503/504); strict `strict: true`
    compile with `noUncheckedIndexedAccess`.
  - `src/index.test.ts`: 15 tests against a stub HTTP server —
    protocol advertisement, User-Agent, decision metadata stamping,
    abstention, no-retry-on-422, 503-retry-then-succeed,
    hang-gives-up-as-`SDKError`, batch per-item errors,
    `decideValue`, health reachability/never-throws, backends,
    close safety.
  - `package.json` (`build`/`test` scripts), `tsconfig.json`
    (strict), `README.md` with usage and semantics.
- `tests/test_deveco_429_ts_sdk.py` (gate): runs `npm test`
  (tsc + node --test) from pytest; skips when the TS toolchain is
  absent.
- `.gitignore`: `sdks/typescript/node_modules|dist`,
  `sdks/rust/target`.

## Verification

`tsc` strict clean; `npm test` — 15 passed; pytest gate — 2 passed.

## Commands run

- `cd sdks/typescript && npm test` — 15 passed
- `pytest tests/test_deveco_429_ts_sdk.py` — 2 passed
