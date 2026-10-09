# Slice 294 — Multiprocess mode

**Status:** complete. Commit: `feat(gjallarbu-294)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

All HugrGate fan-out was thread-bound (`ThreadPoolBatchExecutor`,
slice 282; `BatchScheduler`, slice 285). Threads share the GIL, so
CPU-bound batch work — calibration sweeps, benchmark matrices, bulk
replays — could not scale past one core. There was no sanctioned way
to run gate work in other processes.

## What was built

- `hugrgate/multiproc.py` — new module:
  - `ProcessPool`: taxonomy-clean wrapper over
    `ProcessPoolExecutor` with `submit(fn, *args, **kwargs)` and
    ordered `map(fn, items)`.
  - **Picklability contract**: callable, args, kwargs, and (for
    `map`) every item are `pickle`-validated *before* submission;
    failures raise `MultiprocError` naming the offending object
    instead of killing a worker obscurely.
  - Worker exceptions, timeouts, and worker crashes
    (`BrokenProcessPool`) all surface as `MultiprocError`
    (recoverable) with the worker exception's type name preserved.
  - Default start method `"spawn"` — the gate hosts threads, locks,
    and reaper threads that do not survive `fork` safely.
  - Stats: submitted/completed/failed; idempotent shutdown.
- `hugrgate/errors.py`: new `MultiprocError` (`code="multiproc_error"`,
  `recoverable=True`); registered in `tests/test_errors.py`;
  `"multiprocessing"` added to `_STDLIB` in
  `tests/test_dependency_rules.py`.

## Tests

`tests/test_perf_294_multiproc.py` — 18 tests over real spawned
processes (2 workers): submit/map round-trips, kwargs, ordering,
empty map, picklability rejection for callable/args/kwargs/items
(`threading.Lock` fixtures — `object()` pickles fine, a wrong first
premise the tests caught), worker `ValueError` → `MultiprocError`,
task timeout (slow-marked, 5s sleeper), `os._exit` worker crash →
`MultiprocError`, stats, config validation, post-shutdown rejection,
idempotent shutdown, `Future.exception()` accessor. All green; ruff
clean; error-taxonomy, dependency-rule, and import-cycle gates green.

## Findings fixed during implementation

- `raise _translate_exception(e)` tripped
  `test_raise_sites_use_taxonomy_or_stdlib_validation` (raise sites
  must name a taxonomy class); refactored to a `_describe_failure`
  message builder with `raise MultiprocError(...)` at the sites.
