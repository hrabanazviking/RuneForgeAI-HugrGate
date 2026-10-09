# Slice 039 — Risk matrices

## What existed before
- Slices 037–038: expectation optimizers (min expected cost, max expected
  utility). No worst-case or tail-risk rules — a decision that is great on
  average but catastrophic 1% of the time looked optimal.

## What changed
- **`hugrgate/contracts/risk.py`** (new, kind `"risk"`):
  - Reuses `CostMatrix` as the loss matrix (no duplication — law 2).
  - `minimax_decision` — minimize worst-case loss; distribution-free.
  - `minimax_regret_decision` — minimize worst-case regret via an explicit
    `regret_table` (`regret[d][o] = loss[d][o] − min_d′ loss[d′][o]`, all ≥ 0).
  - `cvar_of_decision` / `cvar_decision` — CVaR_α over the discrete loss
    distribution (worst outcomes first, boundary outcome split
    proportionally); α=0 provably recovers the expected loss (tested).
  - `RiskContract`: outcomes + loss matrix + `attitude`
    (`minimax`/`minimax_regret`/`cvar`, α∈[0,1)); `decide` needs a
    distribution only for `cvar`; `expected_cost` kept as the risk-neutral
    baseline for comparison.
- **`hugrgate/contracts/__init__.py`**: lazy `risk` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Demonstrated divergence: p(calm)=0.9 gives E[calm]=10 < E[crisis]=40
  (min-cost picks calm) while minimax picks crisis (worst 40 < 100) —
  the attitudes genuinely disagree, which is the point of the slice.
- Initial test draft used a non-square decisions×outcomes matrix;
  `CostMatrix` requires square axes, so tests were rewritten with a
  proper square matrix instead of weakening the matrix invariant.

## Tests
- `tests/test_contracts_039.py`: 19 tests — minimax, regret table math,
  minimax-regret, CVaR hand-computed values, α=0≡expectation, attitude
  validation, distribution requirement for CVaR, round-trips, tie/single
  boundaries.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/risk.py`, `tests/test_contracts_039.py`.
