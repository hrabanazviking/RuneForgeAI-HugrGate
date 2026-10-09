# Slice 436 — Interactive inspector

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_436_inspect.py` (15 tests)

## What existed

Every CLI invocation was one-shot: exploring a service meant
retyping full commands and re-reading JSON.

## What changed

- `hugrgate/inspect.py` (new): `InspectSession` REPL —
  `help`, `url [URL]` (show/switch service), `health`,
  `protocol`, `backends`, `models`, `decide <spec> <state>
  [--backend NAME] [--policy FILE]`, `last` (full detail of the
  previous decision), `quit|exit|q`. Errors print inline and never
  kill the loop; `Ctrl-D`/`Ctrl-C` exit cleanly; readline history
  when available; `shlex` parsing so quoted paths work.
- `hugrgate/cli.py`: `hugrgate inspect [--url]` wiring.
- `tests/test_dependency_rules.py`: `hugrgate.inspect` joins the
  SERVICE layer (it drives the client like the CLI).

## Verification

15 tests with a stubbed client: help text, unknown commands,
backends/health/protocol output, decide→last detail flow,
usage/flag/file errors, URL switching, quit variants, a full
scripted session ending in `bye.`, EOF and KeyboardInterrupt
handling. `ruff`/`mypy` clean.

## Commands run

- `pytest tests/test_deveco_436_inspect.py` — 15 passed
