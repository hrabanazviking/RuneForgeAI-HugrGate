# Slice 447 — Systemd packaging

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_447_systemd.py` (6 tests)

## What existed

No service packaging; operators wrote their own units.

## What changed

- `deploy/systemd/hugrgate.service` (new): `Type=simple`,
  `User=hugr`, config-file `ExecStart`, `Restart=on-failure`,
  systemd hardening (`NoNewPrivileges`, `ProtectSystem=full`,
  …), install instructions in the header comment.
- `tests/test_deveco_447_systemd.py` (new): configparser
  structural assertions plus a real `systemd-analyze verify`
  run.

## Notes

- `systemd-analyze verify` on this container exits non-zero
  because of the container's own broken timers
  (motd-news/apt-daily) — unrelated system noise. The test
  asserts no diagnostic names our unit except the known
  missing-binary artifact (hugrgate not installed system-wide
  here).

## Verification

6 passed. `ruff`/`mypy` clean.

## Commands run

- `systemd-analyze verify deploy/systemd/hugrgate.service`
- `pytest tests/test_deveco_447_systemd.py` — 6 passed
