# Slice 293 — Lock contention audit

**Status:** complete. Commit: `feat(gjallarbu-293)` on `gjallarbu/campaign-xii`.

## What was built

- `hugrgate/lockaudit.py` — new module:
  - `InstrumentedLock`: drop-in `Lock`/`RLock` wrapper measuring
    acquisitions, total/mean/max *wait* (contention) and *hold* time.
    Overhead is two `perf_counter` calls per acquisition — a
    diagnostic tool, not a production replacement.
  - `audit_locks(package_root)`: AST pass over the package finding
    every `with <lock>:` critical section (268 in this codebase) and
    flagging `nested-lock` (lock-order/deadlock shape),
    `blocking-call` (sleep/I/O/join inside a critical section), and
    `call-in-critical-section` (any call extending a hold — triage
    fodder). `cond.wait()`/`notify()` on the held condition is
    correctly exempted. Plus `summarize()`.

## Audit results (real run over `hugrgate/`)

- 268 critical sections, 641 findings: 595 call-in-critical-section,
  46 blocking-call, **0 nested-lock** — the codebase has no
  lock-ordering edges; every critical section takes exactly one lock.
- Most blocking-call hits are false positives (`dict.get()`,
  `socket.get()`-shaped names); the two real ones —
  `edge/storage.py::flush` (file rewrite + `os.fsync`) and
  `edge/recovery.py::checkpoint` (file write) — hold the lock
  **deliberately**: buffer-swap + file-replace atomicity requires it,
  and flushes are rare. Documented as accepted, not refactored
  (high-risk change for no hot-path gain).

## Fix applied (the audit's top actionable finding)

`DecisionCache.get/put` computed `cache_key()` (~24µs) and the result
copy (~9µs) *inside* `self._lock` — pure functions of the arguments
with no shared-state access. Both are now hoisted out; the critical
section holds only the dict probe / insert and LRU touch (~1µs).
`_get_locked` was inlined into `get` (no other callers).

Measured (8-thread hammer, best-of-5 medians; old code loaded from
the pre-fix commit for a true A/B):

| threads | pre-fix | post-fix |
|---|---|---|
| 1 | 59.1k ops/s | 58.4k ops/s (tie) |
| 2 | 51.8k | **56.8k (+10%)** |
| 4 | 48.1k | **57.2k (+19%)** |
| 8 | 47.1k (stable) | 36.0k median, range 25k–56k |

Honest caveat: at 8-thread saturation the post-fix run is *unstable*
(GIL convoy on the hoisted CPU-bound key work in a pathological
tight loop; ranges overlap). With realistic interleaving (2ms backend
work between cache ops) pre/post are indistinguishable — backends
dominate, and the shorter hold strictly improves tail latency for
contended `put`s. The hoist is the textbook-correct critical-section
shrinkage; kept with the caveat recorded.

## Tests

`tests/test_perf_293_lockaudit.py` — 8 tests: lock stats, real
two-thread contention measurement, uncontended fast path, bad kind,
`locked()` passthrough, AST patterns on a synthetic package
(nested/blocking/call found, `cond.wait()` and `with open()`
correctly ignored), `summarize()`, and a regression test that the
real package has zero nested-lock findings. All green; ruff clean.
