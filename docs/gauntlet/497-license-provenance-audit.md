# Slice 497 — License/provenance audit

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_497_license.py` (8 tests)

## What it does

`hugrgate/gauntlet/license_audit.py` + `tools/license_audit.py`:

- inventories installed distributions via `importlib.metadata`,
  normalizing `License` / `License-Expression` into SPDX-ish
  tokens (compound `A AND B` expressions split per token);
- classifies each package: **allow** (permissive allowlist —
  MIT, Apache-2.0, BSD, PSF, ISC, 0BSD, Zlib, Unlicense,
  CC0-1.0, BSL-1.0, MPL-2.0 with documented rationale),
  **review** (GPL/AGPL/LGPL copyleft — surfaced, never silently
  passed), **unknown** (no/unrecognized declaration);
- resolves the **runtime dependency closure** from
  `pyproject.toml` `dependencies` (regex parse — no tomllib, so
  it runs on 3.10) and audits that closure, not the dev venv.

## Measured result (real data)

`docs/gauntlet/497-license-manifest.json`:

- **runtime closure: CLEAN** — `hugrgate` (Apache-2.0) +
  `PyYAML 6.0.3` (MIT). The 1.0 tree carries no copyleft.
- full venv (`--all`): 36 allow, 1 review, 1 unknown —
  `scipy` (dev-only; its license text mentions bundled
  LGPL-2.1 libquadmath → flagged for human review, correctly
  conservative) and `pathspec` (lint-only; MIT in reality,
  missing license metadata — upstream metadata gap).

## Verification

8 tests green; `ruff`/`mypy` clean; CLI exits 0 on the runtime
closure, 1 on the full venv (by design — review items exist).
