# Slice 442 — Example gallery

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_442_gallery.py` (9 tests, slow)

## What existed

Eight runnable examples with good docstrings but no index and no
guarantee they keep working.

## What changed

- `docs/dev-gallery.md` (new): gallery index — learning-path
  table (beginner → advanced), per-example sections (what it
  shows, concepts, related docs), and a "contributing an example"
  checklist.
- `tests/test_deveco_442_gallery.py` (new, slow): runs every
  `examples/*.py` in a subprocess with the repo venv (exit 0
  required) and asserts the gallery doc mentions each script.

## Verification

All 8 examples ran green by hand first (~15 s total); the suite
re-runs them (9 passed in 19 s). `ruff`/`mypy` clean.

## Commands run

- `for f in examples/*.py; do venv/bin/python $f; done` — all rc=0
- `pytest tests/test_deveco_442_gallery.py` — 9 passed
