# Slice 060 — Privacy-aware routing v2

## What existed
v1 gated only on backend *location* (remote vs local). Nothing
considered *what the data is*: a remote backend cleared for
"favorite_color" was equally cleared for SSNs.

## What changed
- **`hugrgate/routing/privacy.py`** (new):
  - `PrivacyTier` (IntEnum): PUBLIC < INTERNAL < CONFIDENTIAL <
    RESTRICTED.
  - `DataClassifier`: key-name heuristics (`ssn`/`password` →
    RESTRICTED, `email`/`phone` → CONFIDENTIAL, `internal_*` →
    INTERNAL), custom `extra_rules`, explicit `spec.metadata`
    `["data_tier"]` override (invalid values rejected), and a
    `privacy_class="strict"` policy floor at CONFIDENTIAL.
  - `BackendClearance`: local + no-retention → RESTRICTED; remote or
    retaining → INTERNAL; remote *and* retaining → PUBLIC. Grades from
    `privacy_properties()`, not just the `is_remote` flag.
  - `PrivacyAwarePlanner`: prunes rungs where data tier > backend
    clearance, stamping `privacy_tier`/`backend_clearance` per node.

## Adversarial tests (all passing)
- Remote backend + SSN state → pruned → `Abstention`, even with
  `remote_inference=True`.
- Retaining backend + CONFIDENTIAL email → pruned.
- Strict policy + remote backend + innocuous data → blocked (floor beats
  clearance).
- Spoofed `is_remote=False` with `privacy_properties()["remote"]=True`
  → graded by properties, still blocked for RESTRICTED.

## Integration
Defense in depth over existing guards: executor `skip_reason` (policy +
`PrivacyGuard`) still re-checks at run time. Provenance redaction on
strict policies unchanged.

## Tests
`tests/test_routing_060.py` (11 tests): key classification incl.
boundaries, extra rules, tier override + invalid rejection, strict
floor, all four clearance grades, tier pruning, public-data remote
pass-through, the four adversarial cases above, and a local
RESTRICTED end-to-end win.

## Evidence
- `pytest tests/test_routing_060.py` → 11 passed.
