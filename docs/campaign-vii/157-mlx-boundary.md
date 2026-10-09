# Slice 157 — MLX adapter boundary

## Skald (what already existed)
- No Apple-silicon path. MLX (`mlx-lm`) only runs on Darwin/arm64,
  so the adapter is a *boundary*: a precise, testable statement of
  where the fabric ends and the platform begins.

## Rúnhild (design)
`hugrgate/runtimes/mlx.py::MLXRuntime`: `platform_supported()` is a
pure function of an injectable `(system, machine)` pair, so both sides
of the boundary are unit-testable on any host. `available()` =
supported platform AND importable `mlx_lm` (lazy, `mlx` extra).
Every operation re-checks the boundary and raises
`BackendUnavailable` naming the missing side (wrong platform vs
missing package) — never a raw `ImportError`. Generation follows the
`mlx_lm` convention (`load(repo)`, `generate(model, tokenizer,
prompt, max_tokens, temp, top_p, seed)`); timeouts cooperative.

## Eldra (what was built)
- `hugrgate/runtimes/mlx.py` (new): `MLXRuntime`,
  `SUPPORTED_PLATFORM`, injectable platform + engine.
- `pyproject.toml`: `mlx = ["mlx-lm>=0.16"]` extra.
- `tests/test_dependency_rules.py`: `THIRD_PARTY_PROVIDERS["mlx_lm"]`
  + `"mlx-lm" -> "mlx_lm"` dist normalization.
- `tests/test_localrt_157_mlx.py` (new, 17 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_157_mlx.py tests/test_dependency_rules.py
-q` → all passed. `ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; the `mlx` extra is consumed by a real importer.

## Scribe
Commit `feat(gjallarbu-157): mlx adapter boundary` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- On an Apple-silicon Mac with `mlx-lm`: `platform_supported()`
  true, `mlx_lm.load("mlx-community/...")` real load, `generate`
  kwarg names (`temp` vs `temperature`) against installed version.
