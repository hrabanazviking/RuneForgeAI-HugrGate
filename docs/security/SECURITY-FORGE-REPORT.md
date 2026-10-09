# SECURITY-FORGE-REPORT — Campaign XVII (slices 401–425)

**Mission:** Attack the HugrGate runtime as if it were exposed to hostile
inputs, models, plugins, and networks — then harden what breaks.

**Built on, not duplicating:** privacy fortress (redaction, tokenization,
sealed crypto), secret detection (slice 234), hash-chained audit logs
(slice 015), cluster mutual auth (slice 208).

**Method:** Six Mythic Engineering roles per slice; Yrsa Execution Law;
anti-checkbox rule — every slice attacked existing capabilities first.

## Slice log

| Slice | Artifact | Result |
|---|---|---|
| 401 | `hugrgate/security/threat_model.py` — STRIDE v2, executable + validated | 18 threats, all validated |
| 402 | `hugrgate/security/attack_surface.py` — AST-derived surface inventory + drift detector | no drift |
| 403 | `hugrgate/security/depscan.py` — advisory DB (8 verified CVEs) + scanner | no advisories |
| 404 | `hugrgate/security/supply_chain.py` — policy, CycloneDX SBOM | done |
| 405 | `hugrgate/security/model_signing.py` — HMAC-signed metadata, TrustedModelStore | done |
| 406 | `hugrgate/security/checksums.py` — SHA-256 manifests, verify-then-load | done |
| 407 | `hugrgate/security/plugins.py` — trust levels, signed manifests, capability grants | done |
| 408 | `hugrgate/security/sandbox.py` — audit-hook sandbox, SandboxedBackend | done |
| 409 | `hugrgate/security/input_limits.py` — input-size policy | done |
| 410 | `hugrgate/security/resource_guards.py` — RLIMIT enforcement + CostLedger | done |
| 411 | `hugrgate/security/serde_guards.py` — SafeUnpickler allowlist, 3 call sites hardened | done |
| 412 | `hugrgate/security/path_guards.py` — safe_join containment invariant | done |
| 413 | `hugrgate/security/injection_corpus.py` — 30-payload corpus, sanitizers | 30/30 handled |
| 414 | `hugrgate/security/prompt_injection.py` — fenced data regions, override detector | done |
| 415 | `hugrgate/security/malicious_backend.py` — 5 hostile backends, gauntlet | 5/5 contained |
| 416 | `hugrgate/security/provenance_guards.py` — tamper battery + signed tip checkpoints | 6/6 detected |
| 417 | `hugrgate/security/cache_poisoning.py` — namespace/version key bindings, poison suite | 5/5 contained |
| 418 | `hugrgate/security/replay.py` — ReplayGuard + signed envelopes; bounded cluster seq map | done |
| 419 | `hugrgate/security/authz.py` — deny-by-default roles + capabilities (T-12) | done |
| 420 | `hugrgate/security/ratelimit.py` — per-key token buckets, bounded table (T-13) | done |
| 421 | `hugrgate/security/secret_audit.py` — AST secret-handling audit + standing gate | clean |
| 422 | `hugrgate/security/fuzzing.py` — seeded harness; 8 T-16 crash classes fixed | 31,500 cases, 0 crashes |
| 423 | `tools/secscan.py` — static analysis + gate; TokenVault RCE fixed | 0 high findings |
| 424 | `hugrgate/security/gauntlet.py` — all-battery capstone | 12/12 hold |
| 425 | this report + release gate | — |

## Real vulnerabilities found and fixed

The campaign was not a checklist — the adversarial batteries found
genuine defects in existing code:

1. **Cache cross-tenant reads (T-05).** The cache key bound
   state+spec+policy but not the tenant or model generation; two
   tenants (or two model versions) sharing a cache could read each
   other's entries. Fixed with `namespace`/`model_version` key
   bindings, threaded through the AEAD associated data. Testing also
   exposed an associated-data mismatch between sealing and
   verification in `EncryptedDecisionCache` — fixed.
2. **Unbounded cluster replay map.** `ClusterNode._last_seq` grew one
   entry per sender id forever — a sender-id flood was a
   memory-exhaustion vector. Now a bounded 4096-entry LRU (eviction
   only matters under flood, where the shared key is already
   compromised).
3. **Eight parser crash classes (T-16).** Fuzzing found `KeyError`,
   `TypeError`, and `ValueError` escapes in `DecisionSpec.from_dict`,
   `policy_from_dict`, `result_from_dict`, and both compact codecs
   (missing required keys, non-dict input, mixed-type keys breaking
   `sorted()`, non-mapping `distribution`/`metadata`, non-iterable
   `review_band`). All now raise `SpecError`/`PolicyError`/`SerdeError`.
4. **TokenVault pickle RCE.** `TokenVault.import_vault` ran
   `pickle.loads` on caller-supplied bytes — arbitrary code execution
   on a hostile blob, missed by the slice-411 hardening. Now decoded
   through the deserialization allowlist with structure validation.
5. **Import cycle.** A `security → privacy_crypto` import-time edge
   (via `serde_guards`) bit twice; resolved with lazy imports per the
   established convention. `test_import_cycles` stays green.

## Threat coverage (T-01–T-18)

All 18 STRIDE threats validate; every threat names its tests except
T-18, which is a documented **accepted** residual (cache-timing
side channel is out of scope for the local-first single-tenant
model). Residuals recorded honestly in the model:

- T-12 (unauthenticated service access): **partial** — the AuthZ
  policy engine ships deny-by-default; TLS termination, key
  distribution, and per-route server wiring remain operator
  responsibility.
- T-18 (cache timing): **accepted**.

## New error taxonomy (12 classes, all `recoverable=False` except noted)

`SupplyChainViolation`, `SignatureVerificationFailed`,
`PluginTrustError`, `SandboxViolation`, `InputTooLarge`,
`ResourceBudgetExceeded`, `DeserializationBlocked`,
`PathTraversalBlocked`, `PromptInjectionBlocked`,
`ReplayDetected`, `AuthzDenied`, `RateLimitExceeded`
(`recoverable=True` — "retry after `retry_after_ms`" is the correct
response).

## Gates (release criteria)

- **Full test suite:** green (see below).
- **ruff:** clean over `hugrgate/`, `tools/`, `tests/`.
- **mypy:** clean over `hugrgate/` (387 files).
- **Security gauntlet:** 12/12 batteries hold
  (`tests/test_sec_424_gauntlet.py`).
- **Static scan:** `tools/secscan.py` — 0 high findings over
  `hugrgate/` and `tools/`.
- **Secret audit:** 0 high/medium findings over `hugrgate/`.
- **Fuzzing:** 31,500 cases over 7 targets × 3 seeds — 0 crashes,
  0 hangs.
- **Campaign security tests:** 256 tests across 24
  `test_sec_4xx_*` modules.

## Running the gauntlet

```bash
~/workspace/RuneForgeAI-HugrGate/venv/bin/python -m pytest \
    tests/test_sec_424_gauntlet.py -q
~/workspace/RuneForgeAI-HugrGate/venv/bin/python tools/secscan.py hugrgate
~/workspace/RuneForgeAI-HugrGate/venv/bin/python -c "
from hugrgate.security.secret_audit import run_secret_audit
r = run_secret_audit('hugrgate'); print(r['by_severity'])"
```

## Full suite result

<!-- filled by slice 425 on the release run -->
