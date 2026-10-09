# Slice 176 — ARM64 compatibility audit

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_platform.py` (12 tests, green)

## What existed before

No platform awareness in HugrGate: `hugrgate/` had no `edge` package,
no host introspection, and no way to answer "is this ARM64 board a sane
deployment target?" before shipping a runtime onto it.

## What was built

New subpackage `hugrgate/edge/` (layer `edge` in the architecture map)
with `hugrgate/edge/platform.py`:

- **`PlatformProbe`** — reads `platform.machine()`, `os.cpu_count()`,
  `os.sysconf("SC_PAGE_SIZE")`, `sys.byteorder`, `struct.calcsize("P")`,
  and `/proc/cpuinfo` `Features` lines. All filesystem reads are
  injectable fixtures, so the probe is fully testable on x86 CI.
- **`PlatformInfo`** — immutable snapshot (`arch`, `cpu_features`,
  `page_size`, `is_arm64`, `live` flag distinguishing host data from
  fixtures), JSON-serializable via `to_dict()`.
- **`audit_arm64()`** — produces an `Arm64AuditReport` of typed
  `Arm64Finding`s (stable id, `info|warning|error` severity, area,
  message, remediation, derivation source). Checks: arch is aarch64,
  little-endian, 64-bit Python, Python ≥ 3.10, ASIMD/NEON presence,
  sane page size, multi-core, numpy availability. Verdict: `passed`
  iff zero `error` findings; warnings never block.
- `hugrgate/edge/__init__.py` facade (empty `__all__` for now; slices
  177+ will grow it).

## Integration

- New `edge` layer registered in `tools/gen_arch_map.py`; regenerated
  `docs/campaign-i/architecture-map.md` and
  `docs/campaign-i/003-public-api-inventory.md` (every module declares
  `__all__`; gate tests green).
- `tests/test_edge_platform.py` registered in the unit row of the test
  taxonomy doc.

## Validation notes (Execution Law rule 13)

No ARM64 hardware in this environment. The audit logic is proven
against fixtures and the live x86 host probe, but real board claims
(CPU throttling behavior, NEON throughput, 16 k page-size kernels)
**require on-device runs** — every remediation that depends on silicon
carries an explicit `NEEDS_HARDWARE_VALIDATION` note.

## Verification

- `pytest tests/test_edge_platform.py` — 12 passed
- `ruff check hugrgate/edge/ tests/test_edge_platform.py` — clean
- `mypy hugrgate/edge/` — clean
- `pytest tests/test_taxonomy.py tests/test_arch_map.py tests/test_api_inventory.py` — green (run after doc updates)
