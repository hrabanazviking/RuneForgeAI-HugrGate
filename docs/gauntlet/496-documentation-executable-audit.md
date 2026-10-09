# Slice 496 — Documentation executable audit

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_496_docsaudit.py` (9 tests)

## What it does

`tools/docs_exec_audit.py` — extracts every ` ```python ` block
from given Markdown files and executes each in a subprocess
(repo root on `PYTHONPATH`, per-block timeout). Blocks whose
first line is `# noexec: reason` are reported as SKIP.
Exit 0 iff every executed block passes.

## Real findings (fixed in this slice)

The first run over the 6 docs carrying python blocks found **6
of 7 failing** — genuine doc-vs-code drift:

- `docs/quickstart.md` and `docs/ladder.md` showed a stale
  `LadderRouter([{...}])` dict-rung form; the real API is
  `LadderRouter(registry, rungs=[LadderRung(...)])`. Both
  snippets rewritten to the real, runnable API.
- `docs/evlab/evaluation-lab.md` used `{...}` set-literals where
  the code requires dicts — replaced with realistic shapes and
  marked `# noexec` (still needs a populated gate).
- `docs/api.md`, `docs/calibration.md`,
  `docs/campaign-xiv/observability.md` — illustrative fragments
  that cannot run standalone; marked `# noexec` with reasons.

After fixes: **3 PASS, 4 honest SKIP, 0 failed**
(`test_gauntlet_docs_audit_clean` locks this in).

## Verification

9 tests green (tool unit tests + the live docs audit);
`ruff`/`mypy` clean.
