# Contributing to HugrGate

## Provenance First

Every contribution must have clean provenance. See `CLEAN_ROOM.md`.
Do not submit code derived from proprietary sources or
incompatible licenses.

## Development

```bash
python3 -m venv venv
venv/bin/pip install -e ".[test]"
venv/bin/pytest
```

## Standards

- Production quality: no stubs, no TODOs in merged code.
- Every module has tests in `tests/`.
- Public APIs documented with docstrings.
- ADRs for architectural decisions in `docs/adr/`.

## License

Apache-2.0. By contributing you agree your contributions are
licensed under the same terms.
