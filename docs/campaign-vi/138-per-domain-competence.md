# Slice 138 — Per-domain competence

**Status:** complete. **Tests:** `tests/test_adaptive_domain_competence.py` — 8 tests green.

## What existed before

Slice 137 averaged each backend over everything — a backend superb at
categorical classification but weak at numeric regression looked merely
"average".

## What was built

`hugrgate/adaptive/domain_competence.py` — `PerDomainCompetence`:

- One `CompetenceProfile` per `(backend, domain)`; observations also fold
  into the global backend profile (the domain view refines, never replaces).
- Domain resolution: `spec.metadata["domain"]` → spec `type` → `"unknown"`.
- `get_with_fallback`: exact domain → global backend profile → `None` — the
  router always has *some* evidence; cold domains inherit the backend's
  overall reputation.
- `ranked_in_domain`, `domains()`, `to_dict`/`from_dict`
  (`adaptive-domain-competence/v1`).

## Integration

- Builds on slice 137; reads domains from `DecisionSpec.metadata` /
  telemetry spec dicts.

## Verification

- `pytest tests/test_adaptive_domain_competence.py` — 8/8 green: resolution
  order, per-domain tracking, fallback ladder, telemetry batch update,
  Wilson-ordered in-domain ranking, serialization.
- `mypy hugrgate/adaptive` — clean.
