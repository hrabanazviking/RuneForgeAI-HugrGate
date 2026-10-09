# Slice 435 — CLI UX overhaul

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_435_cli_ux.py` (15 tests), `tests/test_deveco_435_doctor_live.py` (1 slow test)

## What existed

The CLI spoke JSON only, had no health-of-deployment story, no
shell completions, and mistyped subcommands died with a bare
argparse error.

## What changed

- `hugrgate/cli.py`:
  - Global `--format {json,table,yaml}` (default json — machine
    output unchanged). `decide`, `backends`, `models`, `health`
    render aligned plain-text tables; `yaml` via the base-install
    PyYAML dependency. Dependency-free table renderer.
  - New `hugrgate doctor [--url]`: four checks — service
    reachability, protocol version agreement (client vs service),
    backend inventory, and a live end-to-end decision. One line
    per check, exit 1 with a failure summary when anything fails;
    probes never crash on transport errors.
  - New `hugrgate completion {bash,zsh,fish}`: generated
    completion scripts listing real subcommands (from the live
    parser, so they can't drift), with `--format` value
    completion and file completion fallbacks.
  - Did-you-mean: mistyped subcommands suggest the closest match
    (`decid` → `did you mean 'decide'?`).

## Verification

15 unit tests (table alignment, json default preserved, yaml,
decide/backends/models table forms, all three completion
scripts, did-you-mean, bad `--format` rejected, doctor all-pass /
unreachable / protocol-skew via stubbed client) + 1 slow test:
`doctor` exit 0 against a real uvicorn server with all four
checks green. `ruff`/`mypy` clean.

## Commands run

- `pytest tests/test_deveco_435_cli_ux.py tests/test_deveco_435_doctor_live.py` — 16 passed
