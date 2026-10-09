# Slice 445 — Deployment guide

**Date:** 2026-10-09 · **Tests:** smoke checks of referenced commands

## What existed

Deployment knowledge was scattered across CLI help, the daemon
module, and campaign docs — no single operator's guide.

## What changed

- `docs/deployment.md` (new): install → configure → run →
  harden → observe → scale → upgrade. Every command referenced
  was smoke-tested; platform packaging is delegated to the
  slice 446–449 docs.

## Weaknesses found while writing (fixed here)

- The guide first claimed `hugrgate gen daemon > file`; the
  command actually writes the file itself and takes `--out`.
  Fixed before commit.

## Verification

- `hugrgate serve --help`, `hugrgate gen daemon --out`,
  `hugrgate doctor` all smoke-tested; `/health` endpoint
  confirmed in client code.
- Stray `hugrgate.yaml` / `.hugrgate-demo/` artifacts from
  smoke tests removed.

## Commands run

- `python -m hugrgate.cli serve --help` / `gen --help` / `doctor`
