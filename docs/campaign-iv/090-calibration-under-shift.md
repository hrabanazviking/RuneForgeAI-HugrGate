# Slice 090 — Calibration under shift

## What existed
Drift monitoring (088) and imbalance tooling (089) existed, but distribution
shift had no dedicated machinery: no shift detection, no covariate-shift
correction, no label-shift prior estimation.

## What changed
- `hugrgate/calibration/shift.py` (new):
  - `psi` / `psi_band` — population stability index with standard
    interpretation bands for detecting covariate shift on the score axis.
  - `density_ratio_weights` — binned `p_target/p_source` importance weights
    (mean-1 normalized).
  - `resample_for_shift` — resamples the source fit set to mimic the target
    covariate mix (asserted: post-resample PSI drops below "significant").
  - `em_target_prior` — Saerens EM estimate of the target positive rate
    from unlabeled target scores; feeds the slice-089 prior correction.
- `hugrgate/calibration/__init__.py` — exports `shift`.

## Statistical validation
N(0,1) → N(1.5,1) covariate shift: PSI jumps from < 0.1 to > 0.25;
weights up-weight the target neighborhood; resampling removes the
"significant" band. Label shift 20% → 60%: EM recovers 0.6 within ±0.08.

## Tests
`tests/test_calib_shift.py` — 4 tests, all green.
