# Slice 129 — Router feature extraction

**Status:** complete. **Tests:** `tests/test_adaptive_router_features.py` — 10 tests green.

## What existed before

`hugrgate/features.py` (slice 21) defined the `FeatureExtractor` contract for
*decision* state. Nothing featurized *routing* context — spec type, policy
constraints, candidate-set shape.

## What was built

`hugrgate/adaptive/router_features.py`:

- `RouteContext`: state + spec + policy + candidates + per-candidate stats.
- `RouterFeatureExtractor(FeatureExtractor)`: 23 fixed, documented numeric
  columns — `spec_type__*` one-hot, `state__*` shape (key count, text length,
  numeric fraction), `policy__*` constraints normalized (min probability,
  latency/cost budgets, remote/strict flags, allowed/preferred counts),
  `cand__*` summaries (best/mean/spread of quality, latency, cost).
- Implements the slice-21 contract (`extract` / `feature_names` /
  `transform_batch` via the ABC), so existing feature tooling accepts it.
- Stateless (fitted from birth); missing context degrades to zeros, never
  NaN — a NaN would silently poison the bandit's linear model downstream;
  non-finite inputs are clipped.

## Integration

- Contracts: `DecisionSpec`, `DecisionPolicy` from the contracts layer;
  `BackendError` (not silent zeros) when given something that isn't a
  `RouteContext`.

## Verification

- `pytest tests/test_adaptive_router_features.py` — 10/10 green: one-hot
  correctness across all five spec types, policy normalization math,
  candidate summaries, finiteness, graceful degradation, `transform_batch`
  shape via the ABC.
- `mypy hugrgate/adaptive` — clean.
