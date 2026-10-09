# Slice 498 — Release candidate build

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_498_rcbuild.py` (9 tests)

## What it does

`tools/rc_build.py` — builds the sdist + wheel (`python -m build`)
and verifies the release candidate end to end:

1. both artifacts exist with canonical names;
2. wheel METADATA: name, version, requires-python, requires-dist;
3. `entry_points.txt` declares `hugrgate → hugrgate.cli:main`
   and `hugrgate-server → hugrgate.daemon:main`;
4. smoke install: wheel installed `--no-deps` into a temp dir,
   then `import hugrgate`, both entry-point mains run `--help`,
   and one live `decide` succeeds.

## Measured evidence (built 2026-10-09, this machine)

- `hugrgate-1.0.0-py3-none-any.whl` + `hugrgate-1.0.0.tar.gz` —
  **5/5 checks passed** (rebuilt and re-verified after the slice
  500 version bump; the earlier 0.1.0 artifacts verified the same
  procedure)
- METADATA: `Name: hugrgate`, `Version: 1.0.0`,
  `Requires-Python: >=3.10`, sole unconditional
  `Requires-Dist: pyyaml>=6.0` (rest are extras)
- entry points verified present and correct; smoke decision
  returned the expected value

Build deps (`build`, `hatchling`) were installed in a throwaway
venv (`/tmp/rcbuild-venv`); artifacts went to `/tmp/rc-dist-100`
— nothing committed.

## Verification

9 tool unit tests green; `ruff`/`mypy` clean; the full
`rc_build.py` run passed 5/5 live.
