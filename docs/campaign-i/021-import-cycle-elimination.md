# Slice 021 — Import-cycle elimination

**Date:** 2026-10-09 · **Tests:** `tests/test_import_cycles.py` (3 tests)

## The cycle

Tarjan SCC over the real import graph found one: `hugrgate.client`
↔ `hugrgate.server`. `server` imported `policy_from_dict` from
`client` at module level; `client` lazily imported `build_gate` from
`server`. The lazy import dodged the `ImportError`, but the
architectural cycle was real (and the old arch-map test merely
documented it as "known").

## The fix

New neutral module `hugrgate/serde.py` holding `policy_to_dict`,
`policy_from_dict`, `result_from_dict`. `server`, `daemon`, and `cli`
now import from `serde`; `client` re-exports the three helpers
(identity-checked by test — `from hugrgate.client import
policy_from_dict` keeps working). The client's one remaining server
edge stays function-lazy, now justified only by keeping
FastAPI/uvicorn out of the lightweight SDK import. `serde` added to
the `contracts` layer in `tools/gen_arch_map.py`.

## Verification

SCC re-run: 44 modules, **no cycles**. New regression tests: full
graph (lazy edges included) acyclic, `serde` dependency-neutral,
re-export identity. Arch-map + API inventory + repo manifest
regenerated. Full suite 496 passed; mypy clean on 44 files.
