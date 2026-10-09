# Security Forge — Campaign XVII (slices 401–425)

**Mission:** Attack the runtime as if it were exposed to hostile
inputs, models, plugins, and networks.

Built on top of the existing defenses — privacy fortress (redaction,
tokenization, sealed crypto), secret detection (slice 234),
hash-chained provenance (slice 015), cluster mutual auth (slice
208) — hardening what exists, not duplicating it.

## Slice log

| Slice | Artifact | Status |
|---|---|---|
| 401 | `hugrgate/security/threat_model.py` — STRIDE threat model v2, executable + validated | done |
| 402 | `hugrgate/security/attack_surface.py` — attack-surface inventory | done |
| 403 | `hugrgate/security/depscan.py` — dependency security scan | done |
| 404 | `hugrgate/security/supply_chain.py` — supply-chain policy + SBOM | done |
| 405 | `hugrgate/security/model_signing.py` — signed model metadata | done |
| 406 | `hugrgate/security/checksums.py` — model checksum enforcement | done |
| 407 | `hugrgate/security/plugins.py` — plugin trust model | done |
| 408 | `hugrgate/security/sandbox.py` — backend sandbox boundary | done |
| 409 | `hugrgate/security/input_limits.py` — input-size limits | done |
| 410 | `hugrgate/security/resource_guards.py` — resource-exhaustion guards | done |
| 411 | `hugrgate/security/serde_guards.py` — deserialization hardening | done |
| 412 | `hugrgate/security/path_guards.py` — path traversal defenses | done |
| 413 | `hugrgate/security/injection_corpus.py` — injection test corpus | pending |
| 414 | `hugrgate/security/prompt_injection.py` — prompt-injection boundary | pending |
| 415 | `hugrgate/security/malicious_backend.py` — malicious-backend fixtures | pending |
| 416 | `hugrgate/security/provenance_guards.py` — provenance tamper detection | pending |
| 417 | `hugrgate/security/cache_poisoning.py` — cache-poisoning defenses | pending |
| 418 | `hugrgate/security/replay.py` — replay attack defenses | pending |
| 419 | `hugrgate/security/authz.py` — service authorization policy | pending |
| 420 | `hugrgate/security/rate_limit.py` — rate limiting | pending |
| 421 | `hugrgate/security/secret_audit.py` — secret-handling audit | pending |
| 422 | `hugrgate/security/fuzzing.py` — fuzzing campaign harness | pending |
| 423 | `tools/secscan.py` + gate — static security analysis | pending |
| 424 | `hugrgate/security/gauntlet.py` — security gauntlet | pending |
| 425 | release gate + completion report | pending |

Supporting docs: `threat-model.md` (generated from the module),
`SECURITY-FORGE-REPORT.md` (slice 425).
