# Campaign XVIII — Developer Ecosystem: Completion Report

**Branch:** `gjallarbu/campaign-xviii` · **Base:** `origin/main` @ `d522433`
**Slices:** 426–450 (25) · **Date:** 2026-10-09

## Mission

Make the HugrGate developer experience coherent and delightful:
stable protocol, SDKs in six languages, plugin API, CLI tooling,
conformance kits, executable docs, migration paths, deployment
packaging — without duplicating the existing CLI, client, API
inventory, or eval lab.

## Slice log

| Slice | Title | Commit | Tests |
|-------|-------|--------|-------|
| 426 | Stable protocol v1 | `0176c24` | protocol negotiation, envelope |
| 427 | OpenAPI stabilization | `d7fa720` | Pydantic models, `hugrgate openapi` |
| 428 | Python SDK v2 | `2fc25c5` | retries, batch, taxonomy mapping |
| 429 | TypeScript SDK | `3f5889c` | 15 node tests, real |
| 430 | Rust SDK | `487b0c3` | structural (no cargo) |
| 431 | Go SDK | `7f30166` | structural (no go toolchain) |
| 432 | C ABI design | `9c276f9` | gcc -Werror clean, C99 + C++11 |
| 433 | C client prototype | `203e96f` | 9 live socket e2e, ASan/UBSan clean |
| 434 | Mojo integration design | `b2d4428` | FFI offsets cross-checked |
| 435 | CLI UX overhaul | `f5ef902` | formats, doctor, completion |
| 436 | Interactive inspector | `6d642ec` | REPL, 15 tests |
| 437 | Config generator | `84cd9aa` | init/gen/serve --config, 22 tests |
| 438 | Project scaffolder | `cb257cd` | generated pytest suite runs |
| 439 | Backend plugin SDK | `1c8c52b` | entry-point discovery, 15 tests |
| 440 | Backend conformance kit | `fa12fee` | `hugrgate check-backend`, 11 tests |
| 441 | Contract conformance kit | `49e3d7b` | `hugrgate check-contract`, 10 tests |
| 442 | Example gallery | `ecd8abb` | `docs/dev-gallery.md`, 9 tests (slow) |
| 443 | Cookbook | `1cd0008` | `docs/cookbook.md`, recipes executed, 8 tests (slow) |
| 444 | Migration guide | `845251e` | `hugrgate/compat.py`, `docs/migration.md`, 7 tests |
| 445 | Deployment guide | `f24fb46` | `docs/deployment.md` (smoke-tested) |
| 446 | Docker packaging | `84f9e5e` | multi-stage image + compose, 8 tests |
| 447 | Systemd packaging | `f27ec2f` | hardened unit, 6 tests |
| 448 | Windows service guide | `1ab680d` | NSSM script + guide, 6 tests |
| 449 | macOS launchd guide | `47987be` | plist + guide, 6 tests |
| 450 | Release gate | *(this commit)* | `test_deveco_450_release_gate.py`, 5 tests (gate) |

## Weaknesses found and fixed along the way

- The 440 kit caught the kit itself second-guessing binary
  value spaces (now uses `DecisionSpec.value_space()`), and
  over-strict distribution/taxonomy demands on the built-ins.
- The 441 kit caught `DecisionResult` validating distributions
  at construction (documented, not fought).
- Cookbook recipes exposed two real API misuses: `Abstention`
  is *raised* by `decide`, and sample backends must honor
  `spec.options`.
- The 444 work broke a latent `cli ↔ inspect` import cycle
  (slice 436) — fixed via `hugrgate/loaders.py`; also repaired
  `test_dependency_rules` stdlib allowlist gaps from slices
  435/436/438.
- The 445 guide initially misdocumented `hugrgate gen daemon`
  output redirection — corrected to `--out`.

## Verification

- New tests: ~150 across the campaign's test modules.
- `ruff` and `mypy` clean on all new/changed code.
- `test_import_cycles` + `test_dependency_rules` green.
- Release gate (`test_deveco_450_release_gate.py`, gate):
  protocol version consistent across code, server, and SDKs;
  `hugrgate openapi` matches the live app schema; SDK parity
  matrix holds; every CLI command documented; every slice
  documented.
- Full suite: run before push (see push notes).

## What was NOT done

- Rust/Go/Mojo SDKs are genuine code with structural tests
  only — no cargo/go/mojo toolchains in this environment.
- Docker image not build-verified (no daemon here); the
  packaging is structurally linted by tests.
- PowerShell script content-checked only (no pwsh here).

## Files of note for operators

- `docs/deployment.md` — run it in production
- `docs/migration.md` + `hugrgate/compat.py` — upgrade paths
- `docs/cookbook.md`, `docs/dev-gallery.md` — learn it
- `deploy/{docker,systemd,windows,macos}/` — package it
